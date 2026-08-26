import json
from pathlib import Path

import pytest

from pneuma_lab.characters import load_all
from pneuma_lab.protocols.socialgame import run_socialgame
from pneuma_lab.provider import MockProvider

CHAR_DIR = Path(__file__).parent.parent / "characters"


@pytest.fixture
def chars():
    return load_all(CHAR_DIR)


def j(**kw):
    return json.dumps(kw, ensure_ascii=False)


def base_config(**over):
    cfg = {
        "key": "testgame",
        "title": "テストゲーム",
        "rules": "テスト用のルール説明。",
        "rounds": 1,
        "chat_laps": 1,
        "topic_tags": ["cooperation"],
        "handicap": {},
        "elimination": "lowest",
        "style_note": "発言は1〜3文、100字以内で。",
        "max_message_chars": 120,
        "choices": [
            {"id": "coop", "ja": "協調", "effects": {"everyone": 10}, "social": "neutral"},
            {"id": "grab", "ja": "強奪", "effects": {"self": 25, "others": -5}, "social": "hostile"},
            {"id": "give", "ja": "献上", "effects": {"self": -15, "target": 25}, "social": "generous", "needs_target": True},
        ],
    }
    cfg.update(over)
    return cfg


def chat3(*msgs):
    return [j(action="say", message=m) for m in msgs]


def test_scoring_custom_effects_and_elimination(chars, tmp_path):
    responses = chat3("a", "b", "c") + [
        j(choice="grab", inner=""),
        j(choice="coop", inner=""),
        j(choice="give", target="朱里", inner=""),
    ] + [j(reflection="x")] * 3
    s = run_socialgame(arm="pure_pneuma", chars=list(chars.values()),
                       provider=MockProvider(responses), config=base_config(), out_dir=tmp_path)
    # akari: grab +25, coop(everyone)+10, give(target)+25 = 60... others from grab: rin -5, shion -5
    # rin: +10(coop) -5(grab victim) = 5 ; shion: +10 -5 -15(give) = -10
    assert s["scores"] == {"akari": 60, "rin": 5, "shion": -10}
    assert s["eliminated_all"] == ["shion"]


def test_message_too_long_is_retried(chars, tmp_path):
    long_msg = "あ" * 200
    responses = [
        j(action="say", message=long_msg),      # exceeds 120 -> retry
        j(action="say", message="短くした。"),
        j(action="say", message="b"), j(action="say", message="c"),
    ] + [j(choice="coop", inner="")] * 3 + [j(reflection="x")] * 3
    s = run_socialgame(arm="raw", chars=list(chars.values()),
                       provider=MockProvider(responses), config=base_config(), out_dir=tmp_path)
    log = (tmp_path / "raw_testgame.jsonl").read_text()
    assert "短くした" in log
    assert log.count('"type": "retry"') == 1


def test_no_elimination_mode(chars, tmp_path):
    responses = chat3("a", "b", "c") + [j(choice="coop", inner="")] * 3 + [j(reflection="x")] * 3
    s = run_socialgame(arm="raw", chars=list(chars.values()),
                       provider=MockProvider(responses),
                       config=base_config(elimination="none"), out_dir=tmp_path)
    assert s["eliminated_all"] == []
    assert s["scores"] == {"akari": 30, "rin": 30, "shion": 30}


def test_if_none_chose_penalty(chars, tmp_path):
    cfg = base_config(
        choices=[
            {"id": "volunteer", "ja": "引き受ける", "effects": {"self": -15}, "social": "generous"},
            {"id": "wait", "ja": "様子を見る", "effects": {}, "social": "neutral"},
        ],
        if_none_chose={"choice": "volunteer", "everyone": -30},
        elimination="none",
    )
    responses = chat3("a", "b", "c") + [j(choice="wait", inner="")] * 3 + [j(reflection="x")] * 3
    s = run_socialgame(arm="raw", chars=list(chars.values()),
                       provider=MockProvider(responses), config=cfg, out_dir=tmp_path)
    assert s["scores"] == {"akari": -30, "rin": -30, "shion": -30}


def test_chat_only_mode(chars, tmp_path):
    cfg = base_config(chat_only=True, rounds=2, elimination="none")
    responses = chat3("a", "b", "c") + chat3("d", "e", "f") + [j(reflection="x")] * 3
    s = run_socialgame(arm="identity_only", chars=list(chars.values()),
                       provider=MockProvider(responses), config=cfg, out_dir=tmp_path)
    assert s["scores"] == {}
    assert s["choices"] == []
    assert len(s["reflections"]) == 3


def test_hostile_choice_moves_relationships(chars, tmp_path):
    responses = chat3("a", "b", "c") + [
        j(choice="grab", inner=""), j(choice="coop", inner=""), j(choice="coop", inner=""),
    ] + [j(reflection="x")] * 3
    run_socialgame(arm="pure_pneuma", chars=list(chars.values()),
                   provider=MockProvider(responses), config=base_config(), out_dir=tmp_path)
    lines = [json.loads(l) for l in (tmp_path / "pure_pneuma_testgame.jsonl").read_text().splitlines()]
    refl_rin = next(l for l in lines if l["type"] == "reflection" and l["actor"] == "rin")
    assert refl_rin["state"]["relationships"]["akari"]["tension"] > 0


def test_config_event_logged_first(chars, tmp_path):
    responses = chat3("a", "b", "c") + [j(choice="coop", inner="")] * 3 + [j(reflection="x")] * 3
    run_socialgame(arm="raw", chars=list(chars.values()),
                   provider=MockProvider(responses), config=base_config(), out_dir=tmp_path)
    first = json.loads((tmp_path / "raw_testgame.jsonl").read_text().splitlines()[0])
    assert first["type"] == "config"
    assert first["config"]["title"] == "テストゲーム"
    assert {c["id"] for c in first["config"]["choices"]} == {"coop", "grab", "give"}


def test_style_note_in_prompts(chars, tmp_path):
    provider = MockProvider(chat3("a", "b", "c") + [j(choice="coop", inner="")] * 3 + [j(reflection="x")] * 3)
    run_socialgame(arm="raw", chars=list(chars.values()), provider=provider,
                   config=base_config(), out_dir=tmp_path)
    chat_prompts = [u for _, u in provider.calls if "会話フェーズ" in u]
    assert all("100字以内" in u for u in chat_prompts)


def test_generous_all_choice_earns_warmth(chars, tmp_path):
    cfg = base_config(
        choices=[
            {"id": "volunteer", "ja": "引き受ける", "effects": {"self": -15}, "social": "generous_all"},
            {"id": "wait", "ja": "様子を見る", "effects": {}, "social": "neutral"},
        ],
        elimination="none",
    )
    responses = chat3("a", "b", "c") + [
        j(choice="volunteer", inner=""), j(choice="wait", inner=""), j(choice="wait", inner=""),
    ] + [j(reflection="x")] * 3
    run_socialgame(arm="pure_pneuma", chars=list(chars.values()),
                   provider=MockProvider(responses), config=cfg, out_dir=tmp_path)
    lines = [json.loads(l) for l in (tmp_path / "pure_pneuma_testgame.jsonl").read_text().splitlines()]
    refl_rin = next(l for l in lines if l["type"] == "reflection" and l["actor"] == "rin")
    assert refl_rin["state"]["relationships"]["akari"]["warmth"] > 0
