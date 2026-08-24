#!/usr/bin/env python3
"""Hybrid skill router: frozen BM25 + frozen dense, fused by RRF.

Lexical lock: if BM25 has a clear winner (score>=1.0 and margin>=0.5), trust it.
Otherwise RRF-fuse BM25 ranks with dense ranks.
Falls back to BM25-only if catalog/embeddings.json is missing.
"""

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
RRF_K = 60
LEXICAL_MIN = 1.0
LEXICAL_MARGIN = 0.5


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


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def embed_query(text: str, model_name: str) -> list[float]:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)
    vec = model.encode([text], normalize_embeddings=True, show_progress_bar=False)[0]
    return [float(x) for x in vec.tolist()]


def ranks_from_scores(scored: list[tuple[str, float]]) -> dict[str, int]:
    ordered = sorted(scored, key=lambda x: (-x[1], x[0]))
    return {name: i + 1 for i, (name, _) in enumerate(ordered)}


def rrf_fuse(rank_maps: list[dict[str, int]], k: int = RRF_K) -> dict[str, float]:
    names: set[str] = set()
    for m in rank_maps:
        names.update(m)
    out: dict[str, float] = {}
    for name in names:
        s = 0.0
        for m in rank_maps:
            r = m.get(name)
            if r is not None:
                s += 1.0 / (k + r)
        out[name] = s
    return out


def decide(ordered: list[tuple[str, float]], threshold: float, margin: float) -> str:
    if not ordered or ordered[0][1] < threshold:
        return "LOAD=none"
    if len(ordered) > 1 and (ordered[0][1] - ordered[1][1]) < margin:
        return "LOAD=none TIE"
    return f"LOAD={ordered[0][0]}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--idf", default=None)
    ap.add_argument("--embeddings", default=None)
    ap.add_argument("--mode", choices=["bm25", "dense", "hybrid"], default="hybrid")
    ap.add_argument("--threshold", type=float, default=None)
    ap.add_argument("--margin", type=float, default=None)
    ap.add_argument("--rrf-k", type=int, default=RRF_K)
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    idf_path = Path(args.idf) if args.idf else root / "catalog" / "idf.json"
    emb_path = Path(args.embeddings) if args.embeddings else root / "catalog" / "embeddings.json"

    table = json.loads(idf_path.read_text(encoding="utf-8"))
    emb = None
    if emb_path.exists():
        emb = json.loads(emb_path.read_text(encoding="utf-8"))

    if args.mode in ("dense", "hybrid") and emb is None:
        if args.mode == "dense":
            print("ERR embeddings.json missing", file=sys.stderr)
            raise SystemExit(2)
        args.mode = "bm25"

    q_tokens = tokenize(args.query)
    pipeline = any(p in args.query.lower() for p in PIPELINE)

    bm25_scores: list[tuple[str, float]] = []
    call_of: dict[str, str] = {}
    for doc in table["docs"]:
        name = doc["name"]
        call_of[name] = doc["call"]
        s = bm25(q_tokens, doc.get("tokens") or [], table["idf"], table["avgdl"], table["k1"], table["b"])
        if pipeline and name == "skillax":
            s += 0.25
        bm25_scores.append((name, s))
    bm25_scores.sort(key=lambda x: (-x[1], x[0]))

    dense_scores: list[tuple[str, float]] = []
    if emb is not None and args.mode in ("dense", "hybrid"):
        q_vec = embed_query(args.query, emb["model"])
        if len(q_vec) != emb["dim"]:
            print(f"ERR query dim {len(q_vec)} != {emb['dim']}", file=sys.stderr)
            raise SystemExit(2)
        by_name = {d["name"]: d for d in emb["docs"]}
        for name, _ in bm25_scores:
            d = by_name.get(name)
            dense_scores.append((name, cosine(q_vec, d["vector"]) if d else -1.0))

    channel = args.mode
    if args.mode == "hybrid" and len(bm25_scores) >= 1:
        top_s = bm25_scores[0][1]
        second_s = bm25_scores[1][1] if len(bm25_scores) > 1 else 0.0
        if top_s >= LEXICAL_MIN and (top_s - second_s) >= LEXICAL_MARGIN:
            channel = "bm25-lock"

    if args.mode == "bm25" or channel == "bm25-lock":
        fused = {n: s for n, s in bm25_scores}
        version = table.get("ranker_version", "bm25")
        thr = 0.5 if args.threshold is None else args.threshold
        mar = 0.05 if args.margin is None else args.margin
        mode_label = channel if channel == "bm25-lock" else "bm25"
    elif args.mode == "dense":
        fused = {n: s for n, s in dense_scores}
        version = emb.get("ranker_version", "dense") if emb else "dense"
        thr = 0.15 if args.threshold is None else args.threshold
        mar = 0.02 if args.margin is None else args.margin
        mode_label = "dense"
    else:
        r_bm = ranks_from_scores(bm25_scores)
        r_de = ranks_from_scores(dense_scores)
        fused = rrf_fuse([r_bm, r_de], k=args.rrf_k)
        version = emb.get("ranker_version", "hybrid-rrf-1") if emb else "hybrid"
        thr = 0.016 if args.threshold is None else args.threshold
        mar = 0.0005 if args.margin is None else args.margin
        mode_label = "hybrid"

    ordered = sorted(fused.items(), key=lambda x: (-x[1], call_of.get(x[0], ""), x[0]))
    print(f"ranker={version} mode={mode_label} query={args.query!r}")
    for name, s in ordered:
        print(f"{s:.6f}\t{call_of.get(name, '')}\t{name}")
    print(decide(ordered, thr, mar))


if __name__ == "__main__":
    sys.exit(main() or 0)
