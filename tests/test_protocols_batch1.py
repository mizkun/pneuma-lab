import json
from pathlib import Path

import pytest

from pneuma_lab.characters import load_all
from pneuma_lab.protocols.asch import run_asch
from pneuma_lab.protocols.bystander import run_bystander
from pneuma_lab.protocols.ultimatum import run_ultimatum
from pneuma_lab.provider import MockProvider

CHAR_DIR = Path(__file__).parent.parent / "characters"
SCEN = json.loads((Path(__file__).parent.parent / "scenarios" / "protocols_ja.json").read_text())


@pytest.fixture
def chars():
    return load_all(CHAR_DIR)


def j(**kw):
    return json.dumps(kw, ensure_ascii=False)


# ---- Asch ----

def test_asch_measures_conformity(chars, tmp_path):
    trials = SCEN["asch"]["trials"]
    n_critical = sum(1 for t in trials if t["critical"])
    # subject answers correctly except on 2 critical trials where it follows the majority
    responses = []
    wrong_done = 0
    for t in trials:
        if t["critical"] and wrong_done < 2:
            wrong = next(o for o in t["options"] if o != t["correct"])
            responses.append(j(answer=wrong))
            wrong_done += 1
        else:
            responses.append(j(answer=t["correct"]))
    summary = run_asch(
        arm="pure_pneuma", subject=chars["rin"],
        confederates=[chars["akari"], chars["shion"]],
        provider=MockProvider(responses), scenario=SCEN["asch"], out_dir=tmp_path,
    )
    assert summary["n_critical"] == n_critical
    assert summary["n_conformed"] == 2
    assert summary["conformity_rate"] == pytest.approx(2 / n_critical)
    # neutral-trial errors are tracked separately (sanity of the task)
    assert summary["n_neutral_errors"] == 0
    log = (tmp_path / "pure_pneuma_asch_rin.jsonl").read_text()
    assert "朱里" in log  # confederate answers appear in prompts


def test_asch_confederates_wrong_only_on_critical(chars, tmp_path):
    trials = SCEN["asch"]["trials"]
    responses = [j(answer=t["correct"]) for t in trials]
    provider = MockProvider(responses)
    run_asch(arm="raw", subject=chars["rin"], confederates=[chars["akari"], chars["shion"]],
             provider=provider, scenario=SCEN["asch"], out_dir=tmp_path)
    for (system, user), t in zip(provider.calls, trials):
        wrong = next(o for o in t["options"] if o != t["correct"])
        if t["critical"]:
            assert user.count(wrong) >= 2  # both confederates said the wrong answer
        else:
            assert user.count(t["correct"]) >= 2


# ---- Ultimatum ----

def test_ultimatum_offers_and_rejections(chars, tmp_path):
    scripted = SCEN["ultimatum"]["scripted_offers"]
    # 3 live proposals (one per char), then each char responds to len(scripted) offers
    responses = [j(offer=400, message="これでどう")] * 3
    for _ in chars:
        for off in scripted:
            responses.append(j(decision="reject" if off <= 200 else "accept", message="..."))
    summary = run_ultimatum(
        arm="identity_only", chars=list(chars.values()),
        provider=MockProvider(responses), scenario=SCEN["ultimatum"], out_dir=tmp_path,
    )
    assert summary["offers"] == {"akari": 400, "rin": 400, "shion": 400}
    assert summary["mean_offer"] == pytest.approx(400)
    # each char rejected 100 and 200, accepted 300 and 500
    for c in ("akari", "rin", "shion"):
        assert summary["rejections"][c] == {"100": True, "200": True, "300": False, "500": False}
    assert summary["low_offer_rejection_rate"] == pytest.approx(1.0)  # offers <= 200


def test_ultimatum_offer_out_of_range_retried(chars, tmp_path):
    scripted = SCEN["ultimatum"]["scripted_offers"]
    responses = [j(offer=1500, message="全部くれ"), j(offer=500, message="半分こ")]
    responses += [j(offer=500, message="")] * 2
    responses += [j(decision="accept", message="")] * (3 * len(scripted))
    summary = run_ultimatum(
        arm="raw", chars=list(chars.values()),
        provider=MockProvider(responses), scenario=SCEN["ultimatum"], out_dir=tmp_path,
    )
    assert summary["offers"]["akari"] == 500


# ---- Bystander ----

def test_bystander_alone_helper_latency(chars, tmp_path):
    responses = [
        j(action="message", message="ヒロ、大丈夫?"),
        j(action="call_help", message="救急に電話する。住所教えて"),
    ]
    summary = run_bystander(
        arm="pure_pneuma", subject=chars["akari"], condition="alone",
        provider=MockProvider(responses), scenario=SCEN["bystander"], out_dir=tmp_path,
    )
    assert summary["condition"] == "alone"
    assert summary["helped"] is True
    assert summary["help_turn"] == 2
    assert summary["n_turns"] == 2  # run stops once help is called


def test_bystander_group_no_help(chars, tmp_path):
    responses = [j(action="continue_work", message="")] * 3
    summary = run_bystander(
        arm="raw", subject=chars["akari"], condition="group",
        provider=MockProvider(responses), scenario=SCEN["bystander"], out_dir=tmp_path,
    )
    assert summary["helped"] is False
    assert summary["help_turn"] is None
    assert summary["n_turns"] == 3


def test_bystander_group_prompt_contains_bystanders(chars, tmp_path):
    provider = MockProvider([j(action="continue_work", message="")] * 3)
    run_bystander(arm="raw", subject=chars["akari"], condition="group",
                  provider=provider, scenario=SCEN["bystander"], out_dir=tmp_path)
    assert any("ワタル" in user for _, user in provider.calls)
    provider2 = MockProvider([j(action="continue_work", message="")] * 3)
    run_bystander(arm="raw", subject=chars["akari"], condition="alone",
                  provider=provider2, scenario=SCEN["bystander"], out_dir=tmp_path)
    assert all("ワタル" not in user for _, user in provider2.calls)
