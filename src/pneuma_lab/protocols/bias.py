"""Individual decision-bias protocols: framing effect and sunk cost.

Each question is an independent, stateless call (fresh psychological state,
no memory of the other condition).
"""
from __future__ import annotations

import json
from pathlib import Path

from ..characters import Character
from ..engine import InvalidActionError
from .common import AgentState, JsonlLog, ask, parse_json_reply


def _choice_parser(allowed: tuple):
    def parser(text: str) -> dict:
        obj = parse_json_reply(text, required={"choice": str})
        if obj["choice"] not in allowed:
            raise InvalidActionError(f"choice must be one of {allowed}")
        return obj
    return parser


def _framing_objective(scenario: dict, frame: str) -> str:
    opts = scenario[frame]
    return (
        f"# 状況\n{scenario['cover']}\n\n"
        f"- 案A: {opts['A']}\n- 案B: {opts['B']}\n\n"
        "どちらか一方を選ぶ。\n# 出力形式\n"
        '次のJSONのみを出力する:\n{"choice": "A|B", "reason": "一言"}'
    )


def run_framing(arm: str, chars: list[Character], provider, scenario: dict, out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    log = JsonlLog(out_dir / f"{arm}_framing.jsonl")
    choices: dict[str, dict] = {}
    for c in chars:
        choices[c.character_id] = {}
        for frame in ("gain", "loss"):
            state = AgentState(c, others={})
            parsed = ask(provider=provider, arm=arm, char=c, state=state,
                         objective=_framing_objective(scenario, frame),
                         topic_tags=scenario["topic_tags"], log=log,
                         meta={"type": "choice", "frame": frame},
                         parser=_choice_parser(("A", "B")))
            choices[c.character_id][frame] = parsed["choice"]
    n = len(chars)
    flips = sum(1 for v in choices.values() if v["gain"] == "A" and v["loss"] == "B")
    summary = {
        "protocol": "framing", "arm": arm, "choices": choices,
        "flip_rate": flips / n,
        "risk_averse_gain_rate": sum(1 for v in choices.values() if v["gain"] == "A") / n,
        "risk_seeking_loss_rate": sum(1 for v in choices.values() if v["loss"] == "B") / n,
    }
    (out_dir / f"{arm}_framing_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def _sunk_objective(scenario: dict, condition: str) -> str:
    return (
        f"# 状況\n{scenario[condition]}\n\n"
        "どちらかを選ぶ。\n# 出力形式\n"
        '次のJSONのみを出力する:\n{"choice": "continue|stop", "reason": "一言"}'
    )


def run_sunkcost(arm: str, chars: list[Character], provider, scenario: dict, out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    log = JsonlLog(out_dir / f"{arm}_sunkcost.jsonl")
    choices: dict[str, dict] = {}
    for c in chars:
        choices[c.character_id] = {}
        for condition in ("with_sunk", "without_sunk"):
            state = AgentState(c, others={})
            parsed = ask(provider=provider, arm=arm, char=c, state=state,
                         objective=_sunk_objective(scenario, condition),
                         topic_tags=scenario["topic_tags"], log=log,
                         meta={"type": "choice", "condition": condition},
                         parser=_choice_parser(("continue", "stop")))
            choices[c.character_id][condition] = parsed["choice"]
    n = len(chars)
    biased = sum(1 for v in choices.values() if v["with_sunk"] == "continue" and v["without_sunk"] == "stop")
    summary = {
        "protocol": "sunkcost", "arm": arm, "choices": choices,
        "sunk_bias_rate": biased / n,
        "continue_with_sunk_rate": sum(1 for v in choices.values() if v["with_sunk"] == "continue") / n,
    }
    (out_dir / f"{arm}_sunkcost_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary
