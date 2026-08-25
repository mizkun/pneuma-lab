"""Run the choice-dilemma discussion for one or more arms via the Claude Code CLI.

Usage:
  uv run python scripts/run_experiment.py --item career --arms raw identity_only pure_pneuma
  uv run python scripts/run_experiment.py --item career --arms pure_pneuma --run-id smoke --max-turns 4
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pneuma_lab.analysis import compute_shift, render_report  # noqa: E402
from pneuma_lab.characters import load_all  # noqa: E402
from pneuma_lab.experiment import run_condition  # noqa: E402
from pneuma_lab.provider import ClaudeCodeProvider  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--item", default="career")
    ap.add_argument("--arms", nargs="+", default=["raw", "identity_only", "pure_pneuma"])
    ap.add_argument("--max-turns", type=int, default=15)
    ap.add_argument("--model", default="opus")
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()

    items = json.loads((ROOT / "scenarios" / "cdq_items_ja.json").read_text())["items"]
    item = next(i for i in items if i["item_id"] == args.item)
    chars_map = load_all(ROOT / "characters")
    chars = [chars_map["akari"], chars_map["rin"], chars_map["shion"]]

    run_id = args.run_id or time.strftime("%Y%m%d-%H%M%S")
    out_dir = ROOT / "output" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"run_id={run_id} item={args.item} arms={args.arms} model={args.model}", flush=True)

    shifts = []
    for arm in args.arms:
        provider = ClaudeCodeProvider(model=args.model)
        t0 = time.time()
        print(f"[{arm}] start", flush=True)
        summary = run_condition(arm=arm, item=item, chars=chars, provider=provider,
                                out_dir=out_dir, max_turns=args.max_turns)
        dt = time.time() - t0
        s = compute_shift(summary)
        shifts.append(s)
        print(f"[{arm}] done in {dt:.0f}s calls={provider.total_calls} "
              f"pre={summary['pre']} consensus={summary['consensus']} post={summary['post']}", flush=True)

    report = render_report(shifts)
    (out_dir / "report.md").write_text(report)
    print("\n" + report, flush=True)


if __name__ == "__main__":
    main()
