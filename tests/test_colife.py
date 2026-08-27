import json
from pathlib import Path

import pytest

from pneuma_lab.appraiser import MockAppraiser
from pneuma_lab.characters import load_all
from pneuma_lab.protocols.colife import run_colife
from pneuma_lab.provider import MockProvider

CHAR_DIR = Path(__file__).parent.parent / "characters"


@pytest.fixture
def chars():
    c = load_all(CHAR_DIR)
    return [c["akari"], c["rin"], c["shion"]]


def j(**kw):
    return json.dumps(kw, ensure_ascii=False)


def cfg(**over):
    c = {
        "key": "share26", "title": "にじゅうろく荘",
        "setting": "3人は今日からシェアハウス「にじゅうろく荘」で暮らす。それぞれ自分の仕事を抱えている。",
        "days": 7,
        "weekday_laps": 1, "weekend_laps": 2,
        "style_note": "生活の会話らしく短く、1〜3文・120字以内。",
        "max_message_chars": 150,
        "topic_tags": ["cooperation"],
        "anchors": {"1": "引っ越し初日の夜。", "7": "初めての日曜。夜はハウスミーティング。"},
    }
    c.update(over)
    return c


def build_responses(config):
    """say for every chat slot + diary each Sunday + final reflections."""
    res = []
    for day in range(1, config["days"] + 1):
        laps = config["weekend_laps"] if day % 7 in (6, 0) else config["weekday_laps"]
        for _ in range(laps * 3):
            res.append(j(action="say", message=f"day{day}の発言。"))
        if day % 7 == 0:
            res += [j(diary=f"day{day}の日記。")] * 3
    res += [j(reflection="一ヶ月ふりかえり。")] * 3
    return res


def test_colife_day_structure_and_diary(chars, tmp_path):
    config = cfg()
    provider = MockProvider(build_responses(config))
    summarizer = MockProvider(["その日の要約。"] * 10)
    s = run_colife(chars=chars, provider=provider, config=config, out_dir=tmp_path,
                   appraiser=MockAppraiser({}), summarizer=summarizer, arm="pure_pneuma")
    assert s["days"] == 7
    lines = [json.loads(l) for l in (tmp_path / "pure_pneuma_share26.jsonl").read_text().splitlines()]
    chats = [l for l in lines if l["type"] == "chat"]
    # 5 weekdays *3 + sat(day6) 6 + sun(day7) 6 = 15+12 = 27
    assert len(chats) == 27
    diaries = [l for l in lines if l["type"] == "diary"]
    assert len(diaries) == 3  # one sunday x 3 chars
    assert len(s["reflections"]) == 3
    summaries = [l for l in lines if l["type"] == "day_summary"]
    assert len(summaries) == 7


def test_colife_memory_compression(chars, tmp_path):
    config = cfg()
    provider = MockProvider(build_responses(config))
    summarizer = MockProvider(["その日の要約。"] * 10)
    run_colife(chars=chars, provider=provider, config=config, out_dir=tmp_path,
               appraiser=MockAppraiser({}), summarizer=summarizer, arm="pure_pneuma")
    lines = [json.loads(l) for l in (tmp_path / "pure_pneuma_share26.jsonl").read_text().splitlines()]
    day5_prompts = [l["user_prompt"] for l in lines if l.get("type") == "chat" and l.get("day") == 5]
    # day5 prompt: day1-3 only as summaries, day4 verbatim (recent window = 1 previous day)
    p = day5_prompts[-1]
    assert "day4の発言" in p
    assert "day2の発言" not in p
    assert "その日の要約" in p
    # anchors appear on their day
    day1_prompts = [l["user_prompt"] for l in lines if l.get("type") == "chat" and l.get("day") == 1]
    assert "引っ越し初日" in day1_prompts[0]


def test_colife_relationships_persist_across_days(chars, tmp_path):
    config = cfg(days=3)
    responses = []
    for day in range(1, 4):
        for i in range(3):
            responses.append(j(action="say", message=("嫌味。" if (day == 1 and i == 0) else f"day{day}-{i}")))
    responses += [j(reflection="r")] * 3
    provider = MockProvider(responses)
    appraiser = MockAppraiser({"嫌味。": {"rin": {"kind": "dismiss", "intensity": 2}}})
    run_colife(chars=chars, provider=provider, config=config, out_dir=tmp_path,
               appraiser=appraiser, summarizer=MockProvider(["要約。"] * 5), arm="pure_pneuma")
    lines = [json.loads(l) for l in (tmp_path / "pure_pneuma_share26.jsonl").read_text().splitlines()]
    # day3 state: rin's tension toward akari persists (relationships don't decay)
    day3_states = [l["state"] for l in lines if l.get("day") == 3 and l.get("actor") == "rin" and "state" in l]
    assert day3_states[0]["relationships"]["akari"]["tension"] > 0
    # but PAD decayed back to ~baseline overnight
    pad = day3_states[0]["pad"]
    assert abs(pad["pleasure"] - chars[1].affect_baseline["pleasure"]) < 0.02
