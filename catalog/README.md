# Catalog indexes

## Surfaces

| File | Role |
|------|------|
| `../CATALOG.json` | Product list (kernel / apps / merged) |
| `idf.json` | Frozen BM25 IDF + doc tokens |
| `embeddings.json` | Frozen dense vectors (L2-normalized) |
| `live.json` | Measured packs that passed SA6 halt (`measure.py --publish`) |

## Ranker

`scripts/rank.py` defaults to **hybrid** mode:

1. BM25 ranks from `idf.json`
2. Dense cosine ranks from `embeddings.json` (query embedded with the frozen model name)
3. Reciprocal Rank Fusion (`k=60`) when BM25 has no clear winner
4. **Lexical lock** — if BM25 top score ≥ 1.0 and margin ≥ 0.5, trust BM25 (exact triggers)
5. `LOAD=<name>` if top score clears threshold and margin; else `LOAD=none` / `LOAD=none TIE`

Modes: `--mode bm25|dense|hybrid`.

Rebuild (do not edit scores by hand):

```bash
python3 scripts/idf_build.py
python3 scripts/embed_build.py   # needs sentence-transformers at build time only
python3 scripts/rank.py "consult booking dual site"
python3 scripts/rank_test.py
```

Membership is `scripts/live_skills.py` (`LIVE`). Do not add class-900 private kernels or skills without an SA6 call number.

`idf.json` and `embeddings.json` are **frozen**. Changing a skill description does not change rank until you rebuild and commit both files.

## Live measure

```bash
python3 scripts/measure.py path/to/pack --publish
```

Writes `live.json` only on PASS with a content-addressed id.
