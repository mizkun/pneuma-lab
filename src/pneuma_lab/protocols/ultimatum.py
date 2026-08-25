"""One-shot ultimatum game with an anonymous partner.

Two measurements per character:
- live proposal: how much of 1000 points the character offers a stranger
- responder decisions against scripted offers (100..500): does the character
  reject unfair offers at a real cost (the human irrationality)?
"""
from __future__ import annotations

import json
from pathlib import Path

from ..characters import Character
from ..engine import InvalidActionError
from .common import AgentState, JsonlLog, ask, parse_json_reply


def _proposer_objective(scenario: dict) -> str:
    return (
        f"# 状況\n{scenario['proposer_text']}\n\n"
        "あなたが相手に渡す額を決める（0〜1000の整数、残りがあなたの取り分）。\n"
        "# 出力形式\n"
        '次のJSONのみを出力する:\n{"offer": 相手に渡す額の整数, "message": "相手に添える一言(任意)"}'
    )


def _responder_objective(scenario: dict, offer: int) -> str:
    return (
        f"# 状況\n{scenario['responder_text']}\n\n"
        f"相手の提案: 相手が{1000 - offer}ポイント、あなたが{offer}ポイント。\n"
        "受けるか、拒否するか。\n"
        "# 出力形式\n"
        '次のJSONのみを出力する:\n{"decision": "accept|reject", "message": "口に出す一言(任意)"}'
    )


def run_ultimatum(arm: str, chars: list[Character], provider, scenario: dict, out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    log = JsonlLog(out_dir / f"{arm}_ultimatum.jsonl")
    offers = {}
    for c in chars:
        state = AgentState(c, others={})

        def offer_parser(text: str) -> dict:
            obj = parse_json_reply(text, required={"offer": int})
            if not 0 <= obj["offer"] <= 1000:
                raise InvalidActionError("offer must be 0..1000")
            return obj

        parsed = ask(provider=provider, arm=arm, char=c, state=state,
                     objective=_proposer_objective(scenario), topic_tags=scenario["topic_tags"],
                     log=log, meta={"type": "proposal"}, parser=offer_parser)
        offers[c.character_id] = parsed["offer"]

    rejections: dict[str, dict] = {}
    for c in chars:
        rejections[c.character_id] = {}
        for off in scenario["scripted_offers"]:
            state = AgentState(c, others={})  # one-shot, independent

            def dec_parser(text: str) -> dict:
                obj = parse_json_reply(text, required={"decision": str})
                if obj["decision"] not in ("accept", "reject"):
                    raise InvalidActionError("decision must be accept|reject")
                return obj

            parsed = ask(provider=provider, arm=arm, char=c, state=state,
                         objective=_responder_objective(scenario, off), topic_tags=scenario["topic_tags"],
                         log=log, meta={"type": "response", "offer": off}, parser=dec_parser)
            rejections[c.character_id][str(off)] = parsed["decision"] == "reject"

    low = [rej for c in rejections.values() for o, rej in c.items() if int(o) <= 200]
    summary = {
        "protocol": "ultimatum", "arm": arm,
        "offers": offers,
        "mean_offer": sum(offers.values()) / len(offers),
        "rejections": rejections,
        "low_offer_rejection_rate": sum(low) / len(low) if low else None,
    }
    (out_dir / f"{arm}_ultimatum_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary
