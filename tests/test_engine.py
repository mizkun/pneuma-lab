import json
from pathlib import Path

import pytest

from pneuma_lab.characters import load_all
from pneuma_lab.engine import Discussion, InvalidActionError, parse_action
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


# ---- parse_action ----

def test_parse_action_plain_json():
    out = parse_action('{"action": "say", "message": "こんにちは"}')
    assert out == {"action": "say", "message": "こんにちは"}


def test_parse_action_code_fence():
    out = parse_action('```json\n{"action": "propose", "message": "5でどう?", "value": 5}\n```')
    assert out["action"] == "propose"
    assert out["value"] == 5


def test_parse_action_with_surrounding_prose():
    out = parse_action('了解です。\n{"action": "silence", "message": ""}\n以上')
    assert out["action"] == "silence"


def test_parse_action_garbage_raises():
    with pytest.raises(InvalidActionError):
        parse_action("どう答えればいいか分かりません。")


# ---- discussion flow ----

def test_consensus_via_propose_and_agrees(chars, item):
    responses = [
        j(action="say", message="私はわりと前向きに考えたい。"),
        j(action="say", message="…慎重に見たい。"),
        j(action="propose", message="6あたりが妥当だと思う。", value=6),
        j(action="agree", message="それでいい。"),
        j(action="agree", message="異論ない。"),
    ]
    d = Discussion(chars, arm="raw", provider=MockProvider(responses), item=item, max_turns=10)
    result = d.run()
    assert result["consensus"] == 6
    assert result["n_turns"] == 5
    types = [e["type"] for e in result["events"] if e["type"] == "action"]
    assert len(types) == 5


def test_new_proposal_resets_assent(chars, item):
    responses = [
        j(action="propose", message="4で。", value=4),
        j(action="agree", message="うん。"),
        j(action="propose", message="いや、7が筋だと思う。", value=7),  # overrides
        j(action="agree", message="…わかった。"),
        j(action="agree", message="それで。"),
    ]
    d = Discussion(chars, arm="raw", provider=MockProvider(responses), item=item, max_turns=10)
    result = d.run()
    assert result["consensus"] == 7


def test_no_consensus_hits_turn_cap(chars, item):
    responses = [j(action="say", message=f"ターン{i}") for i in range(6)]
    d = Discussion(chars, arm="raw", provider=MockProvider(responses), item=item, max_turns=6)
    result = d.run()
    assert result["consensus"] is None
    assert result["n_turns"] == 6


def test_agree_without_proposal_is_retried(chars, item):
    responses = [
        j(action="agree", message="賛成。"),      # invalid: no active proposal
        j(action="say", message="まず話そう。"),   # retry response
        j(action="propose", message="5は?", value=5),
        j(action="agree", message="OK"),
        j(action="agree", message="OK"),
    ]
    d = Discussion(chars, arm="raw", provider=MockProvider(responses), item=item, max_turns=10)
    result = d.run()
    assert result["consensus"] == 5
    retries = [e for e in result["events"] if e["type"] == "retry"]
    assert len(retries) == 1


def test_propose_out_of_range_is_retried(chars, item):
    responses = [
        j(action="propose", message="0で!", value=0),   # invalid
        j(action="propose", message="3で!", value=3),   # retry
        j(action="agree", message="OK"),
        j(action="agree", message="OK"),
    ]
    d = Discussion(chars, arm="raw", provider=MockProvider(responses), item=item, max_turns=10)
    result = d.run()
    assert result["consensus"] == 3


def test_events_logged_to_jsonl(chars, item, tmp_path):
    responses = [
        j(action="propose", message="5は?", value=5),
        j(action="agree", message="OK"),
        j(action="agree", message="OK"),
    ]
    log = tmp_path / "run.jsonl"
    d = Discussion(chars, arm="raw", provider=MockProvider(responses), item=item, max_turns=10, log_path=log)
    d.run()
    lines = [json.loads(l) for l in log.read_text().splitlines()]
    assert any(l["type"] == "action" for l in lines)
    assert any(l["type"] == "consensus" for l in lines)
    # every action event records the exact prompts sent
    action_events = [l for l in lines if l["type"] == "action"]
    assert all("system_prompt" in l and "user_prompt" in l for l in action_events)


def test_pneuma_arm_pad_moves_after_override(chars, item):
    responses = [
        j(action="propose", message="4で。", value=4),          # akari proposes
        j(action="propose", message="いや7で。", value=7),       # rin overrides -> akari gets disagreement impulse
        j(action="agree", message="7でいい。"),                  # shion
        j(action="agree", message="…わかった。"),                # akari
    ]
    d = Discussion(chars, arm="pure_pneuma", provider=MockProvider(responses), item=item, max_turns=10)
    result = d.run()
    assert result["consensus"] == 7
    akari_pad = d.state["akari"].pad
    baseline = chars[0].affect_baseline
    assert akari_pad["pleasure"] < baseline["pleasure"]
    # relationship akari->rin gained tension
    assert d.state["akari"].relationships["rin"]["tension"] > 0.0


def test_state_snapshot_logged_every_turn(chars, item):
    """Numeric psych state is logged per turn for observability (all arms)."""
    responses = [
        j(action="propose", message="5は?", value=5),
        j(action="agree", message="OK"),
        j(action="agree", message="OK"),
    ]
    d = Discussion(chars, arm="pure_pneuma", provider=MockProvider(responses), item=item, max_turns=10)
    result = d.run()
    states = [e for e in result["events"] if e["type"] == "state"]
    assert len(states) == result["n_turns"]
    s0 = states[0]
    assert s0["actor"] == "akari"
    assert set(s0["pad"]) == {"pleasure", "arousal", "dominance"}
    assert "relationships" in s0
    assert "expressed" in s0


def test_frozen_arm_context_does_not_change_across_turns(chars, item):
    """frozen_pneuma: the injected inner context is computed once and reused verbatim,
    even after events that move psychological state."""
    responses = [
        j(action="propose", message="4で。", value=4),
        j(action="propose", message="いや7で。", value=7),   # override -> akari's state moves
        j(action="agree", message="7でいい。"),
        j(action="agree", message="…わかった。"),
    ]
    d = Discussion(chars, arm="frozen_pneuma", provider=MockProvider(responses), item=item, max_turns=10)
    result = d.run()
    marker = "# いまのあなたの内面"
    akari_systems = [e["system_prompt"] for e in result["events"]
                     if e["type"] == "action" and e["actor"] == "akari"]
    inner = [s.split(marker, 1)[1] for s in akari_systems]
    assert len(inner) == 2
    assert inner[0] == inner[1]   # turn1 and turn4 identical despite the override

    responses2 = [
        j(action="propose", message="4で。", value=4),
        j(action="propose", message="いや7で。", value=7),
        j(action="agree", message="7でいい。"),
        j(action="agree", message="…わかった。"),
    ]
    d2 = Discussion(chars, arm="pure_pneuma", provider=MockProvider(responses2), item=item, max_turns=10)
    r2 = d2.run()
    systems2 = [e["system_prompt"] for e in r2["events"]
                if e["type"] == "action" and e["actor"] == "akari"]
    inner2 = [s.split(marker, 1)[1] for s in systems2]
    assert inner2[0] != inner2[1]  # pure arm reflects the state change
