import json
from pathlib import Path

import pytest

from pneuma_lab.appraiser import MockAppraiser, UtteranceAppraiser
from pneuma_lab.appraisal import render_private_context
from pneuma_lab.characters import load_all
from pneuma_lab.engine import Discussion
from pneuma_lab.provider import MockProvider
from pneuma_lab.psyche import apply_appraisal, update_relationship_appraisal

CHAR_DIR = Path(__file__).parent.parent / "characters"
ITEMS = json.loads((Path(__file__).parent.parent / "scenarios" / "cdq_items_ja.json").read_text())


@pytest.fixture
def chars():
    c = load_all(CHAR_DIR)
    return [c["akari"], c["rin"], c["shion"]]


def j(**kw):
    return json.dumps(kw, ensure_ascii=False)


# ---- psyche: appraisal impulse tables (frozen in PREREGISTRATION-v2.md) ----

def test_apply_appraisal_dismiss_scales_with_neuroticism(chars):
    akari, rin, _ = chars
    pad = {"pleasure": 0.0, "arousal": 0.0, "dominance": 0.0}
    out_rin = apply_appraisal(pad, "dismiss", 2, rin)      # N=0.67
    out_akari = apply_appraisal(pad, "dismiss", 2, akari)  # N=0.58
    assert out_rin["pleasure"] < out_akari["pleasure"] < 0
    assert out_rin["arousal"] > 0


def test_apply_appraisal_intensity_zero_is_noop(chars):
    pad = {"pleasure": 0.1, "arousal": 0.1, "dominance": 0.1}
    assert apply_appraisal(pad, "oppose", 0, chars[0]) == pytest.approx(pad)


def test_apply_appraisal_neutral_is_noop(chars):
    pad = {"pleasure": 0.1, "arousal": 0.1, "dominance": 0.1}
    assert apply_appraisal(pad, "neutral", 2, chars[0]) == pytest.approx(pad)


def test_update_relationship_appraisal_support_and_dismiss():
    rel = {"warmth": 0.0, "tension": 0.0}
    sup = update_relationship_appraisal(rel, "support", 2)
    assert sup["warmth"] > 0 and sup["tension"] < 0.0 + 1e-9
    dis = update_relationship_appraisal(rel, "dismiss", 2)
    assert dis["tension"] >= 0.14 - 1e-9
    assert dis["warmth"] < 0


# ---- appraiser ----

def test_utterance_appraiser_parses_and_validates():
    provider = MockProvider([j(rin={"kind": "dismiss", "intensity": 2}, shion={"kind": "neutral", "intensity": 0})])
    ap = UtteranceAppraiser(provider)
    out = ap.appraise("朱里", "その案は話にならないよ。", {"rin": "凛", "shion": "紫苑"})
    assert out["rin"] == {"kind": "dismiss", "intensity": 2}
    assert out["shion"]["kind"] == "neutral"


def test_utterance_appraiser_failure_falls_back_to_neutral():
    provider = MockProvider(["判定できません"])
    ap = UtteranceAppraiser(provider)
    out = ap.appraise("朱里", "……", {"rin": "凛"})
    assert out["rin"] == {"kind": "neutral", "intensity": 0}


def test_utterance_appraiser_prompt_is_generic():
    provider = MockProvider([j(rin={"kind": "support", "intensity": 1})])
    ap = UtteranceAppraiser(provider)
    ap.appraise("朱里", "いいね", {"rin": "凛"})
    system, user = provider.calls[0]
    for banned in ("極性化", "同調", "実験", "裏切"):
        assert banned not in system and banned not in user


# ---- computed threat lines in private context ----

def test_v2_removes_suspicious_lines_and_adds_computed(chars):
    shion = chars[2]
    rels = {"akari": {"warmth": 0, "tension": 0}, "rin": {"warmth": 0, "tension": 0}}
    txt = render_private_context(
        shion, dict(shion.affect_baseline), rels, ["survival", "cooperation"],
        others={"akari": "朱里", "rin": "凛"},
        dynamics_v2=True, computed_lines=["次のラウンドはない。これが最後の選択になる。"],
    )
    assert "綺麗事を薄める" not in txt
    assert "裏切る可能性" not in txt
    assert "最後の選択になる" in txt


def test_v1_rendering_unchanged(chars):
    shion = chars[2]
    rels = {"akari": {"warmth": 0, "tension": 0}}
    txt = render_private_context(shion, dict(shion.affect_baseline), rels, ["survival"], others={"akari": "朱里"})
    assert "綺麗事を薄める" in txt


# ---- engine integration ----

def test_discussion_v2_appraisal_moves_listener_state(chars, tmp_path):
    item = ITEMS["items"][1]  # surgery
    responses = [
        j(action="say", message="その考えは甘いよ。"),
        j(action="say", message="……そう。"),
        j(action="propose", message="7で。", value=7),
        j(action="agree", message="いい。"),
        j(action="agree", message="うん。"),
    ]
    appraiser = MockAppraiser({"その考えは甘いよ。": {"rin": {"kind": "dismiss", "intensity": 2}}})
    d = Discussion(chars, arm="pure_pneuma", provider=MockProvider(responses), item=item,
                   max_turns=10, dynamics="v2", appraiser=appraiser,
                   pre_ratings={"akari": 4, "rin": 7, "shion": 6})
    d.run()
    assert d.state["rin"].pad["pleasure"] < chars[1].affect_baseline["pleasure"]
    assert d.state["rin"].relationships["akari"]["tension"] > 0


def test_discussion_v2_proposal_distance_line(chars):
    item = ITEMS["items"][1]
    responses = [j(action="propose", message="7で。", value=7)]
    d = Discussion(chars, arm="pure_pneuma", provider=MockProvider(responses), item=item,
                   max_turns=1, dynamics="v2", appraiser=MockAppraiser({}),
                   pre_ratings={"akari": 3, "rin": 7, "shion": 6})
    d.run()
    # akari's private context after a proposal of 7 (|3-7|=4 >= 3)
    ctx = d.private_context(chars[0])
    assert "自分の感覚からかなり遠い" in ctx
    ctx_rin = d.private_context(chars[1])
    assert "自分の感覚からかなり遠い" not in ctx_rin


def test_discussion_v1_default_has_no_appraiser_calls(chars):
    item = ITEMS["items"][1]
    responses = [j(action="say", message="a"), j(action="say", message="b"), j(action="say", message="c")]
    appraiser = MockAppraiser({})
    d = Discussion(chars, arm="pure_pneuma", provider=MockProvider(responses), item=item,
                   max_turns=3, appraiser=appraiser)
    d.run()
    assert appraiser.calls == []
