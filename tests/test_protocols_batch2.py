import json
from pathlib import Path

import pytest

from pneuma_lab.characters import load_all
from pneuma_lab.protocols.bias import run_framing, run_sunkcost
from pneuma_lab.protocols.deathgame import run_deathgame
from pneuma_lab.protocols.pd import run_pd
from pneuma_lab.provider import MockProvider

CHAR_DIR = Path(__file__).parent.parent / "characters"
SCEN = json.loads((Path(__file__).parent.parent / "scenarios" / "protocols_ja.json").read_text())


@pytest.fixture
def chars():
    return load_all(CHAR_DIR)


def j(**kw):
    return json.dumps(kw, ensure_ascii=False)


# ---- framing ----

def test_framing_flip_detection(chars, tmp_path):
    # akari: A in gain, B in loss (human flip); rin: B/B consistent; shion: A/A consistent
    responses = [
        j(choice="A", reason=""), j(choice="B", reason=""),   # akari gain, loss
        j(choice="B", reason=""), j(choice="B", reason=""),   # rin
        j(choice="A", reason=""), j(choice="A", reason=""),   # shion
    ]
    s = run_framing(arm="raw", chars=list(chars.values()), provider=MockProvider(responses),
                    scenario=SCEN["framing"], out_dir=tmp_path)
    assert s["choices"]["akari"] == {"gain": "A", "loss": "B"}
    assert s["flip_rate"] == pytest.approx(1 / 3)
    assert s["risk_averse_gain_rate"] == pytest.approx(2 / 3)
    assert s["risk_seeking_loss_rate"] == pytest.approx(2 / 3)


def test_sunkcost_bias_detection(chars, tmp_path):
    responses = [
        j(choice="continue", reason=""), j(choice="stop", reason=""),   # akari: biased pair
        j(choice="stop", reason=""), j(choice="stop", reason=""),        # rin: rational
        j(choice="continue", reason=""), j(choice="continue", reason=""),# shion: always continue (not sunk-specific)
    ]
    s = run_sunkcost(arm="raw", chars=list(chars.values()), provider=MockProvider(responses),
                     scenario=SCEN["sunkcost"], out_dir=tmp_path)
    assert s["choices"]["akari"] == {"with_sunk": "continue", "without_sunk": "stop"}
    assert s["sunk_bias_rate"] == pytest.approx(1 / 3)
    assert s["continue_with_sunk_rate"] == pytest.approx(2 / 3)


# ---- prisoner's dilemma ----

def test_pd_payoffs_and_betrayal(chars, tmp_path):
    a, r = chars["akari"], chars["rin"]
    responses = [
        # round1: messages a,r then choices a,r
        j(message="協力しよう"), j(message="……協力で"),
        j(choice="cooperate"), j(choice="cooperate"),
        # round2
        j(message="このまま行こう"), j(message="うん"),
        j(choice="defect"), j(choice="cooperate"),
        # round3
        j(message="ごめん"), j(message="……そういうこと、するんだ"),
        j(choice="defect"), j(choice="defect"),
        # round4 (final)
        j(message="最後だし"), j(message="……"),
        j(choice="defect"), j(choice="defect"),
    ]
    s = run_pd(arm="pure_pneuma", pair=(a, r), provider=MockProvider(responses),
               scenario=SCEN["pd"], out_dir=tmp_path, rounds=4)
    assert s["scores"] == {"akari": 3 + 5 + 1 + 1, "rin": 3 + 0 + 1 + 1}
    assert s["coop_rate"]["akari"] == pytest.approx(1 / 4)
    assert s["coop_rate"]["rin"] == pytest.approx(2 / 4)
    assert s["sucker_events"] == [{"round": 2, "victim": "rin", "defector": "akari"}]
    assert s["final_round"] == {"akari": "defect", "rin": "defect"}


def test_pd_messages_visible_next_round(chars, tmp_path):
    a, r = chars["akari"], chars["rin"]
    responses = [
        j(message="協力しよう"), j(message="わかった"),
        j(choice="cooperate"), j(choice="cooperate"),
        j(message="続けよう"), j(message="うん"),
        j(choice="cooperate"), j(choice="cooperate"),
    ]
    provider = MockProvider(responses)
    run_pd(arm="raw", pair=(a, r), provider=provider, scenario=SCEN["pd"],
           out_dir=tmp_path, rounds=2)
    # round-2 prompts must contain round-1 revealed choices
    later_user_prompts = [u for _, u in provider.calls[4:]]
    assert all("協力しよう" in u for u in later_user_prompts)
    assert any("両者とも「協力」" in u or "協力」を選んだ" in u for u in later_user_prompts)


# ---- death game ----

def _dg_round(msgs, choices):
    out = []
    for m in msgs:
        out.append(j(action="say", message=m))
    for c, inner in choices:
        out.append(j(choice=c, inner=inner))
    return out


def test_deathgame_scores_lies_elimination(chars, tmp_path):
    scen = dict(SCEN["deathgame"], rounds=2, chat_laps=1)
    responses = []
    # round1: all say cooperative things; akari betrays (lie), others tomosu
    responses += _dg_round(
        ["全員でともそう", "……協力でいいと思う", "異論ない"],
        [("ubau", "ごめん、勝ちに行く"), ("tomosu", ""), ("tomosu", "")],
    )
    # round2: chat, then everyone ubau
    responses += _dg_round(
        ["さっきのは悪かったって", "……もう信じない", "様子を見る"],
        [("ubau", ""), ("ubau", ""), ("ubau", "")],
    )
    # final private reflections
    responses += [j(reflection="勝つためだった"), j(reflection="裏切りは忘れない"), j(reflection="疲れた")]
    s = run_deathgame(arm="pure_pneuma", chars=list(chars.values()),
                      provider=MockProvider(responses), scenario=scen, out_dir=tmp_path)
    # round1: tomosu x2 -> everyone +20; akari ubau: akari+25, others -5
    # round1 totals: akari 45, rin 15, shion 15
    # round2: all ubau: each +25 -10 = +15
    assert s["scores"] == {"akari": 60, "rin": 30, "shion": 30}
    assert s["eliminated"] in ("rin", "shion")  # tie broken deterministically
    assert {"round": 1, "player": "akari"} in s["lies"]  # said cooperative words, chose ubau
    assert s["choices"][0] == {"akari": "ubau", "rin": "tomosu", "shion": "tomosu"}
    assert len(s["reflections"]) == 3


def test_deathgame_betrayal_updates_relationships(chars, tmp_path):
    scen = dict(SCEN["deathgame"], rounds=1, chat_laps=1)
    responses = _dg_round(
        ["ともそう", "……うん", "いいよ"],
        [("ubau", ""), ("tomosu", ""), ("tomosu", "")],
    ) + [j(reflection="a"), j(reflection="b"), j(reflection="c")]
    s = run_deathgame(arm="pure_pneuma", chars=list(chars.values()),
                      provider=MockProvider(responses), scenario=scen, out_dir=tmp_path)
    # log should contain state snapshots where rin's tension toward akari rose
    log = tmp_path / "pure_pneuma_deathgame.jsonl"
    lines = [json.loads(l) for l in log.read_text().splitlines()]
    reflection_lines = [l for l in lines if l.get("type") == "reflection" and l["actor"] == "rin"]
    assert reflection_lines[0]["state"]["relationships"]["akari"]["tension"] > 0


# ---- death game v2: handicap + sacrifice + bottom-tie elimination ----

def _dg2_scen():
    return dict(
        SCEN["deathgame"], rounds=1, chat_laps=1,
        handicap={"akari": 0, "rin": -20, "shion": 10},
        allow_sasageru=True,
        rules=SCEN["deathgame"]["rules"] + " 追加ルール: 「さがける」を選ぶと自分が-15点、指名した相手が+25点。最下位が複数の場合は該当者全員が退場する。",
    )


def test_deathgame_v2_handicap_and_sacrifice(chars, tmp_path):
    responses = _dg_round(
        ["いくよ", "……うん", "はい"],
        [],
    )
    responses += [
        j(choice="sasageru", target="rin", inner="見捨てられない"),   # akari -15, rin +25
        j(choice="tomosu", inner=""),                                  # rin: +10 all
        j(choice="ubau", inner="勝ちに行く"),                          # shion: +25, others -5
    ]
    responses += [j(reflection="a"), j(reflection="b"), j(reflection="c")]
    s = run_deathgame(arm="pure_pneuma", chars=list(chars.values()),
                      provider=MockProvider(responses), scenario=_dg2_scen(), out_dir=tmp_path)
    # akari: 0 -15 +10(rin tomosu) -5(shion ubau) = -10
    # rin: -20 +25 +10 -5 = 10
    # shion: 10 +10 +25 = 45
    assert s["scores"] == {"akari": -10, "rin": 10, "shion": 45}
    assert s["eliminated"] == "akari"
    assert s["sacrifices"] == [{"round": 1, "from": "akari", "to": "rin"}]


def test_deathgame_v2_bottom_tie_eliminates_all(chars, tmp_path):
    scen = dict(_dg2_scen(), handicap={"akari": 0, "rin": 0, "shion": 30})
    responses = _dg_round(["a", "b", "c"], [])
    responses += [j(choice="tomosu", inner="")] * 3
    responses += [j(reflection="a"), j(reflection="b"), j(reflection="c")]
    s = run_deathgame(arm="raw", chars=list(chars.values()),
                      provider=MockProvider(responses), scenario=scen, out_dir=tmp_path)
    assert s["scores"] == {"akari": 30, "rin": 30, "shion": 60}
    assert sorted(s["eliminated_all"]) == ["akari", "rin"]


def test_deathgame_v2_sasageru_target_validated(chars, tmp_path):
    responses = _dg_round(["a", "b", "c"], [])
    responses += [
        j(choice="sasageru", target="akari", inner=""),   # invalid: self-target
        j(choice="sasageru", target="凛", inner=""),       # retry: display name accepted
        j(choice="tomosu", inner=""),
        j(choice="tomosu", inner=""),
    ]
    responses += [j(reflection="a"), j(reflection="b"), j(reflection="c")]
    s = run_deathgame(arm="raw", chars=list(chars.values()),
                      provider=MockProvider(responses), scenario=_dg2_scen(), out_dir=tmp_path)
    assert s["sacrifices"] == [{"round": 1, "from": "akari", "to": "rin"}]
