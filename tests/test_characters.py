from pathlib import Path

import pytest

from pneuma_lab.characters import Character, load_all, load_character

CHAR_DIR = Path(__file__).parent.parent / "characters"


def test_load_character_akari():
    c = load_character(CHAR_DIR / "akari.json")
    assert isinstance(c, Character)
    assert c.character_id == "akari"
    assert c.display_name == "朱里"
    assert set(c.ocean) == {"openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"}
    assert all(0.0 <= v <= 1.0 for v in c.ocean.values())
    assert len(c.identity_core) >= 1
    assert len(c.negative_constraints) >= 1
    assert set(c.affect_baseline) == {"pleasure", "arousal", "dominance"}
    assert 0.0 <= c.self_monitoring_norm <= 1.0
    assert 0.0 <= c.avoidance <= 1.0
    assert "social" in c.role_pressure


def test_load_all_three_characters():
    chars = load_all(CHAR_DIR)
    assert set(chars) == {"akari", "rin", "shion"}
    names = {c.display_name for c in chars.values()}
    assert names == {"朱里", "凛", "紫苑"}


def test_projects_have_modulation():
    c = load_character(CHAR_DIR / "rin.json")
    assert len(c.projects) >= 1
    for p in c.projects:
        assert "modulation" in p
        assert 0.0 <= p["activation"] <= 1.0


def test_load_character_missing_file():
    with pytest.raises(FileNotFoundError):
        load_character(CHAR_DIR / "nobody.json")
