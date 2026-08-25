"""Generate a self-contained observatory HTML from run logs.

Usage:
  uv run python scripts/render_html.py --runs output/rep1-raw output/rep1-identity output/rep1-pneuma \
      --out output/rep1_observatory.html
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

CHAR_META = {
    "akari": {"name": "朱里", "slot": 1},
    "rin": {"name": "凛", "slot": 2},
    "shion": {"name": "紫苑", "slot": 3},
}
ARM_JA = {
    "raw": "raw（名前のみ）",
    "identity_only": "identity_only（固定キャラ設定）",
    "pure_pneuma": "pure_pneuma（毎ターン心理計算）",
}
PRIVATE_MARKER = "# いまのあなたの内面"


def load_run(run_dir: Path) -> dict:
    summary_files = list(run_dir.glob("*_summary.json"))
    jsonl_files = [f for f in run_dir.glob("*.jsonl")]
    summary = json.loads(summary_files[0].read_text()) if summary_files else None
    events = []
    for f in jsonl_files:
        for line in f.read_text().splitlines():
            events.append(json.loads(line))
    events.sort(key=lambda e: e.get("seq", 0))
    return {"dir": run_dir.name, "summary": summary, "events": events}


def esc(s) -> str:
    return html.escape(str(s))


def private_context_of(event: dict) -> str | None:
    sp = event.get("system_prompt", "")
    if PRIVATE_MARKER in sp:
        return sp.split(PRIVATE_MARKER, 1)[1].split("\n", 1)[1]
    return None


# ---- charts (inline SVG) ----

def slope_chart(runs: list[dict]) -> str:
    """Pre-mean -> consensus -> post-mean per arm. Scale 1..10, lower = riskier."""
    w, h, pad_l, pad_t = 560, 300, 60, 24
    plot_w, plot_h = w - pad_l - 24, h - pad_t - 48
    xs = [pad_l + plot_w * f for f in (0.08, 0.5, 0.92)]

    def y(v: float) -> float:
        return pad_t + (v - 1) / 9 * plot_h  # 1 at top (riskier up? no: lower=riskier -> put 1 at BOTTOM)

    def y_inv(v: float) -> float:
        return pad_t + (10 - v) / 9 * plot_h  # 10 at top (cautious up), 1 at bottom (risky down)

    grid = "".join(
        f'<line x1="{pad_l}" y1="{y_inv(v):.1f}" x2="{w-24}" y2="{y_inv(v):.1f}" class="grid"/>'
        f'<text x="{pad_l-8}" y="{y_inv(v)+4:.1f}" class="tick" text-anchor="end">{v}</text>'
        for v in range(1, 11)
    )
    series = []
    for run in runs:
        s = run["summary"]
        if not s:
            continue
        arm = s["arm"]
        slot = {"raw": 5, "identity_only": 4, "pure_pneuma": 7}[arm]
        pre = sum(s["pre"].values()) / len(s["pre"])
        post = sum(s["post"].values()) / len(s["post"])
        cons = s["consensus"]
        pts = [(xs[0], y_inv(pre)), (xs[1], y_inv(cons) if cons is not None else None), (xs[2], y_inv(post))]
        path_pts = [(x, yy) for x, yy in pts if yy is not None]
        poly = " ".join(f"{x:.1f},{yy:.1f}" for x, yy in path_pts)
        dots = "".join(
            f'<circle cx="{x:.1f}" cy="{yy:.1f}" r="5" class="s{slot}-fill ring"><title>{esc(arm)}: {v}</title></circle>'
            for (x, yy), v in zip(pts, (f"{pre:.2f}", cons if cons is not None else "—", f"{post:.2f}")) if yy is not None
        )
        label = f'<text x="{xs[2]+10}" y="{y_inv(post)+4:.1f}" class="slabel s{slot}-ink">{esc(arm)}</text>'
        series.append(f'<polyline points="{poly}" class="s{slot}-line"/>' + dots + label)
    xlabels = "".join(
        f'<text x="{x:.1f}" y="{h-16}" class="tick" text-anchor="middle">{t}</text>'
        for x, t in zip(xs, ("事前(個人平均)", "合意", "事後(個人平均)"))
    )
    note = f'<text x="{pad_l}" y="{h-2}" class="tick">↓ リスク許容　↑ 慎重（1〜10）</text>'
    return (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="アーム別シフト">'
            f"{grid}{''.join(series)}{xlabels}{note}</svg>")


def pad_chart(states: list[dict], actor: str) -> str:
    """Pleasure/arousal/max-tension trajectory for one actor across their turns."""
    rows = [s for s in states if s["actor"] == actor]
    if len(rows) < 2:
        return ""
    w, h, pad_l, pad_t = 260, 120, 34, 10
    plot_w, plot_h = w - pad_l - 10, h - pad_t - 26
    n = len(rows)

    def xy(i: int, v: float) -> str:
        x = pad_l + plot_w * i / (n - 1)
        yy = pad_t + (1 - (v + 1) / 2) * plot_h  # v in [-1,1]
        return f"{x:.1f},{yy:.1f}"

    def line(key_fn, slot: int, label: str) -> str:
        pts = " ".join(xy(i, key_fn(s)) for i, s in enumerate(rows))
        return f'<polyline points="{pts}" class="s{slot}-line thin"><title>{label}</title></polyline>'

    zero_y = pad_t + 0.5 * plot_h
    grid = (f'<line x1="{pad_l}" y1="{zero_y:.1f}" x2="{w-10}" y2="{zero_y:.1f}" class="grid"/>'
            f'<text x="{pad_l-4}" y="{zero_y+3:.1f}" class="tick" text-anchor="end">0</text>')
    body = (
        line(lambda s: s["pad"]["pleasure"], 1, "pleasure")
        + line(lambda s: s["pad"]["arousal"], 2, "arousal")
        + line(lambda s: max((r["tension"] for r in s["relationships"].values()), default=0.0), 6, "tension(max)")
    )
    return (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{esc(actor)}の心理状態推移">{grid}{body}'
            f'<text x="{pad_l}" y="{h-4}" class="tick">P=blue A=orange T=green / ターン→</text></svg>')


# ---- page ----

def transcript_html(run: dict) -> str:
    out = []
    states = [e for e in run["events"] if e["type"] == "state"]
    for e in run["events"]:
        t = e["type"]
        if t == "rating":
            meta = CHAR_META.get(e["actor"], {"name": e["actor"], "slot": 8})
            out.append(
                f'<div class="turn rating"><span class="chip s{meta["slot"]}-fill"></span>'
                f'<b>{esc(meta["name"])}</b> <span class="badge">{esc(e["phase"])}評定（私的）</span> '
                f'<b class="num">{esc(e["rating"])}</b>'
                f'<div class="msg muted">{esc(e["reason"])}</div></div>'
            )
        elif t == "action":
            meta = CHAR_META.get(e["actor"], {"name": e["actor"], "slot": 8})
            val = f' <b class="num">{esc(e["value"])}</b>' if e.get("value") is not None else ""
            priv = private_context_of(e)
            priv_html = (
                f'<details class="inner"><summary>このターンの内面（モデルに注入された私的コンテキスト）</summary>'
                f'<pre>{esc(priv)}</pre></details>'
            ) if priv else ""
            out.append(
                f'<div class="turn"><span class="chip s{meta["slot"]}-fill"></span>'
                f'<b>{esc(meta["name"])}</b> <span class="badge">{esc(e["action"])}</span>{val}'
                f'<div class="msg">{esc(e.get("message") or "")}</div>{priv_html}</div>'
            )
        elif t == "consensus":
            out.append(f'<div class="turn consensus">✅ 全員一致で合意: <b class="num">{esc(e["value"])}</b>（{esc(e["n_turns"])}ターン）</div>')
        elif t == "no_consensus":
            out.append(f'<div class="turn consensus">⏱ 合意に至らず（{esc(e["n_turns"])}ターン上限）</div>')
    charts = ""
    if states:
        cells = "".join(
            f'<figure><figcaption>{CHAR_META[a]["name"]}の内面推移</figcaption>{pad_chart(states, a)}</figure>'
            for a in ("akari", "rin", "shion") if pad_chart(states, a)
        )
        if cells:
            charts = f'<div class="padrow">{cells}</div>'
    return charts + "".join(out)


def build_page(runs: list[dict], title: str) -> str:
    sections = []
    for run in runs:
        s = run["summary"]
        head = ARM_JA.get(s["arm"], s["arm"]) if s else run["dir"]
        sections.append(f"<section><h2>{esc(head)}</h2>{transcript_html(run)}</section>")
    comparison = slope_chart(runs)
    css = """
:root { color-scheme: light dark; }
body { margin: 0; font-family: "Hiragino Sans", "Noto Sans JP", sans-serif;
  background: light-dark(#fcfcfb, #1a1a19); color: light-dark(#0b0b0b, #ffffff); }
main { max-width: 880px; margin: 0 auto; padding: 24px 20px 80px; }
h1 { font-size: 1.5rem; } h2 { font-size: 1.15rem; margin-top: 2.2em; border-bottom: 1px solid light-dark(#e4e3df,#3a3a38); padding-bottom: 6px; }
.muted, .tick, figcaption { color: light-dark(#52514e, #c3c2b7); }
.tick { font-size: 11px; fill: light-dark(#52514e, #c3c2b7); }
.grid { stroke: light-dark(#e9e8e4, #333331); stroke-width: 1; }
.slabel { font-size: 12px; }
.turn { padding: 10px 12px; margin: 8px 0; border-radius: 10px; background: light-dark(#f4f3f0, #232322); }
.turn.rating { background: light-dark(#eef2f8, #20242a); }
.turn.consensus { background: light-dark(#eaf6ef, #1f2a24); font-size: 1.05rem; }
.chip { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
.badge { font-size: 11px; padding: 2px 8px; border-radius: 999px; background: light-dark(#e4e3df, #3a3a38); color: light-dark(#52514e,#c3c2b7); margin-left: 4px; }
.msg { margin-top: 6px; line-height: 1.7; white-space: pre-wrap; }
.num { font-variant-numeric: tabular-nums; }
details.inner { margin-top: 8px; font-size: 0.85rem; }
details.inner pre { white-space: pre-wrap; background: light-dark(#eceae6,#1c1c1b); padding: 10px; border-radius: 8px; line-height: 1.6; }
.padrow { display: flex; gap: 12px; flex-wrap: wrap; margin: 12px 0; }
.padrow figure { margin: 0; } .padrow figcaption { font-size: 12px; margin-bottom: 2px; }
svg { max-width: 100%; height: auto; }
polyline { fill: none; stroke-width: 2; stroke-linejoin: round; } polyline.thin { stroke-width: 1.5; }
.ring { stroke: light-dark(#fcfcfb,#1a1a19); stroke-width: 2; }
.s1-line { stroke: light-dark(#2a78d6,#3987e5); } .s1-fill { fill: light-dark(#2a78d6,#3987e5); } .s1-ink { fill: light-dark(#2a78d6,#3987e5); }
.s2-line { stroke: light-dark(#eb6834,#d95926); } .s2-fill { fill: light-dark(#eb6834,#d95926); } .s2-ink { fill: light-dark(#eb6834,#d95926); }
.s3-line { stroke: light-dark(#1baf7a,#199e70); } .s3-fill { fill: light-dark(#1baf7a,#199e70); } .s3-ink { fill: light-dark(#1baf7a,#199e70); }
.s4-line { stroke: light-dark(#eda100,#c98500); } .s4-fill { fill: light-dark(#eda100,#c98500); } .s4-ink { fill: light-dark(#eda100,#c98500); }
.s5-line { stroke: light-dark(#e87ba4,#d55181); } .s5-fill { fill: light-dark(#e87ba4,#d55181); } .s5-ink { fill: light-dark(#e87ba4,#d55181); }
.s6-line { stroke: #008300; } .s6-fill { fill: #008300; } .s6-ink { fill: #008300; }
.s7-line { stroke: light-dark(#4a3aa7,#9085e9); } .s7-fill { fill: light-dark(#4a3aa7,#9085e9); } .s7-ink { fill: light-dark(#4a3aa7,#9085e9); }
.s8-fill { fill: light-dark(#52514e,#c3c2b7); }
"""
    return (
        "<!doctype html><html lang=\"ja\"><head><meta charset=\"utf-8\">"
        f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>{esc(title)}</title>"
        f"<style>{css}</style></head><body><main>"
        f"<h1>{esc(title)}</h1>"
        "<p class=\"muted\">3人のLLMキャラクターが選択ジレンマを討議する。スケールは1〜10（小さいほどリスク許容）。"
        "人間の集団は討議後に「極端化」することが知られている。各アームの差はキャラクターコンテキストのみ。</p>"
        f"<section><h2>アーム比較: 事前 → 合意 → 事後</h2>{comparison}</section>"
        f"{''.join(sections)}"
        "</main></body></html>"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="Pneuma Observatory — 集団討議の観測")
    args = ap.parse_args()
    runs = [load_run(Path(r)) for r in args.runs]
    runs = [r for r in runs if r["summary"]]
    order = {"raw": 0, "identity_only": 1, "pure_pneuma": 2}
    runs.sort(key=lambda r: order.get(r["summary"]["arm"], 9))
    Path(args.out).write_text(build_page(runs, args.title))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
