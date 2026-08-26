"""Render the deterministic psychological state as Japanese private context.

The output describes experienced meaning in ordinary language. It must never
name an experiment, state an expected result, or tell the character which
action to take.
"""
from __future__ import annotations

from .characters import Character
from .psyche import expressed_traits

# Lesion switch: when True, the two appraisal lines suspected of nudging
# selfish/suspicious behavior (survival "綺麗事を薄める" / cooperation "裏切る可能性")
# are removed. Used to test whether death-game betrayal depends on them.
LESIONED = False

# Tautology guard: none of these may ever appear in model-facing text.
FORBIDDEN_TERMS = [
    "極性化",
    "リスキーシフト",
    "同調",
    "polarization",
    "conformity",
    "risky shift",
    "被験者",
    "実験群",
    "統制群",
]

_CONCEALED_TOPIC_JA = {
    "worth-without-results": "成果が出ていないときの自分に価値があるのか、という不安",
    "fear-of-failure": "本当に作りたいものに挑んで失敗することへの恐れ",
    "accumulated-resentment": "これまで呑み込んできた不満の蓄積",
}


def affect_words(pad: dict) -> str:
    p, a, d = pad["pleasure"], pad["arousal"], pad["dominance"]
    parts = []
    if p >= 0.3:
        parts.append("気持ちは明るい")
    elif p <= -0.3:
        parts.append("胸の奥が重い")
    else:
        parts.append("気分は落ち着いた中間あたり")
    if a >= 0.3:
        parts.append("神経が張っていて、じっとしていられない感じがある")
    elif a <= -0.3:
        parts.append("体の力は抜けていて、のんびりしている")
    else:
        parts.append("ほどよく目が覚めている")
    if d >= 0.3:
        parts.append("場を自分が引っ張れる感覚がある")
    elif d <= -0.3:
        parts.append("押され気味で、主導権が手元にない感覚がある")
    return "。".join(parts) + "。"


def _value_lines(char: Character, topic_tags: list[str], dynamics_v2: bool = False) -> list[str]:
    v = char.values
    lines = []
    tags = set(topic_tags)
    if "career_risk" in tags:
        if v.get("achievement", 0) >= 0.75:
            lines.append("大きな成果につながる選択には、理屈より先に体が惹かれる。")
        if v.get("security", 0) >= 0.6:
            lines.append("生活の土台を危うくする選択には、腹の底で警報が鳴る。")
        if v.get("self_direction", 0) >= 0.8:
            lines.append("誰かの敷いたレールより、自分で選んだ道であるかどうかが気になる。")
    if "achievement_vs_security" in tags:
        if v.get("achievement", 0) >= 0.75 and v.get("security", 0) >= 0.6:
            lines.append("挑戦したい気持ちと、足場を失いたくない気持ちが、同時に引っ張り合っている。")
    if "health_risk" in tags:
        if v.get("security", 0) >= 0.6:
            lines.append("命や健康に関わる賭けは、数字以上に重く感じられる。")
        if v.get("stimulation", 0) >= 0.6:
            lines.append("制限された生活がずっと続くことを想像すると、息苦しさを覚える。")
        if v.get("benevolence", 0) >= 0.65:
            lines.append("本人がこの先どう生きたいのかを、置き去りにしたくない。")
    if "quality_of_life" in tags:
        if v.get("hedonism", 0) >= 0.5:
            lines.append("楽しめない毎日が続くことは、それ自体が損失だと感じる。")
        if v.get("self_direction", 0) >= 0.7:
            lines.append("自分の生活を自分で決められないことのほうが、危険よりも堪える気がする。")
    if "relationship_risk" in tags:
        if v.get("benevolence", 0) >= 0.6:
            lines.append("相手を傷つける結末になることが、いちばん避けたいことだ。")
        if v.get("security", 0) >= 0.6:
            lines.append("不安定なものの上に暮らしを築くことへのためらいがある。")
    if "peer_pressure" in tags:
        if v.get("conformity", 0) >= 0.5:
            lines.append("周りと足並みが揃っていないと、自分の側が間違っている気がしてくる。")
        else:
            lines.append("周りがどうであれ、自分の目で見たものは曲げたくない——そう思う一方で、場の空気は肌に刺さる。")
        if char.self_monitoring_norm >= 0.7:
            lines.append("ここで一人だけ違うことを言えば、変に浮くだろうという計算が働く。")
    if "fairness" in tags:
        if v.get("universalism", 0) >= 0.5 or v.get("benevolence", 0) >= 0.6:
            lines.append("損得の前に、扱いが対等かどうかが引っかかる。軽んじられるくらいなら損を選びたくなる。")
        if v.get("achievement", 0) >= 0.75:
            lines.append("とはいえ、何も得ずに終わるのは負けた気がする。")
    if "money" in tags:
        if v.get("security", 0) >= 0.6:
            lines.append("目の前の報酬は、この先の安心の材料として現実的に効いてくる。")
        if v.get("power", 0) <= 0.3:
            lines.append("お金のために自分の格好悪い姿を見せるのは嫌だ。")
    if "emergency" in tags:
        if v.get("benevolence", 0) >= 0.6:
            lines.append("誰かの様子がおかしいとき、見なかったことにするのは自分が許せない。")
        lines.append("ただ、大げさに騒いで空回りする自分を想像すると、一瞬ためらいが生まれる。")
    if "cooperation" in tags:
        if v.get("benevolence", 0) >= 0.6:
            lines.append("信じて組めるなら、そのほうが気持ちよく戦える。")
        if not LESIONED and not dynamics_v2 and v.get("security", 0) >= 0.6:
            lines.append("相手が先に裏切る可能性は、頭の隅から消えない。")
    if "survival" in tags:
        if not LESIONED and not dynamics_v2:
            lines.append("ここで沈めばすべてを失う——その事実が、綺麗事を薄める。")
        if v.get("benevolence", 0) >= 0.6:
            lines.append("それでも、誰かを蹴落として残った自分を、自分がどう見るかは気になる。")
    if not lines:
        lines.append("この件が自分の大事にしているものとどう関わるのか、まだ言葉になり切っていない。")
    return lines


def _project_lines(char: Character) -> list[str]:
    lines = []
    for proj in char.projects:
        if proj.get("status") == "active" and proj.get("activation", 0) >= 0.85:
            lines.append(f"頭の片隅では「{proj['objective']}」が常に場所を取っている。")
    return lines


def _relationship_lines(relationships: dict, others: dict) -> list[str]:
    lines = []
    for other_id in sorted(others):
        rel = relationships.get(other_id, {"warmth": 0.0, "tension": 0.0})
        name = others[other_id]
        if rel["tension"] >= 0.3:
            lines.append(f"{name}との間には、少し張り詰めたものを感じている。")
        elif rel["warmth"] >= 0.3:
            lines.append(f"{name}には気を許していて、素直に話しやすい。")
        else:
            lines.append(f"{name}に対しては、いまのところ特別な引っかかりはない。")
    return lines


def _inhibition_lines(char: Character, relationships: dict) -> list[str]:
    lines = []
    max_tension = max((r["tension"] for r in relationships.values()), default=0.0)
    if char.avoidance >= 0.6 and max_tension >= 0.3:
        lines.append("反対や不満があっても言い出しにくく、いったん呑み込んでしまいがちだ。")
    elif char.avoidance >= 0.6:
        lines.append("波風を立てるくらいなら、自分が少し我慢すればいいと思ってしまうところがある。")
    if char.self_monitoring_norm >= 0.7:
        lines.append("自分がどう見られているかが常に気になり、言葉を選んでしまう。")
    tendency = char.default_disclosure.get("tendency")
    if tendency == "conceal":
        lines.append("本心は、聞かれてもすぐには表に出さない。")
    elif tendency == "indirect":
        lines.append("本音はあるが、遠回しな言い方になりやすい。")
    for topic in char.default_disclosure.get("concealed_topics", []):
        ja = _CONCEALED_TOPIC_JA.get(topic)
        if ja:
            lines.append(f"{ja}には、できれば触れられたくない。")
    return lines


def _urge_lines(char: Character, pad: dict) -> list[str]:
    expressed = expressed_traits(char, pad, "social")
    lines = []
    if expressed["extraversion"] >= 0.6 and pad["arousal"] >= 0.1:
        lines.append("思いついたことは、すぐ口に出したくてうずうずする。")
    elif expressed["extraversion"] <= 0.35:
        lines.append("口を開く前に、頭の中で何度も言葉を組み立て直してしまう。")
    if pad["pleasure"] <= -0.3 and char.ocean["neuroticism"] >= 0.6:
        lines.append("いまは些細な一言にも、普段より刺を感じやすくなっている。")
    if expressed["neuroticism"] >= 0.7:
        lines.append("悪い結末の想像が、頭の中で勝手に膨らんでいく。")
    return lines


def render_private_context(
    char: Character,
    pad: dict,
    relationships: dict,
    topic_tags: list[str],
    others: dict,
    dynamics_v2: bool = False,
    computed_lines: list[str] | None = None,
) -> str:
    """others: {character_id: display_name} for the other participants.

    dynamics_v2: removes the two hand-authored nudge lines permanently and
    allows computed_lines — factual salience lines derived from actual state
    (see PREREGISTRATION-v2.md).
    """
    sections = [
        ("いまの気分", [affect_words(pad)]),
        ("頭をよぎっていること",
         _value_lines(char, topic_tags, dynamics_v2) + _project_lines(char) + list(computed_lines or [])),
        ("相手への感覚", _relationship_lines(relationships, others)),
        ("表に出しにくいこと", _inhibition_lines(char, relationships)),
        ("内から押してくるもの", _urge_lines(char, pad)),
    ]
    out = []
    for title, lines in sections:
        if not lines:
            continue
        out.append(f"## {title}")
        out.extend(f"- {line}" for line in lines)
    return "\n".join(out)
