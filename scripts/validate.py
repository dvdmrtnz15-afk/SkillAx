#!/usr/bin/env python3
"""SkillAx v0.1 validator — structure, naming, trigger hygiene, safety floor."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"

NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9]|-(?!-))*[a-z0-9]$")
BAD_DESC = [
    (": ", "colon-space in description (forces YAML quoting)"),
    ("<", "angle bracket < in description"),
    (">", "angle bracket > in description"),
]
DANGER = [
    r"api[_-]?key\s*[:=]",
    r"secret[_-]?key\s*[:=]",
    r"BEGIN (RSA |OPENSSH )?PRIVATE KEY",
    r"ignore (all )?previous instructions",
]


def fail(msg: str, errors: list[str]) -> None:
    errors.append(msg)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md must start with YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("unclosed frontmatter")
    raw = text[4:end]
    body = text[end + 5 :]
    meta: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"invalid frontmatter line: {line}")
        key, val = line.split(":", 1)
        meta[key.strip()] = val.strip()
    return meta, body


def validate_skill(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return [f"{skill_dir.name}: missing SKILL.md"]

    text = skill_md.read_text(encoding="utf-8")
    lines = text.count("\n") + 1
    try:
        meta, body = parse_frontmatter(text)
    except ValueError as e:
        return [f"{skill_dir.name}: {e}"]

    name = meta.get("name", "")
    desc = meta.get("description", "")

    if name != skill_dir.name:
        fail(f"{skill_dir.name}: name '{name}' != directory '{skill_dir.name}'", errors)
    if not NAME_RE.match(name) or not (2 <= len(name) <= 64):
        fail(f"{skill_dir.name}: invalid kebab-case name", errors)
    if not desc:
        fail(f"{skill_dir.name}: missing description", errors)
    if "\n" in desc:
        fail(f"{skill_dir.name}: description must be a single line", errors)
    if len(desc) > 1024:
        fail(f"{skill_dir.name}: description exceeds 1024 characters", errors)
    for token, why in BAD_DESC:
        if token in desc:
            fail(f"{skill_dir.name}: {why}", errors)
    if lines > 500:
        fail(f"{skill_dir.name}: SKILL.md has {lines} lines (max 500)", errors)

    lowered = text.lower()
    for pat in DANGER:
        if re.search(pat, text, re.I):
            fail(f"{skill_dir.name}: safety floor hit ({pat})", errors)

    required = ["core mandate", "operating principles"]
    for section in required:
        if section not in lowered:
            fail(f"{skill_dir.name}: missing section '{section}'", errors)

    return errors


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--all"]
    if "--all" in sys.argv[1:] or not args:
        targets = sorted(p for p in SKILLS.iterdir() if p.is_dir())
    else:
        targets = []
        for a in args:
            p = Path(a)
            if not p.is_absolute():
                p = ROOT / a if a.startswith("skills/") else SKILLS / a
            targets.append(p)

    all_errors: list[str] = []
    for t in targets:
        errs = validate_skill(t)
        if errs:
            all_errors.extend(errs)
        else:
            print(f"OK  {t.name}")

    if all_errors:
        for e in all_errors:
            print(f"ERR {e}", file=sys.stderr)
        return 1
    print(f"validated {len(targets)} skill(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
