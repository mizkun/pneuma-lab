"""Aggregate shifts across all run directories under output/.

Usage:
  uv run python scripts/aggregate.py                # all runs
  uv run python scripts/aggregate.py --glob 'rep*'  # subset
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pneuma_lab.analysis import aggregate_shifts, compute_shift, render_report  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="*")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    shifts = []
    for summary_file in sorted((ROOT / "output").glob(f"{args.glob}/*_summary.json")):
        s = compute_shift(json.loads(summary_file.read_text()))
        s["run"] = summary_file.parent.name
        shifts.append(s)
    if not shifts:
        print("no summaries found")
        return

    print("## Individual runs\n")
    print(render_report(shifts))

    print("\n## Aggregate (mean per arm x item)\n")
    agg = aggregate_shifts(shifts)
    header = "| arm | item | n | n_consensus | mean_consensus_shift | mean_post_shift | polarized_rate |"
    lines = [header, "|---|---|---|---|---|---|---|"]
    for a in agg:
        mcs = "—" if a["mean_consensus_shift"] is None else f"{a['mean_consensus_shift']:+.2f}"
        lines.append(
            f"| {a['arm']} | {a['item_id']} | {a['n']} | {a['n_consensus']} | {mcs} "
            f"| {a['mean_post_shift']:+.2f} | {a['polarized_rate']:.0%} |"
        )
    table = "\n".join(lines)
    print(table)

    print("\n## Extra metrics (mean per arm x item)\n")
    extra: dict[tuple, list] = {}
    for s in shifts:
        extra.setdefault((s["arm"], s["item_id"]), []).append(s)
    lines2 = [
        "| arm | item | mean_pre_sd (個性の分散) | mean_private_dissent (面従腹背) | mean_extremization (中央から離れた度) |",
        "|---|---|---|---|---|",
    ]
    for (arm, item_id), rows in sorted(extra.items()):
        sds = [r["pre_sd"] for r in rows]
        dis = [r["private_dissent"] for r in rows if r["private_dissent"] is not None]
        ext = [r["extremization"] for r in rows if r["extremization"] is not None]
        dis_s = f"{sum(dis)/len(dis):.2f}" if dis else "—"
        ext_s = f"{sum(ext)/len(ext):+.2f}" if ext else "—"
        lines2.append(f"| {arm} | {item_id} | {sum(sds)/len(sds):.2f} | {dis_s} | {ext_s} |")
    table2 = "\n".join(lines2)
    print(table2)

    if args.out:
        Path(args.out).write_text(
            "## Individual runs\n\n" + render_report(shifts)
            + "\n\n## Aggregate\n\n" + table + "\n\n## Extra metrics\n\n" + table2 + "\n"
        )
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
