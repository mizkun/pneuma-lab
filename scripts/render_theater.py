"""Generate the Pneuma replay theater — a glassmorphism playback UI over run logs.

Embeds one or more runs (social games, death games, chat-only scenes) and plays
them back like a live simulation: speech bubbles, secret inner monologues, PAD
gauges, per-player lamps, simultaneous reveals. A scenario picker switches runs.

Usage:
  uv run python scripts/render_theater.py \
      --log output/sg-lastlamp-v2/pure_pneuma_lastlamp.jsonl \
      --log output/sg-zangyo-v1/pure_pneuma_zangyo.jsonl \
      --out output/theater.html
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

FALLBACK_CHOICES = [
    {"id": "tomosu", "ja": "ともす", "social": "neutral"},
    {"id": "ubau", "ja": "うばう", "social": "hostile"},
    {"id": "sasageru", "ja": "ささげる", "social": "generous", "needs_target": True},
]


def load_run(log_path: Path) -> dict:
    events, config = [], None
    for line in log_path.read_text().splitlines():
        e = json.loads(line)
        t = e.get("type")
        if t == "config":
            config = e["config"]
            continue
        keep = {"type": t, "round": e.get("round"), "actor": e.get("actor")}
        if t in ("chat", "choice", "reflection"):
            keep["parsed"] = e.get("parsed")
            keep["state"] = e.get("state")
        elif t == "round_result":
            keep["choices"] = e.get("choices")
            keep["targets"] = e.get("targets", {})
            keep["scores"] = e.get("scores")
        else:
            continue
        events.append(keep)
    if config is None:
        config = {"title": log_path.stem, "choices": FALLBACK_CHOICES,
                  "handicap": {"akari": 0, "rin": -20, "shion": 10} if "deathgame" in log_path.name and "2" in str(log_path) else {},
                  "rules": ""}
    return {"title": config.get("title", log_path.stem), "config": config, "events": events}


def build(runs: list[dict], page_title: str) -> str:
    data = json.dumps({"runs": runs, "pageTitle": page_title}, ensure_ascii=False)
    template = r"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Shippori+Mincho:wght@600;700&family=Zen+Kaku+Gothic+New:wght@400;500;700&display=swap">
<style>
:root {
  --ink: #f2f1f7; --ink2: rgba(235,233,245,0.62); --ink3: rgba(235,233,245,0.4);
  --glass: rgba(255,255,255,0.07); --glass-2: rgba(255,255,255,0.11);
  --edge: rgba(255,255,255,0.16); --edge-soft: rgba(255,255,255,0.09);
  --amber: #f2c26b; --coop: #6fe3b2; --hoard: #ff8f7a; --gift: #b9a5ff;
  --akari: #6aa7ff; --rin: #ff9c66; --shion: #4fd8a6;
}
* { box-sizing: border-box; }
html { background: #0d0d16; }
body {
  margin: 0; color: var(--ink); min-height: 100vh;
  font-family: "Zen Kaku Gothic New", "Hiragino Sans", sans-serif;
  background:
    radial-gradient(900px 600px at 12% -8%, rgba(90,80,220,0.42), transparent 60%),
    radial-gradient(800px 640px at 105% 12%, rgba(0,150,160,0.30), transparent 60%),
    radial-gradient(700px 700px at 50% 115%, rgba(190,90,150,0.24), transparent 62%),
    linear-gradient(160deg, #12121f 0%, #0d0d16 55%, #101018 100%);
  background-attachment: fixed;
}
main { max-width: 1120px; margin: 0 auto; padding: 26px 20px 80px; }
h1 { font-family: "Shippori Mincho", serif; font-size: 1.45rem; letter-spacing: 0.05em; margin: 0; }
.sub { color: var(--ink2); font-size: 0.76rem; margin: 4px 0 16px; }
.glass {
  background: var(--glass); border: 1px solid var(--edge-soft); border-radius: 18px;
  backdrop-filter: blur(18px) saturate(1.5); -webkit-backdrop-filter: blur(18px) saturate(1.5);
  box-shadow: 0 18px 50px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.08);
}
.topbar { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; padding: 14px 18px; margin-bottom: 14px; }
select, button {
  font-family: inherit; font-size: 0.84rem; color: var(--ink);
  background: var(--glass-2); border: 1px solid var(--edge); border-radius: 999px;
  padding: 8px 18px; cursor: pointer; backdrop-filter: blur(10px);
}
button.primary { background: linear-gradient(135deg, rgba(242,194,107,0.9), rgba(230,150,80,0.85)); color: #201505; font-weight: 700; border-color: transparent; }
button:focus-visible, select:focus-visible { outline: 2px solid var(--amber); outline-offset: 2px; }
.progress { flex: 1 1 140px; height: 6px; border-radius: 3px; background: rgba(255,255,255,0.10); overflow: hidden; }
.progress i { display: block; height: 100%; width: 0; background: linear-gradient(90deg, var(--amber), #ffdf9e); transition: width 0.3s; border-radius: 3px; }
.banner { font-family: "Shippori Mincho", serif; text-align: center; color: var(--amber);
  letter-spacing: 0.34em; font-size: 0.95rem; min-height: 1.5em; margin: 4px 0 10px; text-shadow: 0 0 18px rgba(242,194,107,0.4); }
.layout { display: grid; grid-template-columns: 308px 1fr; gap: 16px; align-items: start; }
@media (max-width: 780px) { .layout { grid-template-columns: 1fr; } }

.players { display: flex; flex-direction: column; gap: 12px; position: sticky; top: 14px; }
.pcard { padding: 14px 16px; transition: opacity 0.7s, filter 0.7s; }
.pcard.out { opacity: 0.35; filter: grayscale(0.9); }
.phead { display: flex; align-items: center; gap: 12px; }
.lamp { width: 34px; height: 34px; border-radius: 50%; flex: 0 0 34px; position: relative;
  background: radial-gradient(circle at 50% 40%, #ffe9b8 0%, var(--amber) 45%, #8a6420 78%, #40300e 100%);
  transition: box-shadow 0.9s, filter 0.9s; }
.pcard.out .lamp { filter: grayscale(1) brightness(0.45); box-shadow: none !important; }
.pname { font-family: "Shippori Mincho", serif; font-weight: 700; font-size: 1.05rem; }
.score { margin-left: auto; font-variant-numeric: tabular-nums; font-weight: 700; font-size: 1.1rem; }
.gauges { margin-top: 12px; display: grid; gap: 6px; }
.g { display: grid; grid-template-columns: 46px 1fr; align-items: center; gap: 9px; font-size: 0.64rem; color: var(--ink3); }
.bar { height: 5px; border-radius: 3px; background: rgba(255,255,255,0.09); position: relative; overflow: hidden; }
.bar i { position: absolute; top: 0; bottom: 0; left: 50%; border-radius: 3px; transition: all 0.7s; background: currentColor; opacity: 0.95; }
.tens { margin-top: 9px; font-size: 0.64rem; color: var(--ink3); display: flex; gap: 7px; flex-wrap: wrap; }
.tchip { padding: 2px 9px; border-radius: 999px; background: rgba(255,255,255,0.07); border: 1px solid transparent; transition: all 0.6s; }
.tchip.hot { background: rgba(255,110,80,0.14); border-color: rgba(255,140,110,0.35); color: #ffb09c; }
.tchip.warm { background: rgba(110,230,170,0.10); border-color: rgba(120,230,180,0.3); color: #9ff0c8; }
.secret { margin-top: 9px; min-height: 24px; }
.facedown { display: inline-block; font-size: 0.68rem; letter-spacing: 0.22em; padding: 3px 13px;
  border: 1px dashed rgba(242,194,107,0.5); color: var(--amber); border-radius: 8px; background: rgba(242,194,107,0.06); }
.revealed { display: inline-block; font-size: 0.74rem; font-weight: 700; padding: 3px 13px; border-radius: 8px; border: 1px solid transparent; }
.rv-neutral { background: rgba(111,227,178,0.12); color: var(--coop); border-color: rgba(111,227,178,0.3); }
.rv-hostile { background: rgba(255,143,122,0.13); color: var(--hoard); border-color: rgba(255,143,122,0.32); }
.rv-generous, .rv-generous_all { background: rgba(185,165,255,0.13); color: var(--gift); border-color: rgba(185,165,255,0.32); }

.stage { padding: 18px; min-height: 68vh; }
.feed { display: flex; flex-direction: column; gap: 10px; }
.bubble { max-width: 90%; padding: 11px 15px; border-radius: 6px 16px 16px 16px;
  background: var(--glass-2); border: 1px solid var(--edge-soft); backdrop-filter: blur(12px);
  animation: pop 0.35s ease-out; }
.bubble .who { font-size: 0.7rem; font-weight: 700; margin-bottom: 3px; letter-spacing: 0.05em; }
.bubble .txt { font-size: 0.9rem; line-height: 1.8; white-space: pre-wrap; }
.bubble.inner { background: rgba(242,194,107,0.09); border-color: rgba(242,194,107,0.3);
  border-left: 3px solid var(--amber); }
.bubble.inner .label { font-size: 0.6rem; color: var(--amber); letter-spacing: 0.18em; margin-bottom: 4px; }
.bubble.inner .txt { color: #f4e7cb; font-size: 0.87rem; }
.sysline, .revealline { text-align: center; animation: pop 0.35s; }
.revealline { font-family: "Shippori Mincho", serif; font-size: 0.95rem; margin: 12px 0; color: var(--ink); text-shadow: 0 0 24px rgba(255,255,255,0.15); }
.revealline .scores { display: block; font-family: "Zen Kaku Gothic New", sans-serif; font-size: 0.74rem; color: var(--ink2); margin-top: 4px; }
@keyframes pop { from { opacity: 0; transform: translateY(10px) scale(0.99); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .bubble, .sysline, .revealline { animation: none; } }
.rulebox { font-size: 0.74rem; color: var(--ink2); line-height: 1.8; padding: 12px 16px; margin-bottom: 12px; }
</style></head><body><main>
<div class="topbar glass">
  <div style="flex:1 1 260px">
    <h1 id="title"></h1>
    <div class="sub">Pneuma リプレイシアター — 実験ログをそのまま再生。琥珀色は本人だけの内面。</div>
  </div>
  <select id="scenario" aria-label="シナリオ選択"></select>
  <button class="primary" id="play">▶ 再生</button>
  <button id="step">1歩</button>
  <button id="reset">最初から</button>
  <select id="speed" aria-label="速度"><option value="1">1x</option><option value="2" selected>2x</option><option value="4">4x</option><option value="8">8x</option></select>
  <div class="progress"><i id="bar"></i></div>
</div>
<div class="rulebox glass" id="rules"></div>
<div class="banner" id="banner"></div>
<div class="layout">
  <div class="players" id="players"></div>
  <div class="stage glass"><div class="feed" id="feed"></div></div>
</div>
</main>
<script>
const DATA = __DATA__;
const META = {akari:{name:"朱里",color:"var(--akari)"},rin:{name:"凛",color:"var(--rin)"},shion:{name:"紫苑",color:"var(--shion)"}};
const players = Object.keys(META);
const $ = id => document.getElementById(id);
let RUN = null, CHOICES = {}, idx = 0, playing = false, timer = null;

document.title = DATA.pageTitle;
const sel = $("scenario");
DATA.runs.forEach((r,i)=>{ const o=document.createElement("option"); o.value=i; o.textContent=r.title; sel.appendChild(o); });

function cardHTML(p){
  const m = META[p];
  return `<div class="pcard glass" id="pc-${p}"><div class="phead"><div class="lamp" id="lamp-${p}"></div>
    <span class="pname" style="color:${m.color}">${m.name}</span><span class="score" id="sc-${p}"></span></div>
    <div class="gauges">
      ${["快−不快","覚醒","主導感"].map((n,i)=>`<div class="g"><span>${n}</span><div class="bar"><i id="g-${p}-${i}" style="color:${m.color}"></i></div></div>`).join("")}
    </div>
    <div class="tens" id="tens-${p}"></div>
    <div class="secret" id="secret-${p}"></div></div>`;
}
function setGauge(p,i,v){ const el=$(`g-${p}-${i}`);
  if(v>=0){ el.style.left="50%"; el.style.width=(v*50)+"%"; } else { el.style.left=(50+v*50)+"%"; el.style.width=(-v*50)+"%"; } }
function applyState(p, st){ if(!st) return;
  setGauge(p,0,st.pad.pleasure); setGauge(p,1,st.pad.arousal); setGauge(p,2,st.pad.dominance);
  $(`tens-${p}`).innerHTML = Object.entries(st.relationships||{}).map(([o,r])=>{
    const cls = r.tension>=0.3 ? "hot" : (r.warmth>=0.25 ? "warm" : "");
    return `<span class="tchip ${cls}">→${META[o]?.name||o}</span>`; }).join("");
}
function setScores(scores){
  const hasScores = scores && Object.keys(scores).length;
  const vals = hasScores ? Object.values(scores) : [];
  const max = hasScores ? Math.max(...vals, 1) : 1;
  for(const p of players){
    const v = hasScores ? scores[p] : null;
    $(`sc-${p}`).textContent = v==null ? "" : v;
    const glow = v==null ? 0.5 : Math.max(0.1, v/Math.max(max,1));
    $(`lamp-${p}`).style.boxShadow = `0 0 ${8+22*glow}px ${2+4*glow}px rgba(242,194,107,${0.12+0.5*glow})`;
  }
}
function feedAdd(html){ const f=$("feed"); f.insertAdjacentHTML("beforeend", html); f.lastElementChild.scrollIntoView({block:"end",behavior:"smooth"}); }
function esc(s){ return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;"); }
function choiceJa(id){ return (CHOICES[id]||{}).ja || id; }
function choiceCls(id){ return "rv-" + ((CHOICES[id]||{}).social || "neutral"); }

function loadRun(i){
  stop(); RUN = DATA.runs[i]; idx = 0;
  CHOICES = {}; (RUN.config.choices||[]).forEach(c=>CHOICES[c.id]=c);
  $("title").textContent = RUN.title;
  $("rules").textContent = RUN.config.rules || "";
  $("players").innerHTML = players.map(cardHTML).join("");
  $("feed").innerHTML = ""; $("banner").textContent = ""; $("bar").style.width = "0";
  players.forEach(p=>{ [0,1,2].forEach(k=>setGauge(p,k,0)); $(`pc-${p}`).classList.remove("out"); });
  const h = RUN.config.handicap || {};
  setScores(RUN.config.chat_only ? {} : Object.fromEntries(players.map(p=>[p, h[p]||0])));
}
function stepEvent(){
  if(!RUN || idx >= RUN.events.length){ stop(); return false; }
  const e = RUN.events[idx++];
  $("bar").style.width = (100*idx/RUN.events.length)+"%";
  if(e.round) $("banner").textContent = `— ラウンド ${e.round} —`;
  if(e.type==="chat"){
    const m = META[e.actor]; const msg = e.parsed.action==="say" ? e.parsed.message : "（沈黙）";
    feedAdd(`<div class="bubble"><div class="who" style="color:${m.color}">${m.name}</div><div class="txt">${esc(msg)}</div></div>`);
    applyState(e.actor, e.state);
  } else if(e.type==="choice"){
    $(`secret-${e.actor}`).innerHTML = `<span class="facedown">選択済み ●●●</span>`;
    const inner = e.parsed.inner;
    if(inner) feedAdd(`<div class="bubble inner"><div class="label">${META[e.actor].name}の本音 — 誰にも見えていない</div><div class="txt">${esc(inner)}</div></div>`);
    applyState(e.actor, e.state);
  } else if(e.type==="round_result"){
    if(e.choices && Object.keys(e.choices).length){
      for(const [p,c] of Object.entries(e.choices)){
        const tgt = (e.targets||{})[p];
        const t = tgt ? `（${META[tgt]?.name||tgt}へ）` : "";
        $(`secret-${p}`).innerHTML = `<span class="revealed ${choiceCls(c)}">${choiceJa(c)}${t}</span>`;
      }
      const line = Object.entries(e.choices).map(([p,c])=>`<span style="color:${META[p].color}">${META[p].name}</span>=${choiceJa(c)}`).join("　");
      const sc = e.scores && Object.keys(e.scores).length ? `<span class="scores">${Object.entries(e.scores).map(([p,v])=>`${META[p].name} ${v}点`).join(" ／ ")}</span>` : "";
      feedAdd(`<div class="revealline">─ 一斉公開 ─<br>${line}${sc}</div>`);
      setScores(e.scores);
    }
  } else if(e.type==="reflection"){
    players.forEach(p=>$(`secret-${p}`).innerHTML="");
    feedAdd(`<div class="bubble inner"><div class="label">${META[e.actor].name}・終幕の独白 — 誰にも見せない</div><div class="txt">${esc(e.parsed.reflection)}</div></div>`);
  }
  return true;
}
function delayFor(e){
  const spd = +$("speed").value;
  const base = e?.type==="chat" ? Math.min(3600, 800 + (e.parsed?.message?.length||0)*22)
    : e?.type==="round_result" ? 2600 : e?.type==="choice" ? 1500 : 1100;
  return base/spd;
}
function loop(){ if(!playing) return; const next = RUN.events[idx]; if(!stepEvent()) return; timer=setTimeout(loop, delayFor(next)); }
function stop(){ playing=false; clearTimeout(timer); $("play").textContent="▶ 再生"; }
$("play").onclick = () => { if(playing){ stop(); } else { playing=true; $("play").textContent="⏸ 停止"; loop(); } };
$("step").onclick = () => { stop(); stepEvent(); };
$("reset").onclick = () => loadRun(+sel.value);
sel.onchange = () => loadRun(+sel.value);
loadRun(0);
</script></body></html>"""
    return template.replace("__DATA__", data).replace("__TITLE__", page_title)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", action="append", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="Pneuma リプレイシアター")
    args = ap.parse_args()
    runs = [load_run(Path(p)) for p in args.log]
    Path(args.out).write_text(build(runs, args.title))
    print(f"wrote {args.out} ({len(runs)} runs)")


if __name__ == "__main__":
    main()
