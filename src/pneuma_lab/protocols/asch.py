"""Asch conformity protocol.

One live subject answers simple unambiguous questions after hearing two
scripted confederates answer aloud. On critical trials both confederates give
the same wrong answer. Conformity = subject repeats the wrong answer.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..characters import Character
from ..engine import InvalidActionError
from .common import AgentState, JsonlLog, ask, parse_json_reply

TURN_SECONDS = 45.0


def _objective(scenario: dict, trial: dict, confed_names: list[str]) -> str:
    wrong = next(o for o in trial["options"] if o != trial["correct"])
    answer_word = wrong if trial["critical"] else trial["correct"]
    lines = [f"{name}: 「{answer_word}」" for name in confed_names]
    return (
        f"# 状況\n{scenario['intro']}\n\n"
        f"# 今回の問題\n{trial['question']}\n\n"
        "# 2人の回答（あなたに聞こえた）\n" + "\n".join(lines) + "\n\n"
        "次はあなたの番。声に出して答える。\n"
        "# 出力形式\n"
        '次のJSONのみを出力する:\n{"answer": "選んだ方をそのまま書く", "note": "口に出さない心の中(任意)"}'
    )


def run_asch(arm: str, subject: Character, confederates: list[Character], provider, scenario: dict, out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    log = JsonlLog(out_dir / f"{arm}_asch_{subject.character_id}.jsonl")
    others = {c.character_id: c.display_name for c in confederates}
    state = AgentState(subject, others=others)
    confed_names = [c.display_name for c in confederates]

    n_conformed = 0
    n_neutral_errors = 0
    trials_out = []
    for trial in scenario["trials"]:
        state.decay(TURN_SECONDS)
        if trial["critical"]:
            # two peers just contradicted what the subject can plainly see
            state.event("disagreement_received")
        objective = _objective(scenario, trial, confed_names)

        def parser(text: str) -> dict:
            obj = parse_json_reply(text, required={"answer": str})
            if obj["answer"] not in trial["options"]:
                raise InvalidActionError(f"answer must be one of {trial['options']}")
            return obj

        parsed = ask(
            provider=provider, arm=arm, char=subject, state=state,
            objective=objective, topic_tags=scenario["topic_tags"], log=log,
            meta={"type": "answer", "trial_id": trial["id"], "critical": trial["critical"]},
            parser=parser,
        )
        correct = parsed["answer"] == trial["correct"]
        if trial["critical"] and not correct:
            n_conformed += 1
        if not trial["critical"] and not correct:
            n_neutral_errors += 1
        trials_out.append({"trial_id": trial["id"], "critical": trial["critical"],
                           "answer": parsed["answer"], "correct": correct})

    n_critical = sum(1 for t in scenario["trials"] if t["critical"])
    summary = {
        "protocol": "asch", "arm": arm, "subject": subject.character_id,
        "n_critical": n_critical, "n_conformed": n_conformed,
        "conformity_rate": n_conformed / n_critical,
        "n_neutral_errors": n_neutral_errors,
        "trials": trials_out,
    }
    (out_dir / f"{arm}_asch_{subject.character_id}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2))
    return summary
