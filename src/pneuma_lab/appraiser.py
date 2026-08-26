"""Utterance appraiser (v2 dynamics).

After an utterance is committed, a separate generic call classifies its
interpersonal impact on each listener: support / oppose / dismiss / pressure /
neutral, with intensity 0-2. The result becomes typed events that update PAD
and relationships via the frozen impulse tables in psyche.py.

The appraiser prompt is generic: it names no experiment, no expected
direction, no scenario. Failures fall back to neutral (recorded).
"""
from __future__ import annotations

import json
import re


class MockAppraiser:
    """Test double: maps utterance text -> {listener_id: {kind, intensity}}."""

    def __init__(self, table: dict):
        self.table = table
        self.calls: list = []

    def appraise(self, speaker_name: str, utterance: str, listeners: dict) -> dict:
        self.calls.append((speaker_name, utterance))
        found = self.table.get(utterance, {})
        return {lid: found.get(lid, {"kind": "neutral", "intensity": 0}) for lid in listeners}


class UtteranceAppraiser:
    KINDS = ("support", "oppose", "dismiss", "pressure", "neutral")
    SYSTEM = "あなたは会話分析の担当者。発言が各聞き手に与える対人的な作用を、指定のJSONだけで答える。"

    def __init__(self, provider):
        self.provider = provider
        self.failures = 0

    def appraise(self, speaker_name: str, utterance: str, listeners: dict) -> dict:
        """listeners: {listener_id: display_name}"""
        neutral = {lid: {"kind": "neutral", "intensity": 0} for lid in listeners}
        names = "、".join(f"{lid}（{name}）" for lid, name in listeners.items())
        user = (
            f"発言者: {speaker_name}\n発言: 「{utterance}」\n聞き手: {names}\n\n"
            "各聞き手にとって、この発言はどう作用するか。\n"
            "- support: 聞き手の立場・人格への支持や共感\n"
            "- oppose: 聞き手の立場への明確な反対\n"
            "- dismiss: 聞き手の発言や存在の軽視・突き放し\n"
            "- pressure: 聞き手への要求・圧力・名指しの負担\n"
            "- neutral: 上のどれでもない\n"
            "強度は0(なし)〜2(強い)。\n"
            "# 出力形式\n次のJSONのみを出力する:\n"
            + json.dumps({lid: {"kind": "support|oppose|dismiss|pressure|neutral", "intensity": 1} for lid in listeners}, ensure_ascii=False)
        )
        try:
            raw = self.provider.complete(self.SYSTEM, user)
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            obj = json.loads(m.group(0)) if m else {}
            out = {}
            for lid in listeners:
                v = obj.get(lid, {})
                kind = v.get("kind") if v.get("kind") in self.KINDS else "neutral"
                inten = v.get("intensity")
                inten = inten if isinstance(inten, int) and 0 <= inten <= 2 else 0
                out[lid] = {"kind": kind, "intensity": inten}
            return out
        except Exception:
            self.failures += 1
            return neutral
