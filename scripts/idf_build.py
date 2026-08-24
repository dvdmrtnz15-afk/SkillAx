#!/usr/bin/env python3
"""Build a frozen BM25 IDF table from live public skill descriptions."""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

from live_skills import LIVE, RANKER_VERSION

K1 = 1.2
B = 0.75
TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
STOP = frozenset(
    "a an and as at be by for from in into is it of on or the to use using with without that this those these your you we they their".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP and len(t) > 1]


def description_of(skill_md: Path) -> str:
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return ""
    fm = text.split("---", 2)[1]
    for line in fm.splitlines():
        if line.startswith("description:"):
            return line[len("description:") :].strip()
    return ""


def find_skill_md(name: str, roots: list[Path]) -> Path | None:
    for root in roots:
        p = root / name / "SKILL.md"
        if p.is_file():
            return p
    return None


def build(skills_roots: list[Path]) -> dict:
    docs = []
    for name, call in LIVE.items():
        path = find_skill_md(name, skills_roots)
        desc = description_of(path) if path else name
        tokens = tokenize(name.replace("-", " ") + " " + desc)
        docs.append({"name": name, "call": call, "tokens": tokens, "len": len(tokens)})
    n = len(docs)
    df: dict[str, int] = {}
    for doc in docs:
        for tok in set(doc["tokens"]):
            df[tok] = df.get(tok, 0) + 1
    avgdl = sum(d["len"] for d in docs) / n if n else 0.0
    idf = {tok: math.log(1.0 + (n - c + 0.5) / (c + 0.5)) for tok, c in sorted(df.items())}
    return {
        "ranker_version": RANKER_VERSION,
        "channel": "bm25",
        "k1": K1,
        "b": B,
        "N": n,
        "avgdl": round(avgdl, 6),
        "idf": idf,
        "docs": [{"name": d["name"], "call": d["call"], "len": d["len"], "tokens": d["tokens"]} for d in docs],
        "stopword_policy": "frozen-list-in-idf_build.py",
        "note": "Do not recompute IDF at query time. Rebuild and commit this file to change ranking.",
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    roots = [root / "skills", Path("/home/workdir/.grok/skills")]
    if len(sys.argv) > 1:
        roots.insert(0, Path(sys.argv[1]))
    table = build(roots)
    out = root / "catalog" / "idf.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out} N={table['N']} terms={len(table['idf'])}")


if __name__ == "__main__":
    main()
