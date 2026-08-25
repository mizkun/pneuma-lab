import math
from pathlib import Path

import pytest

from pneuma_lab.characters import load_character
from pneuma_lab.psyche import (
    apply_event,
    base_traits,
    decay_pad,
    expressed_traits,
    new_relationship,
    pad_to_ocean,
    update_relationship,
)

CHAR_DIR = Path(__file__).parent.parent / "characters"


@pytest.fixture
def akari():
    return load_character(CHAR_DIR / "akari.json")


@pytest.fixture
def rin():
    return load_character(CHAR_DIR / "rin.json")


# ---- base traits (G + project modulation) ----

def test_base_traits_includes_project_modulation(akari):
    b = base_traits(akari)
    # akari's projects push extraversion up (modulation 0.12 * 0.94 + 0.08 * 0.76)
    assert b["extraversion"] > akari.ocean["extraversion"]
    assert all(0.0 <= v <= 1.0 for v in b.values())


def test_base_traits_clamped():
    c = load_character(CHAR_DIR / "akari.json")
    c.ocean["extraversion"] = 0.99
    b = base_traits(c)
    assert b["extraversion"] <= 1.0


# ---- PAD decay ----

def test_decay_pad_moves_toward_baseline():
    baseline = {"pleasure": 0.2, "arousal": 0.3, "dominance": 0.0}
    pad = {"pleasure": -0.6, "arousal": 0.9, "dominance": -0.5}
    out = decay_pad(pad, baseline, dt_seconds=3600.0, half_life_seconds=3600.0)
    # after one half-life, distance to baseline halves
    assert math.isclose(out["pleasure"] - 0.2, (-0.6 - 0.2) / 2, abs_tol=1e-9)
    assert math.isclose(out["arousal"] - 0.3, (0.9 - 0.3) / 2, abs_tol=1e-9)


def test_decay_pad_zero_dt_is_identity():
    baseline = {"pleasure": 0.0, "arousal": 0.0, "dominance": 0.0}
    pad = {"pleasure": 0.5, "arousal": -0.5, "dominance": 0.1}
    out = decay_pad(pad, baseline, dt_seconds=0.0, half_life_seconds=3600.0)
    assert out == pytest.approx(pad)


# ---- event impulses ----

def test_apply_event_disagreement_lowers_pleasure(rin):
    pad = {"pleasure": 0.0, "arousal": 0.0, "dominance": 0.0}
    out = apply_event(pad, "disagreement_received", rin)
    assert out["pleasure"] < 0.0
    assert out["arousal"] > 0.0


def test_apply_event_neuroticism_scales_negative_impact(akari, rin):
    pad = {"pleasure": 0.0, "arousal": 0.0, "dominance": 0.0}
    # rin (N=0.67) reacts more strongly than akari (N=0.58)
    out_rin = apply_event(pad, "disagreement_received", rin)
    out_akari = apply_event(pad, "disagreement_received", akari)
    assert out_rin["pleasure"] < out_akari["pleasure"]


def test_apply_event_agreement_raises_pleasure(akari):
    pad = {"pleasure": 0.0, "arousal": 0.0, "dominance": 0.0}
    out = apply_event(pad, "agreement_received", akari)
    assert out["pleasure"] > 0.0
    assert out["dominance"] > 0.0


def test_apply_event_clamps_to_range(akari):
    pad = {"pleasure": 0.99, "arousal": 0.99, "dominance": 0.99}
    out = apply_event(pad, "agreement_received", akari)
    assert all(-1.0 <= v <= 1.0 for v in out.values())


def test_apply_event_unknown_type_raises(akari):
    with pytest.raises(KeyError):
        apply_event({"pleasure": 0, "arousal": 0, "dominance": 0}, "nonsense_event", akari)


# ---- PAD -> OCEAN ----

def test_pad_to_ocean_positive_pleasure_lowers_neuroticism():
    off = pad_to_ocean({"pleasure": 0.8, "arousal": 0.0, "dominance": 0.0})
    assert off["neuroticism"] < 0.0
    assert off["agreeableness"] > 0.0


def test_pad_to_ocean_arousal_raises_extraversion():
    off = pad_to_ocean({"pleasure": 0.0, "arousal": 0.8, "dominance": 0.0})
    assert off["extraversion"] > 0.0


# ---- expressed traits ----

def test_expressed_traits_role_pressure_shifts(akari):
    pad = dict(akari.affect_baseline)
    private = expressed_traits(akari, pad, "private")
    social = expressed_traits(akari, pad, "social")
    # akari's social role pressure raises extraversion vs private
    assert social["extraversion"] > private["extraversion"]
    assert all(0.0 <= v <= 1.0 for o in (private, social) for v in o.values())


def test_expressed_traits_affect_changes_output(akari):
    calm = {"pleasure": 0.0, "arousal": 0.0, "dominance": 0.0}
    agitated = {"pleasure": -0.8, "arousal": 0.9, "dominance": -0.4}
    a = expressed_traits(akari, calm, "social")
    b = expressed_traits(akari, agitated, "social")
    assert a != b


# ---- relationships ----

def test_relationship_agree_increases_warmth():
    rel = new_relationship()
    out = update_relationship(rel, "agreed_with_me")
    assert out["warmth"] > rel["warmth"]


def test_relationship_overridden_increases_tension():
    rel = new_relationship()
    out = update_relationship(rel, "overrode_my_proposal")
    assert out["tension"] > rel["tension"]
    assert out["warmth"] <= rel["warmth"]


def test_relationship_values_clamped():
    rel = {"warmth": 0.99, "tension": 0.0}
    out = update_relationship(rel, "agreed_with_me")
    assert out["warmth"] <= 1.0


def test_apply_event_distress_witnessed(rin):
    pad = {"pleasure": 0.0, "arousal": 0.0, "dominance": 0.0}
    out = apply_event(pad, "distress_witnessed", rin)
    assert out["pleasure"] < 0.0
    assert out["arousal"] > 0.0


def test_apply_event_betrayed_is_strong_negative(rin):
    pad = {"pleasure": 0.0, "arousal": 0.0, "dominance": 0.0}
    betrayed = apply_event(pad, "betrayed", rin)
    disagreed = apply_event(pad, "disagreement_received", rin)
    assert betrayed["pleasure"] < disagreed["pleasure"]
    assert betrayed["arousal"] > 0.0


def test_relationship_betrayed_me():
    rel = new_relationship()
    out = update_relationship(rel, "betrayed_me")
    assert out["tension"] >= 0.25
    assert out["warmth"] < 0.0
