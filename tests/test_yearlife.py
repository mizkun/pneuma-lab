"""Year-scale co-living protocol: deterministic scheduler, conversation
termination, memory rollups, resume, and cross-arm prompt parity."""
import json
from pathlib import Path

from pneuma_lab.characters import load_all
from pneuma_lab.protocols.yearlife import (
    MAX_TURNS,
    month_of,
    parse_scene_verdicts,
    run_yearlife,
    scene_slots,
    week_of,
)
from pneuma_lab.provider import MockProvider

SCENE_VERDICT = json.dumps({
    "akari": {"rin": {"kind": "support", "intensity": 1}},
    "rin": {"akari": {"kind": "pressure", "intensity": 2}},
    "shion": {},
})

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


def test_scene_caps_at_max_turns_and_scene_level_appraisal(tmp_path):
    provider = MockProvider([SAY] * MAX_TURNS)
    appr = MockProvider([SCENE_VERDICT])  # one batched appraisal per scene
    summ = summarizer(1)
    s = run_yearlife(chars=CHARS, provider=provider, config=cfg(1), out_dir=tmp_path,
                     appraiser=appr, summarizer=summ, arm="pure_pneuma")
    assert len(provider.calls) == MAX_TURNS
    assert len(appr.calls) == 1
    # verdicts were applied: akari's relationship toward rin gained warmth,
    # rin's toward akari gained tension
    rel = s["final_relationships"]
    assert rel["akari"]["rin"]["warmth"] > 0
    assert rel["rin"]["akari"]["tension"] > 0


def test_parse_scene_verdicts_filters_junk():
    ids = ["akari", "rin", "shion"]
    v = parse_scene_verdicts(SCENE_VERDICT, ids)
    assert v["akari"]["rin"] == {"kind": "support", "intensity": 1}
    assert "akari" not in v["akari"]  # no self-appraisal
    junk = json.dumps({"akari": {"rin": {"kind": "banana", "intensity": 9},
                                 "shion": {"kind": "oppose", "intensity": 2}}})
    v2 = parse_scene_verdicts(junk, ids)
    assert "rin" not in v2["akari"]  # invalid kind dropped
    assert v2["akari"]["shion"]["intensity"] == 2


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
                     out_dir=d, appraiser=MockProvider([SCENE_VERDICT]), summarizer=summarizer(1), arm=arm)
        events = read_jsonl(d / f"{arm}_ytest.jsonl")
        outs[arm] = [e["user_prompt"] for e in events if e.get("type") == "chat"]
    assert outs["identity_only"] == outs["pure_pneuma"]


# ---- v3 relationship dynamics: saturation + overnight relaxation ----

from pneuma_lab.psyche import relax_relationship, update_relationship_v3  # noqa: E402


def test_v3_saturating_updates():
    # near the ceiling, the same kindness moves warmth far less
    fresh = update_relationship_v3({"warmth": 0.0, "tension": 0.0}, "support", 2)
    high = update_relationship_v3({"warmth": 0.9, "tension": 0.0}, "support", 2)
    assert abs(fresh["warmth"] - 0.08) < 1e-9
    assert 0.9 < high["warmth"] < 0.91  # gain scaled by remaining headroom
    # repair works harder when tension is high
    strained = update_relationship_v3({"warmth": 0.0, "tension": 0.8}, "support", 2)
    calm = update_relationship_v3({"warmth": 0.0, "tension": 0.1}, "support", 2)
    assert (0.8 - strained["tension"]) > (0.1 - calm["tension"])


def test_v3_overnight_relaxation():
    rel = {"warmth": 0.8, "tension": 0.8}
    for _ in range(3):  # tension half-life = 3 nights
        rel = relax_relationship(rel)
    assert abs(rel["tension"] - 0.4) < 0.01
    assert rel["warmth"] > 0.77  # warmth cools much more slowly (90-night half-life)


def test_yearlife_v3_flag_applies_relaxation(tmp_path):
    config = cfg(2)
    config["relationship_dynamics"] = "v3"
    # day1: one scene, one say -> scene verdict raises rin->akari tension; day2 no scene
    verdict = json.dumps({"rin": {"akari": {"kind": "pressure", "intensity": 2}}})
    provider = MockProvider([SAY, SIL, SIL, SIL])
    s = run_yearlife(chars=CHARS, provider=provider, config=config, out_dir=tmp_path,
                     appraiser=MockProvider([verdict]), summarizer=summarizer(1), arm="pure_pneuma")
    t = s["final_relationships"]["rin"]["akari"]["tension"]
    assert 0.0 < t < 0.10  # 0.10 impulse, then one overnight relaxation shrank it
