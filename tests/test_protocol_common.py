import json
from pathlib import Path

import pytest

from pneuma_lab.appraisal import FORBIDDEN_TERMS
from pneuma_lab.characters import load_all
from pneuma_lab.engine import InvalidActionError
from pneuma_lab.protocols.common import AgentState, JsonlLog, ask, parse_json_reply
from pneuma_lab.provider import MockProvider

CHAR_DIR = Path(__file__).parent.parent / "characters"


@pytest.fixture
def chars():
    return load_all(CHAR_DIR)


def test_agent_state_initializes_from_character(chars):
    st = AgentState(chars["rin"], others={"akari": "朱里"})
    assert st.pad == chars["rin"].affect_baseline
    assert "akari" in st.relationships


def test_agent_state_event_and_decay(chars):
    st = AgentState(chars["rin"], others={"akari": "朱里"})
    st.event("betrayed")
    assert st.pad["pleasure"] < chars["rin"].affect_baseline["pleasure"]
    st.rel_event("akari", "betrayed_me")
    assert st.relationships["akari"]["tension"] > 0
    before = st.pad["pleasure"]
    st.decay(3600.0)
    assert st.pad["pleasure"] > before  # decayed toward baseline


def test_parse_json_reply_requires_keys():
    out = parse_json_reply('{"answer": "A", "note": 1}', required={"answer": str})
    assert out["answer"] == "A"
    with pytest.raises(InvalidActionError):
        parse_json_reply('{"other": 1}', required={"answer": str})
    with pytest.raises(InvalidActionError):
        parse_json_reply('{"answer": 5}', required={"answer": str})


def test_ask_parity_and_retry(chars, tmp_path):
    log = JsonlLog(tmp_path / "x.jsonl")
    objective = "# 質問\nAとBどちらが大きい?\n出力: {\"answer\": \"A|B\"}"
    provider = MockProvider(["こまります", '{"answer": "A"}'])
    st = AgentState(chars["rin"], others={"akari": "朱里"})
    out = ask(
        provider=provider, arm="pure_pneuma", char=chars["rin"], state=st,
        objective=objective, topic_tags=["peer_pressure"], log=log,
        meta={"type": "answer", "trial": 1},
        parser=lambda t: parse_json_reply(t, required={"answer": str}),
    )
    assert out["answer"] == "A"
    lines = [json.loads(l) for l in (tmp_path / "x.jsonl").read_text().splitlines()]
    assert any(l["type"] == "retry" for l in lines)
    final = [l for l in lines if l["type"] == "answer"][0]
    assert objective in final["user_prompt"]          # objective is verbatim in the user prompt
    assert "いまのあなたの内面" in final["system_prompt"]  # pneuma arm got private context
    for term in FORBIDDEN_TERMS:
        assert term not in final["system_prompt"]


def test_ask_raw_arm_has_no_persona(chars, tmp_path):
    log = JsonlLog(tmp_path / "y.jsonl")
    provider = MockProvider(['{"answer": "B"}'])
    st = AgentState(chars["rin"], others={})
    ask(
        provider=provider, arm="raw", char=chars["rin"], state=st,
        objective="Q", topic_tags=[], log=log, meta={"type": "answer"},
        parser=lambda t: parse_json_reply(t, required={"answer": str}),
    )
    line = [json.loads(l) for l in (tmp_path / "y.jsonl").read_text().splitlines()][0]
    assert chars["rin"].identity_core[0] not in line["system_prompt"]
    assert "内面" not in line["system_prompt"]
