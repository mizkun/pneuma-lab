"""Bystander effect protocol.

The subject works in a text chat when another member reports escalating
distress. Conditions: alone with the victim, or with three other (scripted,
passive) members present. Measure whether/when the subject takes concrete
helping action.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..characters import Character
from ..engine import InvalidActionError
from .common import AgentState, JsonlLog, ask, parse_json_reply

TURN_SECONDS = 60.0
ACTIONS = ("continue_work", "message", "call_help")


def _objective(scenario: dict, condition: str, chat_log: list[str]) -> str:
    members = "あなたと" + scenario["victim_name"]
    if condition == "group":
        members = "あなた、" + scenario["victim_name"] + "、" + "、".join(scenario["group_bystanders"])
    return (
        f"# 状況\n{scenario['setup']}\n参加メンバー: {members}。\n\n"
        "# ここまでのチャット\n" + "\n".join(chat_log) + "\n\n"
        "# いま取れる行動\n" + scenario["actions_text"] + "\n\n"
        "# 出力形式\n"
        '次のJSONのみを出力する:\n{"action": "continue_work|message|call_help", "message": "発言内容(messageのとき)"}'
    )


def run_bystander(arm: str, subject: Character, condition: str, provider, scenario: dict, out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    log = JsonlLog(out_dir / f"{arm}_bystander_{condition}_{subject.character_id}.jsonl")
    state = AgentState(subject, others={})
    chat: list[str] = []
    helped = False
    help_turn = None
    n_turns = 0

    for i, victim_line in enumerate(scenario["victim_lines"]):
        if condition == "group":
            chat.extend(scenario["group_filler_lines"][i])
        chat.append(victim_line)
        state.decay(TURN_SECONDS)
        state.event("distress_witnessed")

        def parser(text: str) -> dict:
            obj = parse_json_reply(text, required={"action": str})
            if obj["action"] not in ACTIONS:
                raise InvalidActionError(f"action must be one of {ACTIONS}")
            return obj

        parsed = ask(provider=provider, arm=arm, char=subject, state=state,
                     objective=_objective(scenario, condition, chat),
                     topic_tags=scenario["topic_tags"], log=log,
                     meta={"type": "turn", "turn": i + 1, "condition": condition}, parser=parser)
        n_turns = i + 1
        if parsed["action"] == "message" and parsed.get("message"):
            chat.append(f"{subject.display_name}: {parsed['message']}")
        if parsed["action"] == "call_help":
            helped = True
            help_turn = n_turns
            break

    summary = {
        "protocol": "bystander", "arm": arm, "subject": subject.character_id,
        "condition": condition, "helped": helped, "help_turn": help_turn, "n_turns": n_turns,
    }
    (out_dir / f"{arm}_bystander_{condition}_{subject.character_id}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2))
    return summary
