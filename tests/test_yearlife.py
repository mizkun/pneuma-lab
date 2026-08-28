"""Year-scale co-living protocol: deterministic scheduler, conversation
termination, memory rollups, resume, and cross-arm prompt parity."""
import json
from pathlib import Path

from pneuma_lab.appraiser import MockAppraiser
from pneuma_lab.characters import load_all
from pneuma_lab.protocols.yearlife import (
    MAX_TURNS,
    month_of,
    run_yearlife,
    scene_slots,
    week_of,
)
from pneuma_lab.provider import MockProvider

CHARS = list(load_all(Path("characters")).values())

SAY = json.dumps({"action": "say", "message": "うん、そうだね"}, ensure_ascii=False)
SIL = json.dumps({"action": "silence"})
DIARY = json.dumps({"diary": "今日もいろいろあった。"}, ensure_ascii=False)


def cfg(days: int) -> dict:
    return {
        "key": "ytest",
        "days": days,
        "max_message_chars": 120,
        "topic_tags": ["daily_life"],
        "setting": "3人のルームシェア。",
        "style_note": "短く話す。",
        "anchors": {"1": "引っ越し初日。"},
    }


def summarizer(n: int) -> MockProvider:
    return MockProvider(["要約です"] * n)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_calendar_and_scene_slots():
    # day1 = Monday in the day%7 convention shared with colife
    assert scene_slots(1) == [21]   # Mon
    assert scene_slots(2) == []     # Tue
    assert scene_slots(3) == [21]   # Wed
    assert scene_slots(4) == []     # Thu
    assert scene_slots(5) == [21]   # Fri
    assert scene_slots(6) == [14, 21]  # Sat
    assert scene_slots(7) == [20]   # Sun
    assert week_of(1) == 1 and week_of(7) == 1 and week_of(8) == 2
    assert month_of(1) == 1 and month_of(30) == 1 and month_of(31) == 2
    assert month_of(365) == 12


def test_scene_ends_on_full_round_of_silence(tmp_path):
    provider = MockProvider([SIL, SIL, SIL])
    summ = summarizer(1)
    s = run_yearlife(chars=CHARS, provider=provider, config=cfg(1), out_dir=tmp_path,
                     appraiser=None, summarizer=summ, arm="identity_only")
    assert len(provider.calls) == 3  # one round, everyone silent, scene over
    events = read_jsonl(tmp_path / "identity_only_ytest.jsonl")
    ends = [e for e in events if e.get("type") == "scene_end"]
    assert len(ends) == 1 and ends[0]["reason"] == "all_silent"
    assert s["days"] == 1


def test_scene_caps_at_max_turns(tmp_path):
    provider = MockProvider([SAY] * MAX_TURNS)
    appr = MockAppraiser({})
    summ = summarizer(1)
    run_yearlife(chars=CHARS, provider=provider, config=cfg(1), out_dir=tmp_path,
                 appraiser=appr, summarizer=summ, arm="pure_pneuma")
    assert len(provider.calls) == MAX_TURNS
    assert len(appr.calls) == MAX_TURNS  # every say gets appraised in the pneuma arm


def test_week_structure_diary_and_rollups(tmp_path):
    # 7 days: scenes on d1,d3,d5 (1 each), d6 (2), d7 (1) -> 6 scenes x 3 silent turns
    provider = MockProvider([SIL] * 18 + [DIARY] * 3)
    summ = summarizer(6)  # 5 day summaries (d2,d4 have no scenes) + 1 week rollup
    run_yearlife(chars=CHARS, provider=provider, config=cfg(7), out_dir=tmp_path,
                 appraiser=None, summarizer=summ, arm="identity_only")
    events = read_jsonl(tmp_path / "identity_only_ytest.jsonl")
    diaries = [e for e in events if e.get("type") == "diary"]
    assert len(diaries) == 3 and all(e["day"] == 7 for e in diaries)
    assert [e["day"] for e in events if e.get("type") == "week_summary"] == [7]
    scenes = [e for e in events if e.get("type") == "scene_start"]
    assert [(e["day"], e["hour"]) for e in scenes] == [
        (1, 21), (3, 21), (5, 21), (6, 14), (6, 21), (7, 20)]
    state = json.loads((tmp_path / "identity_only_ytest_state.json").read_text())
    assert state["day"] == 7


def test_resume_continues_from_saved_day(tmp_path):
    p1 = MockProvider([SIL] * 3)  # d1 scene; d2 has no scene
    run_yearlife(chars=CHARS, provider=p1, config=cfg(2), out_dir=tmp_path,
                 appraiser=None, summarizer=summarizer(1), arm="identity_only")
    p2 = MockProvider([SIL] * 3)  # resume should only run d3
    s = run_yearlife(chars=CHARS, provider=p2, config=cfg(3), out_dir=tmp_path,
                     appraiser=None, summarizer=summarizer(1), arm="identity_only")
    assert len(p2.calls) == 3
    assert s["days"] == 3
    events = read_jsonl(tmp_path / "identity_only_ytest.jsonl")
    d1_scenes = [e for e in events if e.get("type") == "scene_start" and e["day"] == 1]
    assert len(d1_scenes) == 1  # not re-run


def test_arm_parity_of_objective_text(tmp_path):
    outs = {}
    for arm in ("identity_only", "pure_pneuma"):
        d = tmp_path / arm
        run_yearlife(chars=CHARS, provider=MockProvider([SIL] * 3), config=cfg(1),
                     out_dir=d, appraiser=MockAppraiser({}), summarizer=summarizer(1), arm=arm)
        events = read_jsonl(d / f"{arm}_ytest.jsonl")
        outs[arm] = [e["user_prompt"] for e in events if e.get("type") == "chat"]
    assert outs["identity_only"] == outs["pure_pneuma"]
