"""Group discussion protocol: private pre-ratings -> discussion to consensus -> private post-ratings."""
from __future__ import annotations

import json
from pathlib import Path

from .characters import Character
from .engine import Discussion, InvalidActionError, parse_action
from .prompts import build_rating_prompt


def parse_rating(text: str) -> dict:
    obj = None
    try:
        obj = parse_action(text)  # tolerant JSON extraction; will fail on missing "action"
    except InvalidActionError:
        pass
    if obj is None:
        import re

        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise InvalidActionError(f"no rating JSON in: {text[:200]}")
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            raise InvalidActionError(f"bad rating JSON: {text[:200]}") from e
    rating = obj.get("rating")
    if not isinstance(rating, int) or not 1 <= rating <= 10:
        raise InvalidActionError(f"rating must be integer 1..10, got {rating!r}")
    return {"rating": rating, "reason": str(obj.get("reason", ""))}


def _collect_rating(provider, bundle, log, phase: str, char_id: str) -> int:
    raw = provider.complete(bundle.system, bundle.user)
    try:
        parsed = parse_rating(raw)
    except InvalidActionError as e:
        log({"type": "rating_retry", "phase": phase, "actor": char_id, "error": str(e)})
        retry_user = bundle.user + "\n\n必ず指定されたJSONのみで答えること。"
        raw = provider.complete(bundle.system, retry_user)
        parsed = parse_rating(raw)
    log({
        "type": "rating", "phase": phase, "actor": char_id,
        "rating": parsed["rating"], "reason": parsed["reason"],
        "system_prompt": bundle.system, "user_prompt": bundle.user, "raw_response": raw,
    })
    return parsed["rating"]


def run_condition(
    arm: str,
    item: dict,
    chars: list[Character],
    provider,
    out_dir: Path,
    max_turns: int = 15,
    dynamics: str = "v1",
    appraiser=None,
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / f"{arm}_{item['item_id']}.jsonl"

    def log(event: dict) -> None:
        with log_path.open("a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    discussion = Discussion(chars, arm=arm, provider=provider, item=item, max_turns=max_turns, log_path=log_path,
                            dynamics=dynamics, appraiser=appraiser)

    # 1. private pre-ratings (fresh state; ratings are private and change no public state)
    pre = {}
    for c in chars:
        ctx = discussion.private_context(c) if arm.endswith("pneuma") else None
        bundle = build_rating_prompt(arm, c, item, private_context=ctx)
        pre[c.character_id] = _collect_rating(provider, bundle, log, "pre", c.character_id)

    # 2. discussion to unanimous consensus (v2: private pre-ratings feed the
    # actor's own computed salience lines — own knowledge only, never shared)
    discussion.pre_ratings = dict(pre)
    result = discussion.run()

    # 3. private post-ratings (pure_pneuma uses post-discussion psychological state)
    post = {}
    for c in chars:
        ctx = discussion.private_context(c) if arm.endswith("pneuma") else None
        bundle = build_rating_prompt(arm, c, item, private_context=ctx, dialogue_lines=result["dialogue"])
        post[c.character_id] = _collect_rating(provider, bundle, log, "post", c.character_id)

    summary = {
        "arm": arm,
        "item_id": item["item_id"],
        "polar_direction": item.get("polar_direction"),
        "pre": pre,
        "consensus": result["consensus"],
        "post": post,
        "n_turns": result["n_turns"],
    }
    (out_dir / f"{arm}_{item['item_id']}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2)
    )
    return summary
