"""Shared infrastructure for experiment protocols.

Every protocol calls the model through `ask`, which guarantees:
- identical objective text across arms (the arm only changes the system prompt)
- per-call logging of exact prompts and raw responses
- one retry on unparseable output; technical failure never becomes character intent
"""
from __future__ import annotations

import json
from pathlib import Path

from ..appraisal import render_private_context
from ..characters import Character
from ..engine import InvalidActionError, parse_action
from ..prompts import build_system
from ..psyche import apply_event, decay_pad, new_relationship, update_relationship


class JsonlLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seq = 0

    def write(self, event: dict) -> None:
        self._seq += 1
        with self.path.open("a") as f:
            f.write(json.dumps({"seq": self._seq, **event}, ensure_ascii=False) + "\n")


class AgentState:
    """One character's live psychological state for a protocol run."""

    def __init__(self, char: Character, others: dict):
        self.char = char
        self.others = dict(others)
        self.pad = dict(char.affect_baseline)
        self.relationships = {oid: new_relationship() for oid in others}

    def event(self, event_type: str) -> None:
        self.pad = apply_event(self.pad, event_type, self.char)

    def rel_event(self, target_id: str, event_type: str) -> None:
        self.relationships[target_id] = update_relationship(self.relationships[target_id], event_type)

    def decay(self, dt_seconds: float) -> None:
        self.pad = decay_pad(self.pad, self.char.affect_baseline, dt_seconds, self.char.affect_half_life_seconds)

    def snapshot(self) -> dict:
        return {
            "pad": {k: round(v, 4) for k, v in self.pad.items()},
            "relationships": {t: {k: round(v, 4) for k, v in r.items()} for t, r in self.relationships.items()},
        }


def parse_json_reply(text: str, required: dict) -> dict:
    """Extract a JSON object and check required keys with expected types."""
    try:
        obj = parse_action(text) if "action" in required else None
    except InvalidActionError:
        obj = None
    if obj is None:
        import re

        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*\n?|```$", "", cleaned, flags=re.MULTILINE).strip()
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not m:
            raise InvalidActionError(f"no JSON object in: {text[:200]}")
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            raise InvalidActionError(f"bad JSON: {text[:200]}") from e
    for key, typ in required.items():
        if key not in obj or not isinstance(obj[key], typ):
            raise InvalidActionError(f"missing/invalid '{key}' in: {json.dumps(obj, ensure_ascii=False)[:200]}")
    return obj


def ask(
    provider,
    arm: str,
    char: Character,
    state: AgentState,
    objective: str,
    topic_tags: list,
    log: JsonlLog,
    meta: dict,
    parser,
):
    private_ctx = None
    if arm == "pure_pneuma":
        private_ctx = render_private_context(
            char, state.pad, state.relationships, list(topic_tags), others=state.others
        )
    system = build_system(arm, char, private_ctx)

    def attempt(user_text: str):
        raw = provider.complete(system, user_text)
        return parser(raw), raw

    try:
        parsed, raw = attempt(objective)
    except InvalidActionError as e:
        log.write({"type": "retry", "actor": char.character_id, "error": str(e), **{k: v for k, v in meta.items() if k != "type"}})
        parsed, raw = attempt(objective + "\n\n必ず指定されたJSONのみで答えること。")
    log.write({
        **meta, "actor": char.character_id, "arm": arm,
        "parsed": parsed, "state": state.snapshot(),
        "system_prompt": system, "user_prompt": objective, "raw_response": raw,
    })
    return parsed
