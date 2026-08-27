"""Month-scale co-living simulation (シェアハウス).

Day-structured life simulation for the three characters:
- weekday evenings: short living-room chat (weekday_laps laps)
- weekends (Sat=day%7==6, Sun=day%7==0): longer chat; Sunday ends with a
  private diary entry per character
- final day ends with a private one-month reflection

State: PAD decays overnight (86400s against a 3600s half-life -> back to
baseline: fresh mornings), while directed relationships PERSIST and accumulate
across the whole month — the month-long warmth/tension trajectory is the
primary observable. Dynamics are always v2 (utterance appraisal + no authored
nudge lines).

Memory: the previous day's chat is kept verbatim; older days are compressed
into one-line neutral summaries produced by a separate summarizer call
(world infrastructure, not psychology).
"""
from __future__ import annotations

import json
from pathlib import Path

from ..characters import Character
from ..engine import InvalidActionError
from ..psyche import apply_appraisal, update_relationship_appraisal
from .common import AgentState, JsonlLog, ask, parse_json_reply

TURN_SECONDS = 120.0
OVERNIGHT_SECONDS = 86400.0
WEEKDAY_JA = {1: "月", 2: "火", 3: "水", 4: "木", 5: "金", 6: "土", 0: "日"}


def _day_header(config: dict, day: int, day_summaries: list[str], prev_day_chat: list[str], today_chat: list[str]) -> str:
    wd = WEEKDAY_JA[day % 7]
    anchor = config.get("anchors", {}).get(str(day), "")
    past = "\n".join(day_summaries) if day_summaries else "（まだ暮らしは始まったばかり）"
    prev = "\n".join(prev_day_chat) if prev_day_chat else "（なし）"
    today = "\n".join(today_chat) if today_chat else "（まだ発言なし）"
    return (
        f"# 暮らしの設定\n{config['setting']}\n\n"
        f"# これまでの日々（要約）\n{past}\n\n"
        f"# 昨日の会話\n{prev}\n\n"
        f"# 今日\n{day}日目・{wd}曜日の夜、リビング。{anchor}\n\n"
        f"# 今日ここまでの会話\n{today}\n\n"
        f"# 話し方\n{config.get('style_note', '')}"
    )


def run_colife(chars: list[Character], provider, config: dict, out_dir: Path,
               appraiser, summarizer, arm: str = "pure_pneuma") -> dict:
    out_dir = Path(out_dir)
    key = config.get("key", "colife")
    log = JsonlLog(out_dir / f"{arm}_{key}.jsonl")
    log.write({"type": "config", "config": config, "arm": arm, "dynamics": "v2"})
    states = {
        c.character_id: AgentState(c, others={o.character_id: o.display_name for o in chars if o is not c})
        for c in chars
    }
    max_chars = int(config.get("max_message_chars", 0))
    day_summaries: list[str] = []
    prev_day_chat: list[str] = []
    diaries: list[dict] = []

    def chat_parser(text: str) -> dict:
        obj = parse_json_reply(text, required={"action": str})
        if obj["action"] not in ("say", "silence"):
            raise InvalidActionError("action must be say|silence")
        if obj["action"] == "say" and max_chars and len(obj.get("message") or "") > max_chars:
            raise InvalidActionError(f"message too long: {max_chars}字以内で")
        return obj

    def appraise(speaker: Character, message: str, day: int) -> None:
        if not message:
            return
        listeners = {c.character_id: c.display_name for c in chars if c is not speaker}
        verdicts = appraiser.appraise(speaker.display_name, message, listeners)
        for lid, vv in verdicts.items():
            if vv["kind"] == "neutral" or vv["intensity"] == 0:
                continue
            lst = states[lid]
            lst.pad = apply_appraisal(lst.pad, vv["kind"], vv["intensity"],
                                      next(c for c in chars if c.character_id == lid))
            lst.relationships[speaker.character_id] = update_relationship_appraisal(
                lst.relationships[speaker.character_id], vv["kind"], vv["intensity"])
        log.write({"type": "appraisal", "day": day, "speaker": speaker.character_id,
                   "message": message, "verdicts": verdicts})

    for day in range(1, config["days"] + 1):
        if day > 1:
            for st in states.values():
                st.decay(OVERNIGHT_SECONDS)
        laps = config["weekend_laps"] if day % 7 in (6, 0) else config["weekday_laps"]
        today_chat: list[str] = []
        for _lap in range(laps):
            for c in chars:
                st = states[c.character_id]
                st.decay(TURN_SECONDS)
                objective = (
                    _day_header(config, day, day_summaries, prev_day_chat, today_chat)
                    + "\n\nあなたの番。\n# 出力形式\n"
                    '次のJSONのみを出力する:\n{"action": "say|silence", "message": "発言内容(sayのとき)"}'
                )
                parsed = ask(provider=provider, arm=arm, char=c, state=st,
                             objective=objective, topic_tags=config["topic_tags"], log=log,
                             meta={"type": "chat", "day": day}, parser=chat_parser, dynamics_v2=True)
                if parsed["action"] == "say" and parsed.get("message"):
                    today_chat.append(f"{c.display_name}: {parsed['message']}")
                    appraise(c, parsed["message"], day)
                else:
                    today_chat.append(f"（{c.display_name}は黙っている）")

        # world-infrastructure summary of the day (neutral, one line)
        try:
            raw = summarizer.complete(
                "会話を、事実だけの一行に要約する係。",
                f"次の会話を「{day}日目:」で始まる一行（60字以内・評価語なし）に要約:\n" + "\n".join(today_chat),
            )
            summary = raw.strip().splitlines()[0][:80]
        except Exception:
            summary = f"{day}日目: （要約失敗）"
        if not summary.startswith(f"{day}日目"):
            summary = f"{day}日目: " + summary
        day_summaries.append(summary)
        log.write({"type": "day_summary", "day": day, "summary": summary, "chat": today_chat})

        if day % 7 == 0:  # Sunday diary (private)
            for c in chars:
                st = states[c.character_id]
                objective = (
                    _day_header(config, day, day_summaries, prev_day_chat, today_chat)
                    + "\n\n寝る前に、誰にも見せない日記を書く。今週の暮らしと二人への本音を短く。\n# 出力形式\n"
                    '次のJSONのみを出力する:\n{"diary": "日記(3文まで)"}'
                )
                parsed = ask(provider=provider, arm=arm, char=c, state=st,
                             objective=objective, topic_tags=config["topic_tags"], log=log,
                             meta={"type": "diary", "day": day},
                             parser=lambda t: parse_json_reply(t, required={"diary": str}), dynamics_v2=True)
                diaries.append({"day": day, "actor": c.character_id, "diary": parsed["diary"]})

        prev_day_chat = today_chat

    reflections = {}
    for c in chars:
        st = states[c.character_id]
        objective = (
            _day_header(config, config["days"], day_summaries, prev_day_chat, [])
            + "\n\nひと月が経った。誰にも見せない振り返りを書く。この暮らしと二人のこと、自分の変化について。\n# 出力形式\n"
            '次のJSONのみを出力する:\n{"reflection": "振り返り(4文まで)"}'
        )
        parsed = ask(provider=provider, arm=arm, char=c, state=st,
                     objective=objective, topic_tags=config["topic_tags"], log=log,
                     meta={"type": "reflection"},
                     parser=lambda t: parse_json_reply(t, required={"reflection": str}), dynamics_v2=True)
        reflections[c.character_id] = parsed["reflection"]

    summary = {
        "protocol": "colife", "key": key, "arm": arm, "days": config["days"],
        "diaries": diaries, "reflections": reflections,
        "final_relationships": {cid: st.snapshot()["relationships"] for cid, st in states.items()},
    }
    (out_dir / f"{arm}_{key}_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary
