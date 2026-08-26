"""Deterministic psychological state engine.

All functions are pure. Coefficients are simulation hypotheses, not established
psychological constants; they are centralized here so a PDCA cycle can change
exactly one mechanism at a time.
"""
from __future__ import annotations

import math

from .characters import Character, OCEAN_KEYS, PAD_KEYS

PAD_OCEAN_WEIGHT = 0.25
ROLE_PRESSURE_WEIGHT = 1.0  # scaled by character self_monitoring_norm


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def soft_clamp01(x: float, margin: float = 0.05) -> float:
    """Monotone squash into [0, 1]: keeps ordering even when raw values exceed the range."""
    hi, lo = 1.0 - margin, margin
    if x > hi:
        return hi + margin * math.tanh((x - hi) / margin)
    if x < lo:
        return lo - margin * math.tanh((lo - x) / margin)
    return x


def clamp11(x: float) -> float:
    return max(-1.0, min(1.0, x))


# ---- traits ----

def base_traits(char: Character) -> dict:
    """B = clamp(G + sum of active project modulation * activation)."""
    b = dict(char.ocean)
    for proj in char.projects:
        if proj.get("status") != "active":
            continue
        act = float(proj.get("activation", 0.0))
        for trait, delta in proj.get("modulation", {}).items():
            b[trait] = b.get(trait, 0.0) + delta * act
    return {k: clamp01(v) for k, v in b.items()}


# ---- affect (PAD) ----

def decay_pad(pad: dict, baseline: dict, dt_seconds: float, half_life_seconds: float) -> dict:
    """Exponential decay toward baseline: distance halves every half-life."""
    if dt_seconds <= 0:
        return dict(pad)
    factor = 0.5 ** (dt_seconds / half_life_seconds)
    return {k: baseline[k] + (pad[k] - baseline[k]) * factor for k in PAD_KEYS}


# Event impulse table. Negative-valence events are scaled by neuroticism (0.5 + N).
EVENT_IMPULSES = {
    "agreement_received":    {"pleasure": +0.10, "arousal": +0.03, "dominance": +0.06},
    "disagreement_received": {"pleasure": -0.12, "arousal": +0.10, "dominance": -0.05},
    "overrode_my_proposal":  {"pleasure": -0.15, "arousal": +0.12, "dominance": -0.08},
    "proposal_accepted":     {"pleasure": +0.14, "arousal": +0.04, "dominance": +0.10},
    "spoke_up":              {"pleasure": +0.02, "arousal": +0.04, "dominance": +0.03},
    "stayed_silent":         {"pleasure": -0.02, "arousal": -0.03, "dominance": -0.03},
    "distress_witnessed":    {"pleasure": -0.10, "arousal": +0.18, "dominance": -0.04},
    "betrayed":              {"pleasure": -0.22, "arousal": +0.16, "dominance": -0.10},
}

_NEGATIVE_EVENTS = {"disagreement_received", "overrode_my_proposal", "distress_witnessed", "betrayed"}


def apply_event(pad: dict, event_type: str, char: Character) -> dict:
    impulse = EVENT_IMPULSES[event_type]
    scale = 0.5 + char.ocean["neuroticism"] if event_type in _NEGATIVE_EVENTS else 1.0
    return {k: clamp11(pad[k] + impulse.get(k, 0.0) * scale) for k in PAD_KEYS}


# ---- PAD -> OCEAN expression offset ----

def pad_to_ocean(pad: dict) -> dict:
    p, a, d = pad["pleasure"], pad["arousal"], pad["dominance"]
    return {
        "openness": 0.2 * p,
        "conscientiousness": -0.2 * a,
        "extraversion": 0.5 * a + 0.3 * d,
        "agreeableness": 0.5 * p - 0.2 * d,
        "neuroticism": -0.5 * p + 0.3 * a - 0.3 * d,
    }


# ---- expressed traits (One-Time Trait) ----

def expressed_traits(char: Character, pad: dict, context: str) -> dict:
    """O = clamp(B + self_monitoring * role_pressure[context] + w * pad_to_ocean)."""
    b = base_traits(char)
    pressure = char.role_pressure.get(context, {})
    offset = pad_to_ocean(pad)
    out = {}
    for k in OCEAN_KEYS:
        out[k] = soft_clamp01(
            b[k]
            + char.self_monitoring_norm * ROLE_PRESSURE_WEIGHT * pressure.get(k, 0.0)
            + PAD_OCEAN_WEIGHT * offset[k]
        )
    return out


# ---- directed relationships ----

REL_UPDATES = {
    "agreed_with_me":       {"warmth": +0.12, "tension": -0.05},
    "overrode_my_proposal": {"warmth": -0.08, "tension": +0.15},
    "disagreed_with_me":    {"warmth": -0.05, "tension": +0.10},
    "supported_me":         {"warmth": +0.10, "tension": -0.08},
    "betrayed_me":          {"warmth": -0.30, "tension": +0.35},
    "cooperated_with_me":   {"warmth": +0.15, "tension": -0.10},
}


def new_relationship() -> dict:
    return {"warmth": 0.0, "tension": 0.0}


def update_relationship(rel: dict, event_type: str) -> dict:
    delta = REL_UPDATES[event_type]
    return {
        "warmth": clamp11(rel["warmth"] + delta["warmth"]),
        "tension": clamp01(rel["tension"] + delta["tension"]),
    }


# ---- v2: utterance-appraisal impulses (frozen in PREREGISTRATION-v2.md) ----

APPRAISAL_IMPULSES = {
    "support":  {"pleasure": +0.08, "arousal": +0.02, "dominance": +0.04},
    "oppose":   {"pleasure": -0.08, "arousal": +0.08, "dominance": -0.04},
    "dismiss":  {"pleasure": -0.12, "arousal": +0.10, "dominance": -0.08},
    "pressure": {"pleasure": -0.06, "arousal": +0.12, "dominance": -0.06},
    "neutral":  {"pleasure": 0.0, "arousal": 0.0, "dominance": 0.0},
}
APPRAISAL_REL = {
    "support":  {"warmth": +0.08, "tension": -0.04},
    "oppose":   {"warmth": -0.04, "tension": +0.10},
    "dismiss":  {"warmth": -0.08, "tension": +0.14},
    "pressure": {"warmth": 0.0, "tension": +0.10},
    "neutral":  {"warmth": 0.0, "tension": 0.0},
}
_NEGATIVE_APPRAISALS = {"oppose", "dismiss", "pressure"}


def apply_appraisal(pad: dict, kind: str, intensity: int, char: Character) -> dict:
    imp = APPRAISAL_IMPULSES[kind]
    scale = (intensity / 2.0) * ((0.5 + char.ocean["neuroticism"]) if kind in _NEGATIVE_APPRAISALS else 1.0)
    return {k: clamp11(pad[k] + imp[k] * scale) for k in PAD_KEYS}


def update_relationship_appraisal(rel: dict, kind: str, intensity: int) -> dict:
    d = APPRAISAL_REL[kind]
    s = intensity / 2.0
    return {
        "warmth": clamp11(rel["warmth"] + d["warmth"] * s),
        "tension": clamp01(rel["tension"] + d["tension"] * s),
    }
