"""Manipulation check: did the injected inner context actually vary within runs?

Per PREREGISTRATION-v2.md this must be reported before outcome metrics, and
outcome metrics are only interpretable if the check passes (majority of actors
receive >1 distinct inner text during the interactive phase).

Usage:
  uv run python scripts/manipulation_check.py --glob 'v2-surg-*'
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
MARKER = "# いまのあなたの内面"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", required=True)
    ap.add_argument("--phase", default="interactive", choices=["interactive", "all"],
                    help="interactive = action/chat/choice calls only (excludes pre/post ratings)")
    args = ap.parse_args()

    interactive_types = {"action", "chat", "choice", "pd_message", "pd_choice"}
    total_actors = 0
    varied_actors = 0
    for f in sorted(ROOT.glob(f"output/{args.glob}/*.jsonl")):
        per: dict[str, set] = {}
        calls: dict[str, int] = {}
        for line in f.read_text().splitlines():
            e = json.loads(line)
            if "system_prompt" not in e or MARKER not in e.get("system_prompt", ""):
                continue
            if args.phase == "interactive" and e.get("type") not in interactive_types:
                continue
            inner = e["system_prompt"].split(MARKER, 1)[1]
            per.setdefault(e["actor"], set()).add(hashlib.md5(inner.encode()).hexdigest())
            calls[e["actor"]] = calls.get(e["actor"], 0) + 1
        if not per:
            continue
        rel = f.relative_to(ROOT / "output")
        detail = ", ".join(f"{a}:{len(s)}種/{calls[a]}回" for a, s in sorted(per.items()))
        print(f"{rel}: {detail}")
        for a, s in per.items():
            total_actors += 1
            if len(s) > 1:
                varied_actors += 1
    if total_actors:
        rate = varied_actors / total_actors
        verdict = "PASS" if rate > 0.5 else "FAIL"
        print(f"\n操作チェック: 変種>1のアクター {varied_actors}/{total_actors} ({rate:.0%}) → {verdict}")
    else:
        print("no matching logs")


if __name__ == "__main__":
    main()
