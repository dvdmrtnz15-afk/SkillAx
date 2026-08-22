#!/usr/bin/env python3
"""Deterministic BM25 using frozen catalog/idf.json. Does not rebuild IDF."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
STOP = frozenset(
    "a an and as at be by for from in into is it of on or the to use using with without that this those these your you we they their".split()
)
PIPELINE = frozenset(["then", "recipe", "pipeline", "extract-audit-kernel"])


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP and len(t) > 1]


def bm25(query, doc_tokens, idf, avgdl, k1, b):
    if not doc_tokens:
        return 0.0
    tf = {}
    for t in doc_tokens:
        tf[t] = tf.get(t, 0) + 1
    dl = len(doc_tokens)
    score = 0.0
    for q in query:
        if q not in idf:
            continue
        f = tf.get(q, 0)
        if f == 0:
            continue
        denom = f + k1 * (1 - b + b * dl / avgdl)
        score += idf[q] * (f * (k1 + 1)) / denom
    return score


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--idf", default=None)
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--margin", type=float, default=0.05)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    idf_path = Path(args.idf) if args.idf else root / "catalog" / "idf.json"
    table = json.loads(idf_path.read_text(encoding="utf-8"))
    q_tokens = tokenize(args.query)
    pipeline = any(p in args.query.lower() for p in PIPELINE)
    scored = []
    for doc in table["docs"]:
        name = doc["name"]
        s = bm25(q_tokens, doc.get("tokens") or [], table["idf"], table["avgdl"], table["k1"], table["b"])
        if pipeline and name == "skillax":
            s += 0.25
        scored.append((s, 0 if "recipe" not in name else 1, doc["call"], name))
    scored.sort(key=lambda x: (-x[0], x[1], x[2], x[3]))
    print(f"ranker={table['ranker_version']} query={args.query!r}")
    for s, _, call, name in scored:
        print(f"{s:.4f}\t{call}\t{name}")
    if not scored or scored[0][0] < args.threshold:
        print("LOAD=none")
        return
    if len(scored) > 1 and (scored[0][0] - scored[1][0]) < args.margin:
        print("LOAD=none TIE")
        return
    print(f"LOAD={scored[0][3]}")


if __name__ == "__main__":
    sys.exit(main())
