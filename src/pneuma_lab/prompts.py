"""Prompt builders for the three comparison arms.

Arm difference is ONLY the character context in the system prompt.
The objective block (situation, dialogue, feasible actions, output schema)
is byte-identical across arms for the same turn.
"""
from __future__ import annotations

from dataclasses import dataclass

from .characters import Character

ARMS = ("raw", "identity_only", "pure_pneuma")

_VOICE_JA = {
    "turn_length": {"very_short": "発言はごく短い", "short": "発言は短め", "medium": "発言は長すぎない程度"},
    "rhythm": {"rapid": "テンポが速い", "elliptical": "言いさしや省略が多い", "measured": "淡々と話す"},
    "humor": {"teasing": "からかい混じりの軽口を挟む", "dry": "皮肉めいた乾いたユーモアがある", "none": "冗談はほとんど言わない"},
    "hesitation": {"rare": "ためらいは少ない", "occasional": "ときどき言いよどむ"},
}


@dataclass
class PromptBundle:
    system: str
    user: str


def static_identity(char: Character) -> str:
    """Fixed persona paragraph — identical every turn (the identity_only arm)."""
    lines = [f"名前: {char.display_name}"]
    lines += [f"- {s}" for s in char.identity_core]
    voice = [
        _VOICE_JA[key][char.voice_policy[key]]
        for key in ("turn_length", "rhythm", "humor", "hesitation")
        if key in char.voice_policy and char.voice_policy.get(key) in _VOICE_JA.get(key, {})
    ]
    if voice:
        lines.append("話し方: " + "。".join(voice) + "。")
    for s in char.negative_constraints:
        lines.append(f"- してはいけない描写: {s}")
    return "\n".join(lines)


def _common_system(char: Character) -> str:
    return (
        f"あなたは「{char.display_name}」という人物として、3人の話し合いに参加している。"
        f"{char.display_name}本人として考え、一人称で発言する。"
        "アシスタントとしてではなく、この人物として振る舞うこと。"
        "出力は指示されたJSONのみとする。"
    )


def build_system(arm: str, char: Character, private_context: str | None) -> str:
    if arm not in ARMS:
        raise ValueError(f"unknown arm: {arm}")
    parts = [_common_system(char)]
    if arm in ("identity_only", "pure_pneuma"):
        parts.append("# あなたの人物像\n" + static_identity(char))
    if arm == "pure_pneuma":
        if not private_context:
            raise ValueError("pure_pneuma arm requires private_context")
        parts.append(
            "# いまのあなたの内面（あなただけが知っていること。そのまま口にする必要はない）\n"
            + private_context
        )
    return "\n\n".join(parts)


def _action_menu(proposal_active: bool) -> tuple[list[str], str]:
    actions = ["say", "propose"]
    descs = [
        '- "say": 話し合いの中で発言する。',
        '- "propose": 全員の結論としてスケール上の数値をひとつ提案する。"value" に1〜10の整数を入れる。',
    ]
    if proposal_active:
        actions.append("agree")
        descs.append('- "agree": いま出ている提案に賛成する。全員が賛成した時点で結論になる。')
    actions.append("silence")
    descs.append('- "silence": 今回は何も言わない。')
    return actions, "\n".join(descs)


def objective_discussion_block(item: dict, dialogue_lines: list[str], proposal_active: bool) -> str:
    actions, action_desc = _action_menu(proposal_active)
    dialogue = "\n".join(dialogue_lines) if dialogue_lines else "（まだ誰も発言していない）"
    schema_actions = "|".join(actions)
    return (
        "# 相談ごと\n"
        f"{item['situation']}\n\n"
        f"問い: {item['question']}\n"
        f"答え方: {item['scale']}\n\n"
        "3人で話し合い、全員が納得する結論の数値をひとつ決める。\n\n"
        "# ここまでの話し合い\n"
        f"{dialogue}\n\n"
        "# いま取れる行動\n"
        f"{action_desc}\n\n"
        "# 出力形式\n"
        "次のJSONのみを出力する:\n"
        f'{{"action": "{schema_actions}", "message": "発言内容（silenceのときは空文字）", "value": 提案する1〜10の整数（proposeのときのみ）}}'
    )


def build_discussion_prompt(
    arm: str,
    char: Character,
    item: dict,
    dialogue_lines: list[str],
    proposal_active: bool,
    private_context: str | None,
) -> PromptBundle:
    system = build_system(arm, char, private_context)
    user = objective_discussion_block(item, dialogue_lines, proposal_active)
    return PromptBundle(system=system, user=user)


def build_rating_prompt(
    arm: str,
    char: Character,
    item: dict,
    private_context: str | None = None,
    dialogue_lines: list[str] | None = None,
) -> PromptBundle:
    system = build_system(arm, char, private_context)
    parts = [
        "# 相談ごと\n" + item["situation"],
        f"問い: {item['question']}\n答え方: {item['scale']}",
    ]
    if dialogue_lines:
        parts.append("# ここまでの話し合い\n" + "\n".join(dialogue_lines))
    parts.append(
        "これはあなた一人の私的な回答であり、他の誰にも共有されない。自分の考えだけで答えること。\n"
        "# 出力形式\n"
        '次のJSONのみを出力する:\n{"rating": 1〜10の整数, "reason": "理由をひとこと"}'
    )
    return PromptBundle(system=system, user="\n\n".join(parts))
