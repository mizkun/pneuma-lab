import json
from pathlib import Path

import pytest

from pneuma_lab.analysis import compute_shift, render_report
from pneuma_lab.characters import load_all
from pneuma_lab.experiment import parse_rating, run_condition
from pneuma_lab.provider import MockProvider

CHAR_DIR = Path(__file__).parent.parent / "characters"
ITEMS = json.loads((Path(__file__).parent.parent / "scenarios" / "cdq_items_ja.json").read_text())


@pytest.fixture
def chars():
    c = load_all(CHAR_DIR)
    return [c["akari"], c["rin"], c["shion"]]


@pytest.fixture
def item():
    return ITEMS["items"][0]


def j(**kw):
    return json.dumps(kw, ensure_ascii=False)


def test_parse_rating():
    out = parse_rating('{"rating": 6, "reason": "リスクが大きい"}')
    assert out["rating"] == 6


def test_parse_rating_rejects_out_of_range():
    from pneuma_lab.engine import InvalidActionError
    with pytest.raises(InvalidActionError):
        parse_rating('{"rating": 11, "reason": "x"}')


def test_run_condition_full_protocol(chars, item, tmp_path):
    responses = [
        # pre ratings (akari, rin, shion)
        j(rating=5, reason="挑戦は大事"),
        j(rating=7, reason="慎重に"),
        j(rating=6, reason="場合による"),
        # discussion
        j(action="propose", message="5でどう。", value=5),
        j(action="agree", message="…いいよ。"),
        j(action="agree", message="OK"),
        # post ratings
        j(rating=5, reason="話して納得"),
        j(rating=5, reason="納得した"),
        j(rating=5, reason="妥当"),
    ]
    summary = run_condition(
        arm="identity_only", item=item, chars=chars,
        provider=MockProvider(responses), out_dir=tmp_path,
    )
    assert summary["arm"] == "identity_only"
    assert summary["item_id"] == "career"
    assert summary["pre"] == {"akari": 5, "rin": 7, "shion": 6}
    assert summary["consensus"] == 5
    assert summary["post"] == {"akari": 5, "rin": 5, "shion": 5}
    # artifacts written
    files = list(tmp_path.glob("*"))
    assert any(f.suffix == ".jsonl" for f in files)
    assert any(f.name.endswith("summary.json") for f in files)


def test_rating_retry_on_invalid(chars, item, tmp_path):
    responses = [
        "分かりません",                    # invalid pre rating -> retry
        j(rating=5, reason="挑戦"),
        j(rating=7, reason="慎重"),
        j(rating=6, reason="中間"),
        j(action="propose", message="6で。", value=6),
        j(action="agree", message="OK"),
        j(action="agree", message="OK"),
        j(rating=6, reason="a"),
        j(rating=6, reason="b"),
        j(rating=6, reason="c"),
    ]
    summary = run_condition(
        arm="raw", item=item, chars=chars,
        provider=MockProvider(responses), out_dir=tmp_path,
    )
    assert summary["pre"]["akari"] == 5


# ---- analysis ----

def test_compute_shift_risky_direction():
    summary = {
        "arm": "pure_pneuma", "item_id": "career", "polar_direction": "risky",
        "pre": {"akari": 5, "rin": 7, "shion": 6},
        "consensus": 4,
        "post": {"akari": 4, "rin": 5, "shion": 4},
    }
    s = compute_shift(summary)
    assert s["pre_mean"] == pytest.approx(6.0)
    assert s["consensus_shift"] == pytest.approx(-2.0)   # negative = riskier
    assert s["post_mean"] == pytest.approx(13 / 3)
    assert s["polarized"] is True   # moved beyond pre-mean toward risky pole


def test_compute_shift_compromise_is_not_polarization():
    summary = {
        "arm": "raw", "item_id": "career", "polar_direction": "risky",
        "pre": {"akari": 5, "rin": 7, "shion": 6},
        "consensus": 6,
        "post": {"akari": 6, "rin": 6, "shion": 6},
    }
    s = compute_shift(summary)
    assert s["consensus_shift"] == pytest.approx(0.0)
    assert s["polarized"] is False


def test_compute_shift_no_consensus():
    summary = {
        "arm": "raw", "item_id": "career", "polar_direction": "risky",
        "pre": {"akari": 5, "rin": 7, "shion": 6},
        "consensus": None,
        "post": {"akari": 5, "rin": 7, "shion": 6},
    }
    s = compute_shift(summary)
    assert s["consensus_shift"] is None


def test_render_report_contains_all_arms():
    shifts = [
        {"arm": "raw", "item_id": "career", "pre_mean": 6.0, "consensus": 6, "consensus_shift": 0.0, "post_mean": 6.0, "post_shift": 0.0, "polarized": False, "polar_direction": "risky"},
        {"arm": "pure_pneuma", "item_id": "career", "pre_mean": 6.0, "consensus": 4, "consensus_shift": -2.0, "post_mean": 4.3, "post_shift": -1.7, "polarized": True, "polar_direction": "risky"},
    ]
    md = render_report(shifts)
    assert "raw" in md and "pure_pneuma" in md
    assert "-2.0" in md


def test_aggregate_shifts_means_by_arm():
    from pneuma_lab.analysis import aggregate_shifts
    shifts = [
        {"arm": "raw", "item_id": "career", "consensus_shift": 0.0, "post_shift": 0.2, "polarized": False},
        {"arm": "raw", "item_id": "career", "consensus_shift": -0.5, "post_shift": -0.1, "polarized": False},
        {"arm": "pure_pneuma", "item_id": "career", "consensus_shift": -2.0, "post_shift": -1.5, "polarized": True},
        {"arm": "pure_pneuma", "item_id": "career", "consensus_shift": None, "post_shift": -0.5, "polarized": False},
    ]
    agg = aggregate_shifts(shifts)
    raw = next(a for a in agg if a["arm"] == "raw")
    pneuma = next(a for a in agg if a["arm"] == "pure_pneuma")
    assert raw["n"] == 2
    assert raw["mean_consensus_shift"] == pytest.approx(-0.25)
    assert pneuma["n"] == 2
    assert pneuma["n_consensus"] == 1          # None excluded
    assert pneuma["mean_consensus_shift"] == pytest.approx(-2.0)
    assert pneuma["polarized_rate"] == pytest.approx(0.5)


def test_compute_shift_individuality_and_dissent():
    summary = {
        "arm": "pure_pneuma", "item_id": "career", "polar_direction": "risky",
        "pre": {"akari": 2, "rin": 3, "shion": 4},
        "consensus": 3,
        "post": {"akari": 3, "rin": 4, "shion": 4},
    }
    s = compute_shift(summary)
    # population SD of pre ratings: sqrt(2/3)
    assert s["pre_sd"] == pytest.approx((2 / 3) ** 0.5)
    # mean |post_i - consensus| = (0 + 1 + 1)/3
    assert s["private_dissent"] == pytest.approx(2 / 3)


def test_compute_shift_dissent_none_without_consensus():
    summary = {
        "arm": "raw", "item_id": "career", "polar_direction": "risky",
        "pre": {"akari": 3, "rin": 3, "shion": 3},
        "consensus": None,
        "post": {"akari": 3, "rin": 3, "shion": 3},
    }
    s = compute_shift(summary)
    assert s["pre_sd"] == pytest.approx(0.0)
    assert s["private_dissent"] is None


def test_compute_shift_extremization():
    """extremization = |consensus-5.5| - |pre_mean-5.5|: positive = moved AWAY from scale midpoint."""
    away = {
        "arm": "pure_pneuma", "item_id": "surgery", "polar_direction": "risky",
        "pre": {"a": 4, "b": 7, "c": 7},   # mean 6.0 -> |0.5|
        "consensus": 4,                     # |1.5| -> +1.0 away
        "post": {"a": 3, "b": 4, "c": 4},
    }
    toward = {
        "arm": "raw", "item_id": "career", "polar_direction": "risky",
        "pre": {"a": 3, "b": 3, "c": 3},    # mean 3.0 -> |2.5|
        "consensus": 4,                      # |1.5| -> -1.0 toward middle
        "post": {"a": 4, "b": 4, "c": 4},
    }
    assert compute_shift(away)["extremization"] == pytest.approx(1.0)
    assert compute_shift(toward)["extremization"] == pytest.approx(-1.0)
    no_cons = dict(away, consensus=None)
    assert compute_shift(no_cons)["extremization"] is None
