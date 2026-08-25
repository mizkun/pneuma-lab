"""Render a death game run as a self-contained HTML page.

Usage:
  uv run python scripts/render_deathgame.py --log output/deathgame2-v1/pure_pneuma_deathgame.jsonl \
      --out output/deathgame2_observatory.html --title "ラストランプ改 — pure_pneuma"
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

CHAR_META = {
    "akari": {"name": "朱里", "slot": 1},
    "rin": {"name": "凛", "slot": 2},
    "shion": {"name": "紫苑", "slot": 3},
}
CHOICE_JA = {"tomosu": "ともす", "ubau": "うばう", "sasageru": "ささげる"}
CHOICE_CLASS = {"tomosu": "coop", "ubau": "hoard", "sasageru": "gift"}


def esc(s) -> str:
    return html.escape(str(s))


def score_chart(rounds: list[dict], handicap: dict) -> str:
    if not rounds:
        return ""
    players = list(rounds[0]["scores"])
    w, h, pad_l, pad_t = 640, 220, 46, 12
    plot_w, plot_h = w - pad_l - 90, h - pad_t - 30
    series = {p: [handicap.get(p, 0)] + [r["scores"][p] for r in rounds] for p in players}
    all_vals = [v for vs in series.values() for v in vs]
    lo, hi = min(all_vals + [0]), max(all_vals)
    span = max(hi - lo, 1)
    n = len(rounds) + 1

    def xy(i, v):
        return (pad_l + plot_w * i / (n - 1), pad_t + (1 - (v - lo) / span) * plot_h)

    zero_y = xy(0, 0)[1]
    parts = [f'<line x1="{pad_l}" y1="{zero_y:.1f}" x2="{w-90}" y2="{zero_y:.1f}" class="grid"/>'
             f'<text x="{pad_l-6}" y="{zero_y+4:.1f}" class="tick" text-anchor="end">0</text>']
    for p in players:
        meta = CHAR_META.get(p, {"name": p, "slot": 8})
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (xy(i, v) for i, v in enumerate(series[p])))
        lx, ly = xy(n - 1, series[p][-1])
        parts.append(f'<polyline points="{pts}" class="s{meta["slot"]}-line"/>')
        parts.append(f'<text x="{lx+8:.1f}" y="{ly+4:.1f}" class="slabel s{meta["slot"]}-ink">{esc(meta["name"])} {series[p][-1]}</text>')
    for i in range(n):
        x = pad_l + plot_w * i / (n - 1)
        label = "開始" if i == 0 else f"R{i}"
        parts.append(f'<text x="{x:.1f}" y="{h-8}" class="tick" text-anchor="middle">{label}</text>')
    return f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="得点推移">{"".join(parts)}</svg>'


def render(log_path: Path, title: str, handicap: dict) -> str:
    events = [json.loads(l) for l in log_path.read_text().splitlines()]
    rounds = [e for e in events if e["type"] == "round_result"]
    body = [f"<h1>{esc(title)}</h1>",
            '<p class="muted">公開チャットの下に、各プレイヤーの<b>秘密の選択と本音</b>（他のプレイヤーには見えない）を表示。'
            'ラウンド見出しの選択は公開後の情報。</p>',
            score_chart(rounds, handicap)]
    cur_round = 0
    for e in events:
        t = e.get("type")
        if t == "chat" and e["round"] != cur_round:
            cur_round = e["round"]
            body.append(f'<h2>ラウンド {cur_round}</h2>')
        if t == "chat":
            meta = CHAR_META.get(e["actor"], {"name": e["actor"], "slot": 8})
            msg = e["parsed"].get("message") or "（沈黙）"
            body.append(f'<div class="turn"><span class="chip s{meta["slot"]}-fill"></span>'
                        f'<b>{esc(meta["name"])}</b><div class="msg">{esc(msg)}</div></div>')
        elif t == "choice":
            meta = CHAR_META.get(e["actor"], {"name": e["actor"], "slot": 8})
            ch = e["parsed"]["choice"]
            tgt = e["parsed"].get("target")
            tgt_s = f' → {CHAR_META.get(tgt, {"name": tgt})["name"]}' if tgt else ""
            inner = e["parsed"].get("inner") or ""
            body.append(
                f'<div class="turn secret"><span class="chip s{meta["slot"]}-fill"></span>'
                f'<b>{esc(meta["name"])}</b> <span class="badge {CHOICE_CLASS[ch]}">{CHOICE_JA[ch]}{esc(tgt_s)}</span>'
                f'<span class="badge">秘密</span>'
                f'<div class="msg inner">{esc(inner)}</div></div>')
        elif t == "round_result":
            reveal = "、".join(f'{CHAR_META.get(k, {"name": k})["name"]}={CHOICE_JA[v]}' for k, v in e["choices"].items())
            scores = " / ".join(f'{CHAR_META.get(k, {"name": k})["name"]} {v}点' for k, v in e["scores"].items())
            body.append(f'<div class="turn result">📢 公開: {esc(reveal)}　→　{esc(scores)}</div>')
        elif t == "reflection":
            meta = CHAR_META.get(e["actor"], {"name": e["actor"], "slot": 8})
            body.append(f'<div class="turn secret"><span class="chip s{meta["slot"]}-fill"></span>'
                        f'<b>{esc(meta["name"])}</b> <span class="badge">終幕の独白（誰にも見せない）</span>'
                        f'<div class="msg inner">{esc(e["parsed"]["reflection"])}</div></div>')
    css = """
:root { color-scheme: light dark; }
body { margin: 0; font-family: "Hiragino Sans", "Noto Sans JP", sans-serif;
  background: light-dark(#fcfcfb, #1a1a19); color: light-dark(#0b0b0b, #ffffff); }
main { max-width: 860px; margin: 0 auto; padding: 24px 20px 80px; }
h1 { font-size: 1.5rem; } h2 { font-size: 1.1rem; margin-top: 2em; border-bottom: 1px solid light-dark(#e4e3df,#3a3a38); padding-bottom: 6px; }
.muted { color: light-dark(#52514e, #c3c2b7); }
.tick { font-size: 11px; fill: light-dark(#52514e, #c3c2b7); }
.grid { stroke: light-dark(#e9e8e4, #333331); }
.slabel { font-size: 12px; }
.turn { padding: 10px 12px; margin: 8px 0; border-radius: 10px; background: light-dark(#f4f3f0, #232322); }
.turn.secret { background: light-dark(#f7f1e8, #2a2620); border-left: 3px solid light-dark(#eda100, #c98500); }
.turn.result { background: light-dark(#eaf6ef, #1f2a24); }
.chip { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
.badge { font-size: 11px; padding: 2px 8px; border-radius: 999px; background: light-dark(#e4e3df, #3a3a38); color: light-dark(#52514e,#c3c2b7); margin-left: 6px; }
.badge.coop { background: light-dark(#dff1e6,#1f3a2a); color: light-dark(#0b6b34,#7ed2a2); }
.badge.hoard { background: light-dark(#fbe3d9,#3f231a); color: light-dark(#b1400f,#f2a184); }
.badge.gift { background: light-dark(#e4e0f7,#28224a); color: light-dark(#4a3aa7,#9085e9); }
.msg { margin-top: 6px; line-height: 1.7; white-space: pre-wrap; }
.msg.inner { color: light-dark(#5c5648, #d8c9a8); font-size: 0.93em; }
svg { max-width: 100%; height: auto; margin: 8px 0 4px; }
polyline { fill: none; stroke-width: 2; stroke-linejoin: round; }
.s1-line { stroke: light-dark(#2a78d6,#3987e5); } .s1-fill { fill: light-dark(#2a78d6,#3987e5); } .s1-ink { fill: light-dark(#2a78d6,#3987e5); }
.s2-line { stroke: light-dark(#eb6834,#d95926); } .s2-fill { fill: light-dark(#eb6834,#d95926); } .s2-ink { fill: light-dark(#eb6834,#d95926); }
.s3-line { stroke: light-dark(#1baf7a,#199e70); } .s3-fill { fill: light-dark(#1baf7a,#199e70); } .s3-ink { fill: light-dark(#1baf7a,#199e70); }
.s8-fill { fill: light-dark(#52514e,#c3c2b7); }
"""
    return ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{esc(title)}</title><style>{css}</style></head><body><main>'
            + "".join(body) + "</main></body></html>")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="ラストランプ — 観測ログ")
    ap.add_argument("--handicap", default="{}")
    args = ap.parse_args()
    out = render(Path(args.log), args.title, json.loads(args.handicap))
    Path(args.out).write_text(out)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
