# Catalog indexes

`idf.json` is a **frozen** BM25 snapshot (`ranker_version: bm25-frozen-1`).

- Query time reads this file. It does not recompute document frequency.
- Doc token lists are frozen too. Editing a SKILL.md description does not change rank until you rebuild and commit.
- Live public set only (no class 900, no merged historical skill).

```
python3 scripts/rank.py "consult booking dual site"
python3 scripts/idf_build.py   # then commit catalog/idf.json
```

Change weights or the corpus → bump `RANKER_VERSION` in `scripts/idf_build.py`.
