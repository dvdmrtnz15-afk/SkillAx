#!/usr/bin/env python3
"""Build frozen dense embeddings for live skill descriptions.

Requires sentence-transformers at build time only.
Query-time rank.py embeds the query with the same model; doc vectors stay frozen.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from live_skills import EMBED_DIM, EMBED_MODEL, LIVE, RANKER_VERSION


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


def embed_text(name: str, desc: str) -> str:
    return f"{name.replace('-', ' ')}. {desc}".strip()


def build(skills_roots: list[Path]) -> dict:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMBED_MODEL)
    docs = []
    texts = []
    for name, call in LIVE.items():
        path = find_skill_md(name, skills_roots)
        desc = description_of(path) if path else name
        text = embed_text(name, desc)
        docs.append({"name": name, "call": call, "text": text})
        texts.append(text)

    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    if int(vectors.shape[1]) != EMBED_DIM:
        raise SystemExit(f"expected dim {EMBED_DIM}, got {vectors.shape[1]}")

    out_docs = []
    for doc, vec in zip(docs, vectors):
        out_docs.append(
            {
                "name": doc["name"],
                "call": doc["call"],
                "text": doc["text"],
                "vector": [round(float(x), 8) for x in vec.tolist()],
            }
        )

    return {
        "ranker_version": RANKER_VERSION,
        "channel": "dense",
        "model": EMBED_MODEL,
        "dim": EMBED_DIM,
        "normalized": True,
        "N": len(out_docs),
        "docs": out_docs,
        "note": "Do not re-embed documents at query time. Rebuild and commit this file to change dense ranking.",
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    roots = [root / "skills", Path("/home/workdir/.grok/skills")]
    if len(sys.argv) > 1:
        roots.insert(0, Path(sys.argv[1]))
    table = build(roots)
    out = root / "catalog" / "embeddings.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out} N={table['N']} dim={table['dim']} model={table['model']}")


if __name__ == "__main__":
    main()
