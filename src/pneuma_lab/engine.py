"""Discussion engine: deterministic world core + model-owned actions.

The engine owns turn order, feasible actions, validation, event log, and
psychological state updates. The model owns which action the character takes
and the words that accompany it. The engine never selects, ranks, or
recommends an action.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .appraisal import render_private_context
from .characters import Character
from .prompts import build_discussion_prompt
from .psyche import apply_event, decay_pad, new_relationship, update_relationship


class InvalidActionError(Exception):
    pass


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_action(text: str) -> dict:
    """Extract the first JSON object from model output (tolerates fences/prose)."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?|```$", "", cleaned, flags=re.MULTILINE).strip()
    candidates = [cleaned]
    m = _JSON_RE.search(cleaned)
    if m:
        candidates.append(m.group(0))
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "action" in obj:
            return obj
    raise InvalidActionError(f"no action JSON found in: {text[:200]}")


@dataclass
class PsycheState:
    pad: dict
    relationships: dict = field(default_factory=dict)


class Discussion:
    def __init__(
        self,
        chars: list[Character],
        arm: str,
        provider,
        item: dict,
        max_turns: int = 15,
        log_path: Path | None = None,
        turn_seconds: float = 60.0,
    ):
        self.chars = chars
        self.arm = arm
        self.provider = provider
        self.item = item
        self.max_turns = max_turns
        self.log_path = Path(log_path) if log_path else None
        self.turn_seconds = turn_seconds
        self.events: list[dict] = []
        self.dialogue: list[str] = []
        self.proposal: dict | None = None  # {"value", "proposer", "assents": set}
        self._seq = 0
        self.state: dict[str, PsycheState] = {
            c.character_id: PsycheState(
                pad=dict(c.affect_baseline),
                relationships={o.character_id: new_relationship() for o in chars if o is not c},
            )
            for c in chars
        }
        self._by_id = {c.character_id: c for c in chars}

    # ---- event log ----

    def _log(self, event: dict) -> None:
        self._seq += 1
        event = {"seq": self._seq, **event}
        self.events.append(event)
        if self.log_path:
            with self.log_path.open("a") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")

    # ---- psychology plumbing ----

    def _others(self, char: Character) -> dict:
        return {c.character_id: c.display_name for c in self.chars if c is not char}

    def private_context(self, char: Character) -> str:
        st = self.state[char.character_id]
        return render_private_context(
            char, st.pad, st.relationships, self.item.get("topic_tags", []), others=self._others(char)
        )

    def _impulse(self, char_id: str, event_type: str) -> None:
        st = self.state[char_id]
        st.pad = apply_event(st.pad, event_type, self._by_id[char_id])

    def _rel(self, owner_id: str, target_id: str, event_type: str) -> None:
        st = self.state[owner_id]
        st.relationships[target_id] = update_relationship(st.relationships[target_id], event_type)

    # ---- validation ----

    def _validate(self, action: dict) -> None:
        kind = action.get("action")
        allowed = {"say", "propose", "silence"} | ({"agree"} if self.proposal else set())
        if kind not in allowed:
            raise InvalidActionError(f"action '{kind}' is not available now (allowed: {sorted(allowed)})")
        if kind == "propose":
            value = action.get("value")
            if not isinstance(value, int) or not 1 <= value <= 10:
                raise InvalidActionError("propose requires integer 'value' in 1..10")

    # ---- main loop ----

    def _call_model(self, char: Character) -> tuple[dict, str, str, str]:
        private_ctx = self.private_context(char) if self.arm == "pure_pneuma" else None
        bundle = build_discussion_prompt(
            self.arm, char, self.item, self.dialogue,
            proposal_active=self.proposal is not None,
            private_context=private_ctx,
        )
        raw = self.provider.complete(bundle.system, bundle.user)
        action = parse_action(raw)
        self._validate(action)
        return action, bundle.system, bundle.user, raw

    def _turn(self, char: Character) -> None:
        st = self.state[char.character_id]
        st.pad = decay_pad(st.pad, char.affect_baseline, self.turn_seconds, char.affect_half_life_seconds)
        try:
            action, system, user, raw = self._call_model(char)
        except InvalidActionError as e:
            self._log({"type": "retry", "actor": char.character_id, "error": str(e)})
            note = f"（前回の{char.display_name}の出力は無効だった: {e}。もう一度。）"
            self.dialogue.append(note)
            try:
                action, system, user, raw = self._call_model(char)
            except InvalidActionError as e2:
                # double failure is a technical failure, never recorded as character intent
                self._log({"type": "forced_silence", "actor": char.character_id, "error": str(e2)})
                self.dialogue.remove(note)
                return
            self.dialogue.remove(note)

        self._log({
            "type": "action", "actor": char.character_id, "arm": self.arm,
            "action": action["action"], "message": action.get("message", ""),
            "value": action.get("value"),
            "system_prompt": system, "user_prompt": user, "raw_response": raw,
        })
        self._apply(char, action)

    def _apply(self, char: Character, action: dict) -> None:
        kind = action["action"]
        name = char.display_name
        message = (action.get("message") or "").strip()

        if kind == "say":
            self.dialogue.append(f"{name}: {message}")
            self._impulse(char.character_id, "spoke_up")

        elif kind == "propose":
            value = action["value"]
            if self.proposal and self.proposal["proposer"] != char.character_id:
                old = self.proposal["proposer"]
                self._impulse(old, "overrode_my_proposal")
                self._rel(old, char.character_id, "overrode_my_proposal")
            if message:
                self.dialogue.append(f"{name}: {message}")
            self.dialogue.append(f"（{name}が全員の結論として {value} を提案した）")
            self.proposal = {"value": value, "proposer": char.character_id, "assents": {char.character_id}}
            self._impulse(char.character_id, "spoke_up")

        elif kind == "agree":
            proposer = self.proposal["proposer"]
            if message:
                self.dialogue.append(f"{name}: {message}")
            self.dialogue.append(f"（{name}は現在の提案 {self.proposal['value']} に賛成した）")
            self.proposal["assents"].add(char.character_id)
            if proposer != char.character_id:
                self._impulse(proposer, "agreement_received")
                self._rel(proposer, char.character_id, "agreed_with_me")

        elif kind == "silence":
            self.dialogue.append(f"（{name}は黙っている）")
            self._impulse(char.character_id, "stayed_silent")

    def run(self) -> dict:
        self._log({"type": "start", "arm": self.arm, "item_id": self.item["item_id"],
                   "participants": [c.character_id for c in self.chars]})
        consensus = None
        n_turns = 0
        for i in range(self.max_turns):
            char = self.chars[i % len(self.chars)]
            self._turn(char)
            n_turns += 1
            if self.proposal and self.proposal["assents"] == {c.character_id for c in self.chars}:
                consensus = self.proposal["value"]
                self._impulse(self.proposal["proposer"], "proposal_accepted")
                self._log({"type": "consensus", "value": consensus, "proposer": self.proposal["proposer"], "n_turns": n_turns})
                break
        if consensus is None:
            self._log({"type": "no_consensus", "n_turns": n_turns})
        return {"consensus": consensus, "n_turns": n_turns, "events": self.events, "dialogue": list(self.dialogue)}
