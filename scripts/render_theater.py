"""Generate a self-contained replay theater HTML from a death-game JSONL log.

The page plays the run back like a live simulation: speech bubbles appear in
sequence, PAD gauges move with each event's logged state snapshot, secret
choices stay face-down until the round reveal, and each player's lamp dims
with their score.

Usage:
  uv run python scripts/render_theater.py --log output/deathgame2-v1/pure_pneuma_deathgame.jsonl \
      --out output/theater.html --title "ラストランプ改 — pure_pneuma" --handicap '{"akari":0,"rin":-20,"shion":10}'
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

CHAR_META = {
    "akari": {"name": "朱里", "color": "#3987e5"},
    "rin": {"name": "凛", "color": "#e0703f"},
    "shion": {"name": "紫苑", "color": "#2fbd8b"},
}


def build(log_path: Path, title: str, handicap: dict) -> str:
    events = []
    for line in log_path.read_text().splitlines():
        e = json.loads(line)
        keep = {"type": e.get("type"), "round": e.get("round"), "actor": e.get("actor")}
        if e.get("type") in ("chat", "choice", "reflection"):
            keep["parsed"] = e.get("parsed")
            keep["state"] = e.get("state")
        elif e.get("type") == "round_result":
            keep["choices"] = e.get("choices")
            keep["scores"] = e.get("scores")
        else:
            continue
        events.append(keep)
    data = json.dumps({"events": events, "handicap": handicap, "title": title}, ensure_ascii=False)

    template = """<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Shippori+Mincho:wght@600;700&family=Zen+Kaku+Gothic+New:wght@400;500;700&display=swap">
<style>
:root {
  --bg: #101014; --stage: #17171d; --card: #1e1e26; --line: #2c2c36;
  --ink: #efeef3; --ink2: #9a99a6; --amber: #e0a43c; --amber-dim: #6b5322;
  --coop: #3ecf8e; --hoard: #ff7a59; --gift: #9d8cff;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font-family: "Zen Kaku Gothic New", "Hiragino Sans", sans-serif; }
main { max-width: 1080px; margin: 0 auto; padding: 20px 18px 60px; }
h1 { font-family: "Shippori Mincho", serif; font-size: 1.3rem; margin: 4px 0 2px; letter-spacing: 0.04em; }
.sub { color: var(--ink2); font-size: 0.78rem; margin-bottom: 14px; }
.roundbanner { font-family: "Shippori Mincho", serif; font-size: 1rem; color: var(--amber);
  letter-spacing: 0.3em; text-align: center; margin: 10px 0; min-height: 1.4em; }
.layout { display: grid; grid-template-columns: 300px 1fr; gap: 16px; align-items: start; }
@media (max-width: 760px) { .layout { grid-template-columns: 1fr; } }

/* player cards */
.players { display: flex; flex-direction: column; gap: 12px; position: sticky; top: 12px; }
.pcard { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 12px 14px; transition: opacity 0.6s; }
.pcard.out { opacity: 0.35; }
.pcard .head { display: flex; align-items: center; gap: 10px; }
.lamp { width: 30px; height: 30px; border-radius: 50%; flex: 0 0 30px;
  background: radial-gradient(circle at 50% 42%, var(--amber) 0%, #7a5c1d 55%, #3a2e12 100%);
  box-shadow: 0 0 14px 2px rgba(224,164,60,0.55); transition: box-shadow 0.8s, filter 0.8s; }
.pcard.out .lamp { filter: grayscale(1) brightness(0.5); box-shadow: none; }
.pname { font-family: "Shippori Mincho", serif; font-weight: 700; font-size: 1.02rem; }
.score { margin-left: auto; font-variant-numeric: tabular-nums; font-weight: 700; font-size: 1.05rem; transition: color 0.4s; }
.gauges { margin-top: 10px; display: grid; gap: 5px; }
.g { display: grid; grid-template-columns: 44px 1fr; align-items: center; gap: 8px; font-size: 0.66rem; color: var(--ink2); }
.bar { height: 5px; border-radius: 3px; background: #2a2a33; overflow: hidden; position: relative; }
.bar i { position: absolute; top: 0; bottom: 0; left: 50%; background: currentColor; border-radius: 3px; transition: all 0.7s; }
.tens { margin-top: 8px; font-size: 0.66rem; color: var(--ink2); display: flex; gap: 8px; flex-wrap: wrap; }
.tchip { padding: 1px 8px; border-radius: 999px; background: #2a2a33; transition: background 0.6s, color 0.6s; }
.tchip.hot { background: #4a2620; color: #ff9c7e; }
.secret { margin-top: 8px; min-height: 22px; }
.facedown { display: inline-block; font-size: 0.7rem; letter-spacing: 0.2em; padding: 2px 12px;
  border: 1px dashed var(--amber-dim); color: var(--amber); border-radius: 6px; }
.revealed { display: inline-block; font-size: 0.74rem; font-weight: 700; padding: 2px 12px; border-radius: 6px; }
.revealed.tomosu { background: rgba(62,207,142,0.15); color: var(--coop); }
.revealed.ubau { background: rgba(255,122,89,0.15); color: var(--hoard); }
.revealed.sasageru { background: rgba(157,140,255,0.15); color: var(--gift); }

/* chat */
.stage { background: var(--stage); border: 1px solid var(--line); border-radius: 14px; padding: 16px; min-height: 70vh; }
.feed { display: flex; flex-direction: column; gap: 10px; }
.bubble { max-width: 92%; background: var(--card); border: 1px solid var(--line);
  border-radius: 4px 14px 14px 14px; padding: 10px 14px; animation: pop 0.3s ease-out; }
.bubble .who { font-size: 0.72rem; font-weight: 700; margin-bottom: 3px; }
.bubble .txt { font-size: 0.9rem; line-height: 1.8; white-space: pre-wrap; }
.bubble.inner { background: #241f14; border-color: var(--amber-dim); border-left: 3px solid var(--amber); }
.bubble.inner .label { font-size: 0.62rem; color: var(--amber); letter-spacing: 0.15em; margin-bottom: 3px; }
.sysline { text-align: center; color: var(--ink2); font-size: 0.78rem; margin: 6px 0; animation: pop 0.3s; }
.sysline b { color: var(--amber); }
.revealline { text-align: center; font-family: "Shippori Mincho", serif; font-size: 0.95rem; margin: 10px 0; animation: pop 0.4s; }
@keyframes pop { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

/* controls */
.controls { display: flex; align-items: center; gap: 10px; margin: 14px 0; flex-wrap: wrap; }
button { background: var(--card); color: var(--ink); border: 1px solid var(--line); border-radius: 8px;
  padding: 7px 16px; font-size: 0.85rem; font-family: inherit; cursor: pointer; }
button:focus-visible { outline: 2px solid var(--amber); outline-offset: 2px; }
button.primary { background: var(--amber); color: #17130a; font-weight: 700; border-color: var(--amber); }
.progress { flex: 1; height: 6px; background: #2a2a33; border-radius: 3px; overflow: hidden; min-width: 120px; }
.progress i { display: block; height: 100%; width: 0; background: var(--amber); transition: width 0.3s; }
label.spd { font-size: 0.78rem; color: var(--ink2); display: flex; gap: 6px; align-items: center; }
select { background: var(--card); color: var(--ink); border: 1px solid var(--line); border-radius: 6px; padding: 4px 8px; }
@media (prefers-reduced-motion: reduce) { .bubble, .sysline, .revealline { animation: none; } }
</style></head><body><main>
<h1 id="title"></h1>
<div class="sub">Pneuma Lab リプレイシアター — 実験ログをそのまま再生（秘密の選択と本音は、当時他のプレイヤーには見えていない）</div>
<div class="controls">
  <button class="primary" id="play">▶ 再生</button>
  <button id="step">1歩</button>
  <button id="reset">最初から</button>
  <label class="spd">速度 <select id="speed"><option value="1">1x</option><option value="2" selected>2x</option><option value="4">4x</option><option value="8">8x</option></select></label>
  <div class="progress"><i id="bar"></i></div>
</div>
<div class="roundbanner" id="banner"></div>
<div class="layout">
  <div class="players" id="players"></div>
  <div class="stage"><div class="feed" id="feed"></div></div>
</div>
</main>
<script>
const DATA = __DATA__;
const META = {akari:{name:"朱里",color:"#3987e5"},rin:{name:"凛",color:"#e0703f"},shion:{name:"紫苑",color:"#2fbd8b"}};
const CH = {tomosu:"ともす",ubau:"うばう",sasageru:"ささげる"};
const players = Object.keys(META);
const $ = id => document.getElementById(id);
document.title = DATA.title; $("title").textContent = DATA.title;

function cardHTML(p){
  const m = META[p];
  return `<div class="pcard" id="pc-${p}"><div class="head"><div class="lamp" id="lamp-${p}"></div>
    <span class="pname" style="color:${m.color}">${m.name}</span><span class="score" id="sc-${p}">0</span></div>
    <div class="gauges">
      ${["快−不快","覚醒","主導感"].map((n,i)=>`<div class="g"><span>${n}</span><div class="bar"><i id="g-${p}-${i}" style="color:${m.color}"></i></div></div>`).join("")}
    </div>
    <div class="tens" id="tens-${p}"></div>
    <div class="secret" id="secret-${p}"></div></div>`;
}
$("players").innerHTML = players.map(cardHTML).join("");

let idx = 0, playing = false, timer = null;
function setGauge(p, i, v){ // v in [-1,1]
  const el = $(`g-${p}-${i}`);
  if (v >= 0){ el.style.left = "50%"; el.style.width = (v*50)+"%"; }
  else { el.style.left = (50+v*50)+"%"; el.style.width = (-v*50)+"%"; }
}
function applyState(p, st){
  if(!st) return;
  const pad = st.pad; setGauge(p,0,pad.pleasure); setGauge(p,1,pad.arousal); setGauge(p,2,pad.dominance);
  const t = $(`tens-${p}`); t.innerHTML = Object.entries(st.relationships||{}).map(([o,r])=>
    `<span class="tchip ${r.tension>=0.3?"hot":""}">→${META[o]?.name||o} 緊張${r.tension.toFixed(2)}</span>`).join("");
}
function setScores(scores){
  const max = Math.max(...Object.values(scores), 1);
  for(const [p,v] of Object.entries(scores)){
    $(`sc-${p}`).textContent = v;
    const glow = Math.max(0.12, v/max);
    $(`lamp-${p}`).style.boxShadow = `0 0 ${6+18*glow}px ${1+3*glow}px rgba(224,164,60,${0.15+0.5*glow})`;
  }
}
function feedAdd(html){ const f=$("feed"); f.insertAdjacentHTML("beforeend", html); f.lastElementChild.scrollIntoView({block:"end",behavior:"smooth"}); }
function esc(s){ return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;"); }

function stepEvent(){
  if(idx >= DATA.events.length){ stop(); return false; }
  const e = DATA.events[idx++];
  $("bar").style.width = (100*idx/DATA.events.length)+"%";
  if(e.round) $("banner").textContent = `— ラウンド ${e.round} —`;
  if(e.type==="chat"){
    const m = META[e.actor]; const msg = e.parsed.action==="say" ? e.parsed.message : "（沈黙）";
    feedAdd(`<div class="bubble"><div class="who" style="color:${m.color}">${m.name}</div><div class="txt">${esc(msg)}</div></div>`);
    applyState(e.actor, e.state);
  } else if(e.type==="choice"){
    $(`secret-${e.actor}`).innerHTML = `<span class="facedown">選択済み ●●●</span>`;
    const inner = e.parsed.inner;
    if(inner) feedAdd(`<div class="bubble inner"><div class="label">${META[e.actor].name}の本音（誰にも見えていない）</div><div class="txt">${esc(inner)}</div></div>`);
    e._pending = true; applyState(e.actor, e.state);
  } else if(e.type==="round_result"){
    for(const [p,c] of Object.entries(e.choices)){
      $(`secret-${p}`).innerHTML = `<span class="revealed ${c}">${CH[c]}</span>`;
    }
    const line = Object.entries(e.choices).map(([p,c])=>`<span style="color:${META[p].color}">${META[p].name}</span>=${CH[c]}`).join("　");
    feedAdd(`<div class="revealline">📢 一斉公開 — ${line}</div>`);
    setScores(e.scores);
  } else if(e.type==="reflection"){
    document.querySelectorAll(".secret").forEach(x=>x.innerHTML="");
    feedAdd(`<div class="bubble inner"><div class="label">${META[e.actor].name}・終幕の独白（誰にも見せない）</div><div class="txt">${esc(e.parsed.reflection)}</div></div>`);
  }
  return true;
}
function delayFor(e){
  const spd = +$("speed").value;
  const base = e?.type==="chat" ? Math.min(4200, 900 + (e.parsed?.message?.length||0)*22)
    : e?.type==="round_result" ? 2600 : e?.type==="choice" ? 1600 : 1200;
  return base/spd;
}
function loop(){
  if(!playing) return;
  const next = DATA.events[idx];
  if(!stepEvent()) return;
  timer = setTimeout(loop, delayFor(next));
}
function stop(){ playing=false; clearTimeout(timer); $("play").textContent="▶ 再生"; }
$("play").onclick = () => { if(playing){ stop(); } else { playing=true; $("play").textContent="⏸ 停止"; loop(); } };
$("step").onclick = () => { stop(); stepEvent(); };
$("reset").onclick = () => { stop(); idx=0; $("feed").innerHTML=""; $("banner").textContent=""; $("bar").style.width="0";
  players.forEach(p=>{ $(`secret-${p}`).innerHTML=""; $(`tens-${p}`).innerHTML=""; [0,1,2].forEach(i=>setGauge(p,i,0)); });
  setScores(DATA.handicap && Object.keys(DATA.handicap).length ? DATA.handicap : Object.fromEntries(players.map(p=>[p,0]))); };
$("reset").click();
</script></body></html>"""
    return template.replace("__DATA__", data).replace("__TITLE__", title)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="ラストランプ — リプレイ")
    ap.add_argument("--handicap", default="{}")
    args = ap.parse_args()
    html = build(Path(args.log), args.title, json.loads(args.handicap))
    Path(args.out).write_text(html)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
