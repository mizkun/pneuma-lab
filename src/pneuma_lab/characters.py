"""Character definitions loaded from JSON (schema shared with the original Pneuma assets)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

OCEAN_KEYS = ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")
PAD_KEYS = ("pleasure", "arousal", "dominance")


@dataclass
class Character:
    character_id: str
    display_name: str
    ocean: dict
    values: dict
    identity_core: list
    negative_constraints: list
    voice_policy: dict
    projects: list
    affect_baseline: dict
    affect_half_life_seconds: float
    self_monitoring_norm: float
    avoidance: float
    role_pressure: dict
    default_disclosure: dict = field(default_factory=dict)


def load_character(path: Path) -> Character:
    raw = json.loads(Path(path).read_text())
    p = raw["personality"]
    return Character(
        character_id=raw["character_id"],
        display_name=raw["display_name"],
        ocean=dict(p["ocean"]),
        values=dict(p["values"]),
        identity_core=list(p["identity_core"]),
        negative_constraints=list(p["negative_constraints"]),
        voice_policy=dict(raw.get("voice_policy", {})),
        projects=list(raw.get("projects", [])),
        affect_baseline=dict(raw["affect_baseline"]),
        affect_half_life_seconds=float(raw.get("affect_half_life_seconds", 3600.0)),
        self_monitoring_norm=float(raw.get("self_monitoring_norm", 0.5)),
        avoidance=float(raw.get("avoidance", 0.5)),
        role_pressure=dict(raw.get("role_pressure", {})),
        default_disclosure=dict(raw.get("default_disclosure", {})),
    )


def load_all(directory: Path) -> dict[str, Character]:
    chars = {}
    for path in sorted(Path(directory).glob("*.json")):
        c = load_character(path)
        chars[c.character_id] = c
    return chars
