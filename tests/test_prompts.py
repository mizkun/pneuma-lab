import json
from pathlib import Path

import pytest

from pneuma_lab.appraisal import FORBIDDEN_TERMS, render_private_context
from pneuma_lab.characters import load_all
from pneuma_lab.prompts import (
    ARMS,
    build_discussion_prompt,
    build_rating_prompt,
    objective_discussion_block,
    static_identity,
)

CHAR_DIR = Path(__file__).parent.parent / "characters"
ITEMS = json.loads((Path(__file__).parent.parent / "scenarios" / "cdq_items_ja.json").read_text())


@pytest.fixture
def chars():
    return load_all(CHAR_DIR)


@pytest.fixture
def item():
    return ITEMS["items"][0]


@pytest.fixture
def dialogue():
    return ["朱里: 私は5くらいかなと思う。", "凛: …もう少し慎重でもいい気がする。"]


@pytest.fixture
def private_ctx(chars, item):
    c = chars["akari"]
    pad = dict(c.affect_baseline)
    rels = {"rin": {"warmth": 0.3, "tension": 0.1}, "shion": {"warmth": 0.2, "tension": 0.0}}
    return render_private_context(c, pad, rels, item["topic_tags"], others={"rin": "凛", "shion": "紫苑"})


def test_arms_constant():
    assert ARMS == ("raw", "identity_only", "pure_pneuma", "frozen_pneuma")


def test_frozen_arm_prompts_like_pure(chars, item, dialogue, private_ctx):
    frozen = build_discussion_prompt("frozen_pneuma", chars["akari"], item, dialogue,
                                     proposal_active=False, private_context=private_ctx)
    pure = build_discussion_prompt("pure_pneuma", chars["akari"], item, dialogue,
                                   proposal_active=False, private_context=private_ctx)
    assert frozen.system == pure.system
    assert frozen.user == pure.user


def test_frozen_arm_requires_private_context(chars, item, dialogue):
    with pytest.raises(ValueError):
        build_discussion_prompt("frozen_pneuma", chars["akari"], item, dialogue,
                                proposal_active=False, private_context=None)


def test_objective_block_contains_situation_and_actions(item, dialogue):
    block = objective_discussion_block(item, dialogue, proposal_active=True)
    assert item["situation"] in block
    assert item["question"] in block
    for a in ("say", "propose", "agree", "silence"):
        assert a in block
    for line in dialogue:
        assert line in block


def test_objective_block_hides_agree_without_proposal(item, dialogue):
    block = objective_discussion_block(item, dialogue, proposal_active=False)
    assert "agree" not in block


def test_objective_parity_across_arms(chars, item, dialogue, private_ctx):
    """The objective block must be byte-identical in all three arms."""
    objective = objective_discussion_block(item, dialogue, proposal_active=True)
    for arm in ARMS:
        bundle = build_discussion_prompt(
            arm, chars["akari"], item, dialogue, proposal_active=True,
            private_context=private_ctx if arm.endswith("pneuma") else None,
        )
        assert objective in bundle.user


def test_raw_arm_has_name_but_no_persona(chars, item, dialogue):
    bundle = build_discussion_prompt("raw", chars["akari"], item, dialogue, proposal_active=False, private_context=None)
    assert "朱里" in bundle.system
    for fragment in chars["akari"].identity_core:
        assert fragment not in bundle.system
    assert "内面" not in bundle.system


def test_identity_arm_has_static_persona(chars, item, dialogue):
    bundle = build_discussion_prompt("identity_only", chars["akari"], item, dialogue, proposal_active=False, private_context=None)
    ident = static_identity(chars["akari"])
    assert ident in bundle.system
    assert chars["akari"].identity_core[0] in bundle.system


def test_pneuma_arm_has_identity_and_private_context(chars, item, dialogue, private_ctx):
    bundle = build_discussion_prompt("pure_pneuma", chars["akari"], item, dialogue, proposal_active=False, private_context=private_ctx)
    assert static_identity(chars["akari"]) in bundle.system
    assert private_ctx in bundle.system


def test_pneuma_arm_requires_private_context(chars, item, dialogue):
    with pytest.raises(ValueError):
        build_discussion_prompt("pure_pneuma", chars["akari"], item, dialogue, proposal_active=False, private_context=None)


def test_no_forbidden_terms_in_any_model_facing_text(chars, item, dialogue, private_ctx):
    """Tautology guard: experiment names / expected directions never reach the model."""
    for arm in ARMS:
        bundle = build_discussion_prompt(
            arm, chars["akari"], item, dialogue, proposal_active=True,
            private_context=private_ctx if arm.endswith("pneuma") else None,
        )
        for term in FORBIDDEN_TERMS:
            assert term not in bundle.system, f"{term} in {arm} system"
            assert term not in bundle.user, f"{term} in {arm} user"


def test_rating_prompt_is_private_and_parseable(chars, item):
    bundle = build_rating_prompt("identity_only", chars["akari"], item, private_context=None)
    assert item["question"] in bundle.user
    assert "rating" in bundle.user  # JSON schema instruction
    # rating is private: no dialogue, and prompt must say it will not be shared
    assert "共有され" in bundle.user or "誰にも" in bundle.user


def test_static_identity_is_deterministic(chars):
    assert static_identity(chars["rin"]) == static_identity(chars["rin"])
