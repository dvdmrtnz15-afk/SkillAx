#!/usr/bin/env python3
"""Admit or reject a SemanticIR fragment. Deterministic. No model."""

from __future__ import annotations

import json
import re
import sys
from typing import Any

SOURCE_TYPES = {
    "grok",
    "claude",
    "chatgpt",
    "gemini",
    "perplexity",
    "linear",
    "github",
    "gmail",
    "drive",
    "slack-export",
    "teams",
    "calendar",
}

DECORATIVE_WHY = {
    "might be useful",
    "could be useful",
    "interesting",
    "tbd",
    "n/a",
    "na",
    "none",
    "later",
    "important",
    "context",
    "just context",
}

EMPTY_NEXT = {
    "tbd",
    "n/a",
    "na",
    "none",
    "later",
    "continue",
    "keep going",
    "todo",
    "wip",
}

OUT_OF_LEASE = re.compile(
    r"\b(parenting[- ]time|opposing counsel|custody|family.?legal|tru-7)\b",
    re.I,
)
NO_EVIDENCE = re.compile(
    r"\b(no world delta|no new sha|organism still|hourly self-prompt|circadian receipt)\b",
    re.I,
)
AMPLIFIER = re.compile(
    r"\b(we built|we shipped|buyer is|deadline is|guaranteed|this is done|marked done)\b",
    re.I,
)
HEDGE = re.compile(r"\b(might|maybe|could|claimed|source said)\b", re.I)


def _s(value: Any) -> str:
    return str(value or "").strip()


def gate(frag: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    title = _s(frag.get("title"))
    idea = _s(frag.get("idea"))
    nxt = _s(frag.get("next_action"))
    why = _s(frag.get("why_it_matters"))
    residual = _s(frag.get("residual"))
    source_type = _s(frag.get("source_type")).lower()
    source_url = _s(frag.get("source_url"))
    plane = _s(frag.get("plane")).lower()
    impact = frag.get("impact")

    if not title:
        errors.append("missing title")
    if not idea:
        errors.append("missing idea")
    elif len(idea.split()) < 8:
        errors.append("idea too thin")
    if not nxt:
        errors.append("missing next_action")
    elif nxt.lower() == idea.lower():
        errors.append("next_action restates idea")
    elif nxt.lower() in EMPTY_NEXT:
        errors.append("next_action empty-gesture")
    if not why:
        errors.append("missing why_it_matters")
    elif why.lower() in DECORATIVE_WHY:
        errors.append("decorative why_it_matters")
    if "residual" not in frag:
        errors.append("missing residual field")
    if source_type not in SOURCE_TYPES:
        errors.append("invalid or missing source_type")
    if source_url and not source_url.startswith(("http://", "https://")):
        errors.append("source_url invented or malformed")
    if not plane:
        errors.append("missing plane")

    blob = " ".join([title, idea, nxt, why, residual])
    if OUT_OF_LEASE.search(blob):
        errors.append("out_of_lease")
    if NO_EVIDENCE.search(blob):
        errors.append("no-evidence pass")
    if AMPLIFIER.search(idea) and not HEDGE.search(idea):
        errors.append("amplification in idea")

    try:
        impact_n = int(impact) if impact is not None else None
    except (TypeError, ValueError):
        impact_n = None
        if impact is not None:
            errors.append("impact not an int")

    admit = not errors
    if errors == ["missing next_action"] and impact_n is not None and impact_n >= 8:
        admit = True
        warnings.append("incomplete but high-impact exception")

    return {
        "ok": admit,
        "errors": errors,
        "warnings": warnings,
        "fragment": frag,
    }


def main(argv: list[str]) -> int:
    raw = sys.stdin.read() if not argv else open(argv[0], encoding="utf-8").read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": [f"invalid json: {exc}"]}, indent=2))
        return 2
    result = gate(data)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
