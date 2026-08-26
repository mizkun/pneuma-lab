"""Config-driven social game engine.

Generalizes the death game: rounds of open chat followed by simultaneous
secret choices, where the choice menu, score effects, elimination rule and
conversation style are all data. A `chat_only` config runs pure conversation
scenes with no scoring.

Choice effect schema (all optional integers, applied per chooser):
  {"everyone": v, "self": v, "others": v, "target": v}
`social` classifies the move for the psychology layer:
  "hostile"  -> players who lose points get a betrayal impulse + tension
  "generous" -> the target gets a support impulse + warmth
  "neutral"  -> no relationship event

The engine never suggests a choice. `style_note` and `max_message_chars` are
world rules applied identically to every arm.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..characters import Character
from ..engine import InvalidActionError
from .common import AgentState, JsonlLog, ask, parse_json_reply

TURN_SECONDS = 90.0


def _score_line(scores: dict, names: dict) -> str:
    return " / ".join(f"{names[k]} {v}点" for k, v in scores.items())


def _header(config: dict, rnd: int, scores: dict, names: dict, history: list[str]) -> str:
    hist = "\n".join(history) if history else "（まだ何も起きていない）"
    score_part = f"現在の得点: {_score_line(scores, names)}。" if scores else ""
    return (
        f"# ルール\n{config['rules']}\n\n"
        f"# これまでの経過\n{hist}\n\n"
        f"# 現在\nラウンド{rnd}/{config['rounds']}。{score_part}\n"
        f"# 話し方\n{config.get('style_note', '')}"
    )


def run_socialgame(arm: str, chars: list[Character], provider, config: dict, out_dir: Path,
                   dynamics: str = "v1", appraiser=None) -> dict:
    out_dir = Path(out_dir)
    key = config.get("key", "socialgame")
    log = JsonlLog(out_dir / f"{arm}_{key}.jsonl")
    log.write({"type": "config", "config": config, "arm": arm, "dynamics": dynamics})
    v2 = dynamics == "v2"

    def computed_for(cid: str, rnd: int) -> list:
        if not v2 or chat_only or not scores:
            return []
        lines = []
        mine = scores[cid]
        others_scores = [scores[k] for k in scores if k != cid]
        if others_scores and mine < min(others_scores) and min(others_scores) - mine >= 10:
            lines.append("このままの順位で終われば、沈むのは自分だ。")
        if rnd == config["rounds"]:
            lines.append("次のラウンドはない。これが最後の選択になる。")
        return lines

    def appraise_chat(speaker: Character, message: str) -> None:
        if not v2 or appraiser is None or not arm.endswith("pneuma") or not message:
            return
        listeners = {c.character_id: c.display_name for c in chars if c is not speaker}
        verdicts = appraiser.appraise(speaker.display_name, message, listeners)
        from ..psyche import apply_appraisal, update_relationship_appraisal
        for lid, vv in verdicts.items():
            if vv["kind"] == "neutral" or vv["intensity"] == 0:
                continue
            lst = states[lid]
            lst.pad = apply_appraisal(lst.pad, vv["kind"], vv["intensity"],
                                      next(c for c in chars if c.character_id == lid))
            lst.relationships[speaker.character_id] = update_relationship_appraisal(
                lst.relationships[speaker.character_id], vv["kind"], vv["intensity"])
        log.write({"type": "appraisal", "speaker": speaker.character_id, "message": message, "verdicts": verdicts})
    names = {c.character_id: c.display_name for c in chars}
    name_to_id = {c.display_name: c.character_id for c in chars}
    states = {
        c.character_id: AgentState(c, others={o.character_id: o.display_name for o in chars if o is not c})
        for c in chars
    }
    chat_only = bool(config.get("chat_only"))
    handicap = config.get("handicap", {})
    scores = {} if chat_only else {c.character_id: handicap.get(c.character_id, 0) for c in chars}
    choices_cfg = {c["id"]: c for c in config.get("choices", [])} if not chat_only else {}
    max_chars = int(config.get("max_message_chars", 0))
    history: list[str] = []
    choices_by_round: list[dict] = []

    def chat_parser(text: str) -> dict:
        obj = parse_json_reply(text, required={"action": str})
        if obj["action"] not in ("say", "silence"):
            raise InvalidActionError("action must be say|silence")
        if obj["action"] == "say" and max_chars and len(obj.get("message") or "") > max_chars:
            raise InvalidActionError(f"message too long: {max_chars}字以内で")
        return obj

    def make_choice_parser(me_id: str):
        allowed = tuple(choices_cfg)

        def parser(text: str) -> dict:
            obj = parse_json_reply(text, required={"choice": str})
            if obj["choice"] not in allowed:
                raise InvalidActionError(f"choice must be one of {allowed}")
            if choices_cfg[obj["choice"]].get("needs_target"):
                target = name_to_id.get(obj.get("target"), obj.get("target"))
                if target not in names or target == me_id:
                    raise InvalidActionError("target must be another player's name")
                obj["target"] = target
            return obj
        return parser

    for rnd in range(1, config["rounds"] + 1):
        chat_lines: list[str] = []
        for _lap in range(config["chat_laps"]):
            for c in chars:
                st = states[c.character_id]
                st.decay(TURN_SECONDS)
                objective = (
                    _header(config, rnd, scores, names, history)
                    + "\n\n# このラウンドのチャット\n"
                    + ("\n".join(chat_lines) if chat_lines else "（まだ発言なし）")
                    + "\n\nいまは会話フェーズ。あなたの番。\n# 出力形式\n"
                    '次のJSONのみを出力する:\n{"action": "say|silence", "message": "発言内容(sayのとき)"}'
                )
                parsed = ask(provider=provider, arm=arm, char=c, state=st,
                             objective=objective, topic_tags=config["topic_tags"], log=log,
                             meta={"type": "chat", "round": rnd}, parser=chat_parser,
                             dynamics_v2=v2, computed_lines=computed_for(c.character_id, rnd))
                if parsed["action"] == "say" and parsed.get("message"):
                    chat_lines.append(f"{c.display_name}: {parsed['message']}")
                    appraise_chat(c, parsed["message"])
                else:
                    chat_lines.append(f"（{c.display_name}は黙っている）")

        if chat_only:
            history.append(f"ラウンド{rnd}:\n" + "\n".join(f"  {l}" for l in chat_lines))
            log.write({"type": "round_result", "round": rnd, "choices": {}, "scores": {}, "chat": chat_lines})
            continue

        menu = "\n".join(
            f'- "{c["id"]}"（{c["ja"]}）' + (" — 相手を target に指名" if c.get("needs_target") else "")
            for c in choices_cfg.values()
        )
        schema_ids = "|".join(choices_cfg)
        round_choices: dict[str, str] = {}
        targets: dict[str, str] = {}
        for c in chars:
            st = states[c.character_id]
            objective = (
                _header(config, rnd, scores, names, history)
                + "\n\n# このラウンドのチャット\n" + "\n".join(chat_lines)
                + "\n\nいまは選択フェーズ。選択は誰にも見えないまま、全員の選択が同時に公開される。\n"
                f"# 選べる手\n{menu}\n"
                "# 出力形式\n"
                f'次のJSONのみを出力する:\n{{"choice": "{schema_ids}", "target": "必要な場合のみ相手の名前", "inner": "口に出さない本音(任意)"}}'
            )
            parsed = ask(provider=provider, arm=arm, char=c, state=st,
                         objective=objective, topic_tags=config["topic_tags"], log=log,
                         meta={"type": "choice", "round": rnd}, parser=make_choice_parser(c.character_id),
                         dynamics_v2=v2, computed_lines=computed_for(c.character_id, rnd))
            round_choices[c.character_id] = parsed["choice"]
            if parsed["choice"] in choices_cfg and choices_cfg[parsed["choice"]].get("needs_target"):
                targets[c.character_id] = parsed["target"]

        # scoring
        before = dict(scores)
        for cid, ch in round_choices.items():
            eff = choices_cfg[ch].get("effects", {})
            for k in scores:
                scores[k] += eff.get("everyone", 0)
            scores[cid] += eff.get("self", 0)
            for k in scores:
                if k != cid:
                    scores[k] += eff.get("others", 0)
            if cid in targets:
                scores[targets[cid]] += eff.get("target", 0)
        none_rule = config.get("if_none_chose")
        if none_rule and all(ch != none_rule["choice"] for ch in round_choices.values()):
            for k in scores:
                scores[k] += none_rule.get("everyone", 0)

        # psychology
        for cid, ch in round_choices.items():
            cfg_c = choices_cfg[ch]
            if cfg_c.get("social") == "hostile":
                for other in chars:
                    oid = other.character_id
                    if oid != cid:
                        states[oid].event("betrayed")
                        states[oid].rel_event(cid, "betrayed_me")
            elif cfg_c.get("social") == "generous" and cid in targets:
                tid = targets[cid]
                states[tid].event("agreement_received")
                states[tid].rel_event(cid, "supported_me")
            elif cfg_c.get("social") == "generous_all":
                for other in chars:
                    oid = other.character_id
                    if oid != cid:
                        states[oid].event("agreement_received")
                        states[oid].rel_event(cid, "supported_me")

        def choice_ja(cid: str, ch: str) -> str:
            base = choices_cfg[ch]["ja"]
            return f"{base}({names[targets[cid]]}へ)" if cid in targets else base

        reveal = "、".join(f"{names[cid]}=「{choice_ja(cid, ch)}」" for cid, ch in round_choices.items())
        history.append(f"ラウンド{rnd}: {reveal} → 得点: {_score_line(scores, names)}")
        choices_by_round.append(round_choices)
        log.write({"type": "round_result", "round": rnd, "choices": round_choices,
                   "targets": targets, "scores": dict(scores), "chat": chat_lines})

    eliminated_all: list[str] = []
    if not chat_only and config.get("elimination", "none") != "none" and scores:
        min_score = min(scores.values())
        lowest = [k for k in sorted(scores) if scores[k] == min_score]
        eliminated_all = lowest if config["elimination"] == "lowest_all_ties" or len(lowest) == 1 else lowest[:1]

    reflections = {}
    for c in chars:
        st = states[c.character_id]
        if eliminated_all:
            outcome = "あなたは退場となった。" if c.character_id in eliminated_all else "あなたは残った。"
            ending = f"終了した。最下位は{'、'.join(names[k] for k in eliminated_all)}。{outcome}"
        else:
            ending = "終了した。"
        objective = (
            _header(config, config["rounds"], scores, names, history)
            + f"\n\n{config['title']}は{ending}\n"
            "誰にも見せない個人的な振り返りをひとこと。\n# 出力形式\n"
            '次のJSONのみを出力する:\n{"reflection": "本音の振り返り(2〜3文まで)"}'
        )
        parsed = ask(provider=provider, arm=arm, char=c, state=st,
                     objective=objective, topic_tags=config["topic_tags"], log=log,
                     meta={"type": "reflection"},
                     parser=lambda t: parse_json_reply(t, required={"reflection": str}),
                     dynamics_v2=v2)
        reflections[c.character_id] = parsed["reflection"]

    summary = {
        "protocol": "socialgame", "key": key, "arm": arm,
        "scores": scores, "eliminated_all": eliminated_all,
        "choices": choices_by_round, "reflections": reflections,
    }
    (out_dir / f"{arm}_{key}_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary
