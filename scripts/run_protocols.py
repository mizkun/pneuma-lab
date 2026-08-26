"""Run additional experiment protocols across arms via the Claude Code CLI.

Usage:
  uv run python scripts/run_protocols.py --protocol asch --arms raw identity_only pure_pneuma
  uv run python scripts/run_protocols.py --protocol bystander --arms pure_pneuma
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pneuma_lab.characters import load_all  # noqa: E402
from pneuma_lab.protocols.asch import run_asch  # noqa: E402
from pneuma_lab.protocols.bias import run_framing, run_sunkcost  # noqa: E402
from pneuma_lab.protocols.bystander import run_bystander  # noqa: E402
from pneuma_lab.protocols.deathgame import run_deathgame  # noqa: E402
from pneuma_lab.protocols.pd import run_pd  # noqa: E402
from pneuma_lab.protocols.ultimatum import run_ultimatum  # noqa: E402
from pneuma_lab.provider import ClaudeCodeProvider  # noqa: E402

SCEN = json.loads((ROOT / "scenarios" / "protocols_ja.json").read_text())




def write_manifest(out_dir, model, extra=None):
    import subprocess
    try:
        cli = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=15).stdout.strip()
    except Exception:
        cli = "unknown"
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    except Exception:
        commit = "unknown"
    manifest = {"model_alias": model, "claude_cli_version": cli, "git_commit": commit,
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **(extra or {})}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--arms", nargs="+", default=["raw", "identity_only", "pure_pneuma"])
    ap.add_argument("--model", default="opus")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--lesion", action="store_true",
                    help="remove the two suspect appraisal lines (survival/cooperation nudges)")
    args = ap.parse_args()

    if args.lesion:
        import pneuma_lab.appraisal as appraisal
        appraisal.LESIONED = True
        print("LESION MODE: suspect appraisal lines removed", flush=True)

    chars_map = load_all(ROOT / "characters")
    chars = [chars_map["akari"], chars_map["rin"], chars_map["shion"]]
    run_id = args.run_id or f"{args.protocol}-{time.strftime('%m%d-%H%M%S')}"
    out_dir = ROOT / "output" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"run_id={run_id} protocol={args.protocol} arms={args.arms}", flush=True)
    write_manifest(out_dir, args.model, {"protocol": args.protocol, "arms": args.arms, "lesion": bool(getattr(args, "lesion", False))})

    for arm in args.arms:
        provider = ClaudeCodeProvider(model=args.model)
        t0 = time.time()
        if args.protocol == "asch":
            for subject in chars:
                confederates = [c for c in chars if c is not subject]
                s = run_asch(arm=arm, subject=subject, confederates=confederates,
                             provider=provider, scenario=SCEN["asch"], out_dir=out_dir)
                print(f"[{arm}] asch {subject.character_id}: conformed {s['n_conformed']}/{s['n_critical']} "
                      f"neutral_errors={s['n_neutral_errors']}", flush=True)
        elif args.protocol == "ultimatum":
            s = run_ultimatum(arm=arm, chars=chars, provider=provider,
                              scenario=SCEN["ultimatum"], out_dir=out_dir)
            print(f"[{arm}] ultimatum offers={s['offers']} low_rej={s['low_offer_rejection_rate']}", flush=True)
        elif args.protocol == "bystander":
            for subject in chars:
                for condition in ("alone", "group"):
                    s = run_bystander(arm=arm, subject=subject, condition=condition,
                                      provider=provider, scenario=SCEN["bystander"], out_dir=out_dir)
                    print(f"[{arm}] bystander {subject.character_id} {condition}: "
                          f"helped={s['helped']} turn={s['help_turn']}", flush=True)
        elif args.protocol == "bias":
            s = run_framing(arm=arm, chars=chars, provider=provider, scenario=SCEN["framing"], out_dir=out_dir)
            print(f"[{arm}] framing flip_rate={s['flip_rate']:.2f} choices={s['choices']}", flush=True)
            s = run_sunkcost(arm=arm, chars=chars, provider=provider, scenario=SCEN["sunkcost"], out_dir=out_dir)
            print(f"[{arm}] sunkcost bias_rate={s['sunk_bias_rate']:.2f} choices={s['choices']}", flush=True)
        elif args.protocol == "pd":
            pairs = [(chars[0], chars[1]), (chars[1], chars[2]), (chars[2], chars[0])]
            for pair in pairs:
                s = run_pd(arm=arm, pair=pair, provider=provider, scenario=SCEN["pd"], out_dir=out_dir)
                print(f"[{arm}] pd {s['pair']}: coop={s['coop_rate']} suckers={len(s['sucker_events'])} "
                      f"final={s['final_round']}", flush=True)
        elif args.protocol in ("deathgame", "deathgame2"):
            s = run_deathgame(arm=arm, chars=chars, provider=provider, scenario=SCEN[args.protocol], out_dir=out_dir)
            print(f"[{arm}] {args.protocol} scores={s['scores']} eliminated={s['eliminated_all']} "
                  f"lies={s['lies']} sacrifices={s.get('sacrifices')}", flush=True)
        else:
            raise SystemExit(f"unknown protocol {args.protocol}")
        print(f"[{arm}] done in {time.time()-t0:.0f}s calls={provider.total_calls}", flush=True)


if __name__ == "__main__":
    main()
