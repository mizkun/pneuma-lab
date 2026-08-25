from pathlib import Path

import pytest

from pneuma_lab.appraisal import FORBIDDEN_TERMS, affect_words, render_private_context
from pneuma_lab.characters import load_all

CHAR_DIR = Path(__file__).parent.parent / "characters"
OTHERS = {"rin": "凛", "shion": "紫苑"}


@pytest.fixture
def chars():
    return load_all(CHAR_DIR)


def _ctx(char, pad=None, rels=None, tags=("career_risk", "achievement_vs_security")):
    pad = pad or dict(char.affect_baseline)
    rels = rels if rels is not None else {t: {"warmth": 0.0, "tension": 0.0} for t in OTHERS}
    others = {k: v for k, v in OTHERS.items() if k != char.character_id}
    return render_private_context(char, pad, rels, list(tags), others=others)


def test_deterministic(chars):
    a = _ctx(chars["akari"])
    b = _ctx(chars["akari"])
    assert a == b


def test_nonempty_japanese(chars):
    for c in chars.values():
        others = {k: v for k, v in {"akari": "朱里", **OTHERS}.items() if k != c.character_id}
        pad = dict(c.affect_baseline)
        rels = {t: {"warmth": 0.0, "tension": 0.0} for t in others}
        txt = render_private_context(c, pad, rels, ["career_risk"], others=others)
        assert len(txt) > 50


def test_no_forbidden_terms(chars):
    txt = _ctx(chars["shion"])
    for term in FORBIDDEN_TERMS:
        assert term not in txt


def test_inhibition_appears_for_high_avoidance_and_tension(chars):
    shion = chars["shion"]  # avoidance 0.76
    rels = {"akari": {"warmth": 0.1, "tension": 0.6}, "rin": {"warmth": 0.2, "tension": 0.0}}
    txt = render_private_context(shion, dict(shion.affect_baseline), rels, ["career_risk"], others={"akari": "朱里", "rin": "凛"})
    assert "言い出しにくい" in txt or "呑み込" in txt or "口が重" in txt


def test_negative_affect_changes_text(chars):
    calm = _ctx(chars["rin"], pad={"pleasure": 0.1, "arousal": 0.1, "dominance": 0.0})
    upset = _ctx(chars["rin"], pad={"pleasure": -0.7, "arousal": 0.7, "dominance": -0.3})
    assert calm != upset


def test_affect_words_extremes():
    low = affect_words({"pleasure": -0.8, "arousal": -0.8, "dominance": -0.8})
    high = affect_words({"pleasure": 0.8, "arousal": 0.8, "dominance": 0.8})
    assert low != high
    assert len(low) > 0 and len(high) > 0


def test_topic_tags_shift_value_conflicts(chars):
    career = _ctx(chars["rin"], tags=("career_risk", "achievement_vs_security"))
    health = _ctx(chars["rin"], tags=("health_risk", "quality_of_life"))
    assert career != health


def test_no_action_directive_in_context(chars):
    """The private context must never tell the character WHAT action to take."""
    txt = _ctx(chars["akari"])
    for directive in ("propose", "agreeを選", "silenceを選", "sayを選"):
        assert directive not in txt


def test_new_protocol_tags_have_specific_lines(chars):
    generic = "まだ言葉になり切っていない"
    for tag in ("peer_pressure", "fairness", "emergency", "cooperation", "survival"):
        txt = _ctx(chars["shion"], tags=(tag,))
        assert generic not in txt, f"tag {tag} fell through to generic line"


def test_lesion_mode_removes_suspect_lines(chars):
    from pneuma_lab import appraisal
    try:
        appraisal.LESIONED = True
        surv = _ctx(chars["shion"], tags=("survival",))
        coop = _ctx(chars["shion"], tags=("cooperation",))
        assert "綺麗事を薄める" not in surv
        assert "裏切る可能性" not in coop
        assert len(surv) > 30 and len(coop) > 30  # other content remains
    finally:
        appraisal.LESIONED = False
    assert "綺麗事を薄める" in _ctx(chars["shion"], tags=("survival",))
