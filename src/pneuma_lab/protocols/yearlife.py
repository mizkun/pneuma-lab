"""Year-scale co-living simulation (ルームシェア1年).

The clock is an hourly daytime tick (8:00–23:00). Every tick decays affect;
conversation scenes fire at deterministic slots (no RNG anywhere):

- Mon/Wed/Fri 21:00, Sat 14:00 and 21:00, Sun 20:00 (day%7, day1=Mon)
- a scene runs until a full round of silence or MAX_TURNS turns
- Sunday night: private diary per character, then the week's day-summaries
  roll up into a week summary
- every 30 days the month's week-summaries roll up into a month summary

Memory (identical in every arm): yesterday's chat verbatim, this week's day
summaries, this month's week summaries, all month summaries. Summaries are
world infrastructure produced by a separate summarizer model.

The pneuma arm additionally recomputes the injected inner context every turn.
Appraisal is BATCHED PER SCENE (one summarizer-style call over the scene
transcript, applied to affect and relationships at scene end) — per-utterance
appraisal at year scale would cost ~2500 extra CLI calls. Within a scene the
injected context therefore reflects the state at scene start; the observable
is the day-to-day and month-to-month divergence. The appraiser is only
invoked for arms that consume psyche state.

State is checkpointed to <arm>_<key>_state.json after every simulated day so
a multi-hour run can be killed and resumed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..characters import Character
from ..engine import InvalidActionError
from ..psyche import apply_appraisal, update_relationship_appraisal
from .common import AgentState, JsonlLog, ask, parse_json_reply

TURN_SECONDS = 120.0
TICK_SECONDS = 3600.0
OVERNIGHT_SECONDS = 9 * 3600.0  # 23:00 -> 8:00
TICK_HOURS = tuple(range(8, 24))
MAX_TURNS = 9
WEEKDAY_JA = {1: "月", 2: "火", 3: "水", 4: "木", 5: "金", 6: "土", 0: "日"}
_SLOTS = {1: [21], 2: [], 3: [21], 4: [], 5: [21], 6: [14, 21], 0: [20]}


APPRAISE_KINDS = ("support", "oppose", "dismiss", "pressure", "neutral")
SCENE_APPRAISE_SYSTEM = (
    "あなたは会話分析の担当者。会話全体が各聞き手に与えた対人的な作用を、指定のJSONだけで答える。"
)


def scene_slots(day: int) -> list[int]:
    return list(_SLOTS[day % 7])


def parse_scene_verdicts(text: str, ids: list[str]) -> dict:
    """{listener: {speaker: {kind, intensity}}} — self pairs and junk dropped."""
    obj = parse_json_reply(text, required={})
    out: dict = {}
    for listener in ids:
        row = obj.get(listener) or {}
        clean = {}
        for speaker in ids:
            if speaker == listener:
                continue
            v = row.get(speaker)
            if not isinstance(v, dict):
                continue
            kind = v.get("kind")
            try:
                intensity = int(v.get("intensity", 0))
            except (TypeError, ValueError):
                continue
            if kind in APPRAISE_KINDS and kind != "neutral" and 1 <= intensity <= 2:
                clean[speaker] = {"kind": kind, "intensity": intensity}
        out[listener] = clean
    return out


def week_of(day: int) -> int:
    return (day - 1) // 7 + 1


def month_of(day: int) -> int:
    return min((day - 1) // 30 + 1, 12)


def _context_header(config: dict, day: int, hour: int, mem: dict, today_chat: list[str]) -> str:
    wd = WEEKDAY_JA[day % 7]
    anchor = config.get("anchors", {}).get(str(day), "")
    months = "\n".join(mem["month_summaries"]) or "（まだ最初の月）"
    weeks = "\n".join(mem["week_summaries"]) or "（今月はまだ週のまとめなし）"
    days_ = "\n".join(mem["day_summaries"]) or "（今週はまだ日のまとめなし）"
    prev = "\n".join(mem["prev_day_chat"]) or "（なし）"
    today = "\n".join(today_chat) or "（まだ発言なし）"
    return (
        f"# 暮らしの設定\n{config['setting']}\n\n"
        f"# これまでの月ごとのまとめ\n{months}\n\n"
        f"# 今月の週ごとのまとめ\n{weeks}\n\n"
        f"# 今週の日ごとのまとめ\n{days_}\n\n"
        f"# 昨日の会話\n{prev}\n\n"
        f"# 今\n{day}日目・{wd}曜日の{hour}時、リビング。{anchor}\n\n"
        f"# 今日ここまでの会話\n{today}\n\n"
        f"# 話し方\n{config.get('style_note', '')}"
    )


def _summarize(summarizer, log: JsonlLog, kind: str, day: int, label: str, body: list[str]) -> str:
    try:
        raw = summarizer.complete(
            "会話や記録を、事実だけの一行に要約する係。",
            f"次の内容を「{label}:」で始まる一行（60字以内・評価語なし）に要約:\n" + "\n".join(body),
        )
        summary = raw.strip().splitlines()[0][:90]
    except Exception:
        summary = f"{label}: （要約失敗）"
    if not summary.startswith(label):
        summary = f"{label}: " + summary
    log.write({"type": kind, "day": day, "summary": summary})
    return summary


def _load_state(path: Path, states: dict, mem: dict) -> int:
    if not path.exists():
        return 0
    saved = json.loads(path.read_text())
    for cid, st in states.items():
        snap = saved["states"].get(cid)
        if snap:
            st.pad = dict(snap["pad"])
            st.relationships = {t: dict(r) for t, r in snap["relationships"].items()}
    for k in mem:
        mem[k] = saved["mem"][k]
    return int(saved["day"])


def _save_state(path: Path, day: int, states: dict, mem: dict) -> None:
    payload = {
        "day": day,
        "states": {cid: {"pad": st.pad, "relationships": st.relationships}
                   for cid, st in states.items()},
        "mem": mem,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False))
    os.replace(tmp, path)


def run_yearlife(chars: list[Character], provider, config: dict, out_dir: Path,
                 appraiser, summarizer, arm: str = "pure_pneuma") -> dict:
    out_dir = Path(out_dir)
    key = config.get("key", "yearlife")
    log = JsonlLog(out_dir / f"{arm}_{key}.jsonl")
    state_path = out_dir / f"{arm}_{key}_state.json"
    states = {
        c.character_id: AgentState(c, others={o.character_id: o.display_name for o in chars if o is not c})
        for c in chars
    }
    mem: dict = {"month_summaries": [], "week_summaries": [], "day_summaries": [],
                 "prev_day_chat": [], "diaries": []}
    start_day = _load_state(state_path, states, mem) + 1
    if start_day == 1:
        log.write({"type": "config", "config": config, "arm": arm, "dynamics": "v2"})

    max_chars = int(config.get("max_message_chars", 0))
    use_psyche = arm.endswith("pneuma")

    def chat_parser(text: str) -> dict:
        obj = parse_json_reply(text, required={"action": str})
        if obj["action"] not in ("say", "silence"):
            raise InvalidActionError("action must be say|silence")
        if obj["action"] == "say" and max_chars and len(obj.get("message") or "") > max_chars:
            raise InvalidActionError(f"message too long: {max_chars}字以内で")
        return obj

    by_id = {c.character_id: c for c in chars}
    name_to_id = {c.display_name: c.character_id for c in chars}

    def appraise_scene(day: int, hour: int, scene_lines: list[str]) -> None:
        """One batched appraisal call over the whole scene transcript."""
        if not (use_psyche and appraiser and scene_lines):
            return
        ids = list(by_id)
        roster = "、".join(f"{c.display_name}({c.character_id})" for c in chars)
        user = (
            f"参加者: {roster}\n\n# 会話\n" + "\n".join(scene_lines) + "\n\n"
            "この会話全体を通して、各聞き手が各話し手から受けた対人的な作用を集計する。\n"
            "kindは support(支えられた)/oppose(反対された)/dismiss(軽く流された)/"
            "pressure(圧を受けた)/neutral、intensityは0-2。\n# 出力形式\n"
            "次のJSONのみを出力する(キーはcharacter_id、自分自身のキーは含めない):\n"
            '{"akari": {"rin": {"kind": "...", "intensity": 0}, "shion": {...}}, "rin": {...}, "shion": {...}}'
        )
        try:
            raw = appraiser.complete(SCENE_APPRAISE_SYSTEM, user)
            verdicts = parse_scene_verdicts(raw, ids)
        except Exception as e:
            log.write({"type": "appraisal_error", "day": day, "hour": hour, "error": str(e)})
            return
        for listener, row in verdicts.items():
            lst = states[listener]
            for speaker, vv in row.items():
                lst.pad = apply_appraisal(lst.pad, vv["kind"], vv["intensity"], by_id[listener])
                lst.relationships[speaker] = update_relationship_appraisal(
                    lst.relationships[speaker], vv["kind"], vv["intensity"])
        log.write({"type": "scene_appraisal", "day": day, "hour": hour, "verdicts": verdicts})

    def run_scene(day: int, hour: int, scene_idx: int, today_chat: list[str]) -> None:
        log.write({"type": "scene_start", "day": day, "hour": hour})
        order = [chars[(day + scene_idx + i) % len(chars)] for i in range(len(chars))]
        scene_lines: list[str] = []
        silences = 0
        turns = 0
        reason = "max_turns"
        while turns < MAX_TURNS:
            c = order[turns % len(order)]
            st = states[c.character_id]
            st.decay(TURN_SECONDS)
            objective = (
                _context_header(config, day, hour, mem, today_chat)
                + "\n\nあなたの番。話すことがなければ黙っていてよい。\n# 出力形式\n"
                '次のJSONのみを出力する:\n{"action": "say|silence", "message": "発言内容(sayのとき)"}'
            )
            parsed = ask(provider=provider, arm=arm, char=c, state=st,
                         objective=objective, topic_tags=config["topic_tags"], log=log,
                         meta={"type": "chat", "day": day, "hour": hour}, parser=chat_parser,
                         dynamics_v2=True)
            turns += 1
            if parsed["action"] == "say" and parsed.get("message"):
                line = f"{c.display_name}: {parsed['message']}"
                today_chat.append(line)
                scene_lines.append(line)
                silences = 0
            else:
                today_chat.append(f"（{c.display_name}は黙っている）")
                silences += 1
                if silences >= len(chars):
                    reason = "all_silent"
                    break
        log.write({"type": "scene_end", "day": day, "hour": hour, "turns": turns, "reason": reason})
        appraise_scene(day, hour, scene_lines)

    for day in range(start_day, config["days"] + 1):
        if day > 1:
            for st in states.values():
                st.decay(OVERNIGHT_SECONDS)
        slots = scene_slots(day)
        today_chat: list[str] = []
        scene_idx = 0
        for hour in TICK_HOURS:
            for st in states.values():
                st.decay(TICK_SECONDS)
            if hour in slots:
                run_scene(day, hour, scene_idx, today_chat)
                scene_idx += 1

        if today_chat:
            mem["day_summaries"].append(
                _summarize(summarizer, log, "day_summary", day, f"{day}日目", today_chat))

        if day % 7 == 0:  # Sunday: private diary, then week rollup
            for c in chars:
                st = states[c.character_id]
                objective = (
                    _context_header(config, day, 23, mem, today_chat)
                    + "\n\n寝る前に、誰にも見せない日記を書く。この暮らしと二人への本音、自分のことを短く。\n# 出力形式\n"
                    '次のJSONのみを出力する:\n{"diary": "日記(3文まで)"}'
                )
                parsed = ask(provider=provider, arm=arm, char=c, state=st,
                             objective=objective, topic_tags=config["topic_tags"], log=log,
                             meta={"type": "diary", "day": day},
                             parser=lambda t: parse_json_reply(t, required={"diary": str}),
                             dynamics_v2=True)
                mem["diaries"].append({"day": day, "actor": c.character_id, "diary": parsed["diary"]})
            if mem["day_summaries"]:
                mem["week_summaries"].append(
                    _summarize(summarizer, log, "week_summary", day,
                               f"第{week_of(day)}週", mem["day_summaries"]))
                mem["day_summaries"] = []

        if day % 30 == 0 and mem["week_summaries"]:
            mem["month_summaries"].append(
                _summarize(summarizer, log, "month_summary", day,
                           f"{month_of(day)}ヶ月目", mem["week_summaries"]))
            mem["week_summaries"] = []

        mem["prev_day_chat"] = today_chat
        _save_state(state_path, day, states, mem)

    summary = {
        "protocol": "yearlife", "key": key, "arm": arm, "days": config["days"],
        "diaries": mem["diaries"],
        "month_summaries": mem["month_summaries"],
        "final_relationships": {cid: st.snapshot()["relationships"] for cid, st in states.items()},
    }
    (out_dir / f"{arm}_{key}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2))
    return summary
