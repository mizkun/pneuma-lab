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
    return {
        "arm": summary["arm"],
        "item_id": summary["item_id"],
        "polar_direction": direction,
        "pre_mean": pre_mean,
        "consensus": consensus,
        "consensus_shift": consensus_shift,
        "post_mean": post_mean,
        "post_shift": post_mean - pre_mean,
        "polarized": polarized,
    }


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
