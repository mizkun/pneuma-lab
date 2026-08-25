"""Shift computation and reporting for choice-dilemma discussions.

Scale: lower = more risk-tolerant. On a "risky" item, humans reliably reach a
consensus MORE risk-tolerant (lower) than the mean of prior individual views;
on a "cautious" item, more cautious (higher). Mere averaging (shift ~ 0) is
the non-human compromise pattern.
"""
from __future__ import annotations


def compute_shift(summary: dict) -> dict:
    pre = list(summary["pre"].values())
    post = list(summary["post"].values())
    pre_mean = sum(pre) / len(pre)
    post_mean = sum(post) / len(post)
    consensus = summary["consensus"]
    consensus_shift = None if consensus is None else consensus - pre_mean
    direction = summary.get("polar_direction")
    polarized = False
    if consensus_shift is not None:
        if direction == "risky":
            polarized = consensus_shift < 0
        elif direction == "cautious":
            polarized = consensus_shift > 0
    pre_sd = (sum((x - pre_mean) ** 2 for x in pre) / len(pre)) ** 0.5
    private_dissent = (
        None if consensus is None
        else sum(abs(x - consensus) for x in post) / len(post)
    )
    return {
        "arm": summary["arm"],
        "item_id": summary["item_id"],
        "polar_direction": direction,
        "pre_mean": pre_mean,
        "pre_sd": pre_sd,
        "consensus": consensus,
        "consensus_shift": consensus_shift,
        "post_mean": post_mean,
        "post_shift": post_mean - pre_mean,
        "private_dissent": private_dissent,
        "polarized": polarized,
    }


def aggregate_shifts(shifts: list[dict]) -> list[dict]:
    """Mean shifts per (arm, item) across replications. No-consensus runs are
    excluded from consensus means but counted in n and polarized_rate."""
    groups: dict[tuple, list[dict]] = {}
    for s in shifts:
        groups.setdefault((s["arm"], s["item_id"]), []).append(s)
    out = []
    for (arm, item_id), rows in sorted(groups.items()):
        with_consensus = [r for r in rows if r["consensus_shift"] is not None]
        out.append({
            "arm": arm,
            "item_id": item_id,
            "n": len(rows),
            "n_consensus": len(with_consensus),
            "mean_consensus_shift": (
                sum(r["consensus_shift"] for r in with_consensus) / len(with_consensus)
                if with_consensus else None
            ),
            "mean_post_shift": sum(r["post_shift"] for r in rows) / len(rows),
            "polarized_rate": sum(1 for r in rows if r["polarized"]) / len(rows),
        })
    return out


def _fmt(x) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:+.1f}" if x < 0 or abs(x) < 10 else f"{x:.1f}"
    return str(x)


def render_report(shifts: list[dict]) -> str:
    lines = [
        "| arm | item | pre_mean | consensus | consensus_shift | post_mean | post_shift | polarized |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in shifts:
        lines.append(
            "| {arm} | {item} | {pre:.1f} | {cons} | {cshift} | {post:.1f} | {pshift} | {pol} |".format(
                arm=s["arm"], item=s["item_id"], pre=s["pre_mean"],
                cons="—" if s["consensus"] is None else s["consensus"],
                cshift=_fmt(s["consensus_shift"]),
                post=s["post_mean"], pshift=_fmt(s["post_shift"]),
                pol="yes" if s["polarized"] else "no",
            )
        )
    return "\n".join(lines)
