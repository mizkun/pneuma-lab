"""Iterated prisoner's dilemma with pre-round communication (one pair)."""
from __future__ import annotations

import json
from pathlib import Path

from ..characters import Character
from ..engine import InvalidActionError
from .common import AgentState, JsonlLog, ask, parse_json_reply

PAYOFFS = {("cooperate", "cooperate"): (3, 3), ("cooperate", "defect"): (0, 5),
           ("defect", "cooperate"): (5, 0), ("defect", "defect"): (1, 1)}
TURN_SECONDS = 60.0
CHOICE_JA = {"cooperate": "協力", "defect": "自分優先"}


def _history_text(history: list[dict], me: str, other_name: str) -> str:
    if not history:
        return "（まだ最初のラウンド）"
    out = []
    for h in history:
        out.append(f"ラウンド{h['round']}: 会話:")
        out.extend(f"  {line}" for line in h["messages"])
        oid = next(k for k in h["choices"] if k != me)
        mine, theirs = h["choices"][me], h["choices"][oid]
        if mine == theirs:
            out.append(f"  → 両者とも「{CHOICE_JA[mine]}」を選んだ。")
        else:
            out.append(f"  → あなたは「{CHOICE_JA[mine]}」、{other_name}は「{CHOICE_JA[theirs]}」を選んだ。")
        out.append(f"  現在の得点: あなた {h['scores'][me]}点 / {other_name} {h['scores'][oid]}点")
    return "\n".join(out)


def _msg_objective(scenario: dict, rnd: int, rounds: int, history: list, me: str, other_name: str, this_round_msgs: list) -> str:
    cur = ("\n# このラウンドの会話\n" + "\n".join(this_round_msgs)) if this_round_msgs else ""
    return (
        f"# ルール\n{scenario['rules']}\n\n"
        f"# これまでの経過\n{_history_text(history, me, other_name)}\n\n"
        f"いまはラウンド{rnd}/{rounds}の会話フェーズ。相手は{other_name}。{cur}\n"
        "# 出力形式\n"
        '次のJSONのみを出力する:\n{"message": "相手への短いメッセージ"}'
    )


def _choice_objective(scenario: dict, rnd: int, rounds: int, history: list, me: str, other_name: str, this_round_msgs: list) -> str:
    return (
        f"# ルール\n{scenario['rules']}\n\n"
        f"# これまでの経過\n{_history_text(history, me, other_name)}\n\n"
        f"# このラウンドの会話\n" + "\n".join(this_round_msgs) + "\n\n"
        f"いまはラウンド{rnd}/{rounds}の選択フェーズ。選択は相手に見えないまま同時に公開される。\n"
        "# 出力形式\n"
        '次のJSONのみを出力する:\n{"choice": "cooperate|defect", "inner": "口に出さない本音(任意)"}'
    )


def run_pd(arm: str, pair: tuple, provider, scenario: dict, out_dir: Path, rounds: int = 4,
           dynamics: str = "v1", appraiser=None, behavior_line: str | None = None) -> dict:
    c1, c2 = pair
    out_dir = Path(out_dir)
    log = JsonlLog(out_dir / f"{arm}_pd_{c1.character_id}_{c2.character_id}.jsonl")
    states = {
        c1.character_id: AgentState(c1, others={c2.character_id: c2.display_name}),
        c2.character_id: AgentState(c2, others={c1.character_id: c1.display_name}),
    }
    scores = {c1.character_id: 0, c2.character_id: 0}
    v2 = dynamics == "v2"

    def computed_for(rnd: int) -> list:
        return ["次のラウンドはない。これが最後の選択になる。"] if (v2 and rnd == rounds) else []

    def appraise_msg(speaker, listener, message: str) -> None:
        if not v2 or appraiser is None or not arm.endswith("pneuma") or not message:
            return
        verdicts = appraiser.appraise(speaker.display_name, message, {listener.character_id: listener.display_name})
        from ..psyche import apply_appraisal, update_relationship_appraisal
        vv = verdicts.get(listener.character_id, {"kind": "neutral", "intensity": 0})
        if vv["kind"] != "neutral" and vv["intensity"] > 0:
            lst = states[listener.character_id]
            lst.pad = apply_appraisal(lst.pad, vv["kind"], vv["intensity"], listener)
            lst.relationships[speaker.character_id] = update_relationship_appraisal(
                lst.relationships[speaker.character_id], vv["kind"], vv["intensity"])
        log.write({"type": "appraisal", "speaker": speaker.character_id, "message": message, "verdicts": verdicts})
    history: list[dict] = []
    coop_counts = {c1.character_id: 0, c2.character_id: 0}
    sucker_events = []
    per_round = []

    def choice_parser(text: str) -> dict:
        obj = parse_json_reply(text, required={"choice": str})
        if obj["choice"] not in ("cooperate", "defect"):
            raise InvalidActionError("choice must be cooperate|defect")
        return obj

    for rnd in range(1, rounds + 1):
        msgs = []
        for me, other in ((c1, c2), (c2, c1)):
            st = states[me.character_id]
            st.decay(TURN_SECONDS)
            parsed = ask(provider=provider, arm=arm, char=me, state=st,
                         objective=_msg_objective(scenario, rnd, rounds, history, me.character_id, other.display_name, msgs),
                         topic_tags=scenario["topic_tags"], log=log,
                         meta={"type": "pd_message", "round": rnd},
                         parser=lambda t: parse_json_reply(t, required={"message": str}),
                         dynamics_v2=v2, computed_lines=computed_for(rnd), behavior_line=behavior_line)
            msgs.append(f"{me.display_name}: {parsed['message']}")
            appraise_msg(me, other, parsed["message"])
        choices = {}
        for me, other in ((c1, c2), (c2, c1)):
            st = states[me.character_id]
            parsed = ask(provider=provider, arm=arm, char=me, state=st,
                         objective=_choice_objective(scenario, rnd, rounds, history, me.character_id, other.display_name, msgs),
                         topic_tags=scenario["topic_tags"], log=log,
                         meta={"type": "pd_choice", "round": rnd},
                         parser=choice_parser,
                         dynamics_v2=v2, computed_lines=computed_for(rnd), behavior_line=behavior_line)
            choices[me.character_id] = parsed["choice"]

        p1, p2 = PAYOFFS[(choices[c1.character_id], choices[c2.character_id])]
        scores[c1.character_id] += p1
        scores[c2.character_id] += p2
        for me, other in ((c1, c2), (c2, c1)):
            mid, oid = me.character_id, other.character_id
            if choices[mid] == "cooperate":
                coop_counts[mid] += 1
            if choices[mid] == "cooperate" and choices[oid] == "defect":
                sucker_events.append({"round": rnd, "victim": mid, "defector": oid})
                states[mid].event("betrayed")
                states[mid].rel_event(oid, "betrayed_me")
            elif choices[mid] == "cooperate" and choices[oid] == "cooperate":
                states[mid].event("agreement_received")
                states[mid].rel_event(oid, "cooperated_with_me")
        history.append({"round": rnd, "messages": msgs, "choices": dict(choices), "scores": dict(scores)})
        per_round.append(dict(choices))
        log.write({"type": "pd_round_result", "round": rnd, "choices": choices, "scores": dict(scores)})

    summary = {
        "protocol": "pd", "arm": arm,
        "pair": [c1.character_id, c2.character_id],
        "scores": scores,
        "coop_rate": {k: v / rounds for k, v in coop_counts.items()},
        "sucker_events": sucker_events,
        "per_round": per_round,
        "final_round": per_round[-1],
    }
    (out_dir / f"{arm}_pd_{c1.character_id}_{c2.character_id}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2))
    return summary
