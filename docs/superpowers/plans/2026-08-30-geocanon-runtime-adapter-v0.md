# GeoCanon Runtime Adapter v0 — Implementation Plan

## Goal

Add a portable, executable immutable-plate runtime adapter and advisory evaluation envelope on top of GeoCanon/SceneProof v0 without moving final authority into SkillAx.

## Workstream 1 — Runtime schema

Create `spec/geocanon/geocanon-runtime.schema.json` covering:

- `RuntimeAdapterRequest`
- typed local raster artifacts
- subject segmentation, placement, relighting, shadow and occlusion parameters
- exact stage order
- immutable-region policy
- `RuntimeAdapterResult`
- advisory evaluation observations

Update the base receipt schema with optional runtime binding fields.

## Workstream 2 — Reference adapter

Create `scripts/geocanon_runtime.py` with:

- strict relative-path resolution;
- SHA-256 and dimension verification;
- ASCII P2/P3 parser/writer;
- deterministic relighting;
- contact-shadow synthesis;
- alpha compositing;
- occlusion restoration;
- immutable-pixel hashing;
- stage artifact ledger;
- request and result semantic validation;
- `run` and `validate-result` CLIs.

## Workstream 3 — Receipt integration

Extend `scripts/geocanon_receipt.py` to:

- accept `--runtime-request` and `--runtime-result` together;
- validate output binding and adapter result integrity;
- reject authoritative gate results that contradict runtime `FAIL` observations;
- add runtime hash/job/render mode fields to receipt v0.2.

Maintain backward compatibility when no runtime pair is supplied.

## Workstream 4 — Synthetic fixture

Add a small content-addressed runtime fixture:

- 6×6 immutable RGB plate;
- 6×6 mutable mask;
- 2×2 subject image and segmentation;
- 2×2 occlusion mask;
- request, bundle, deterministic output and result.

No real user imagery enters the repository.

## Workstream 5 — Adversarial tests

Add regressions for:

- stage reorder;
- render-mode escalation;
- plate hash mismatch;
- duplicate subjects;
- subject placement outside the mutable mask;
- shadow footprint escape;
- full-frame mutable mask;
- adapter verdict/canon authority escalation;
- result-hash tampering;
- immutable-pixel tampering with repaired self-reported hashes;
- missing stage artifacts;
- valid runtime receipt binding;
- receipt contradiction between runtime `FAIL` and authoritative `PASS`.

## Workstream 6 — Documentation and CI

Document the adapter boundary in the GeoCanon skill and design spec. Add runtime tests and deterministic fixture validation to `.github/workflows/validate.yml`.

## Verification

```bash
python3 -m json.tool spec/geocanon/geocanon-runtime.schema.json
python3 -m json.tool fixtures/geocanon/runtime/reference.bundle.json
python3 -m json.tool fixtures/geocanon/runtime/reference.request.json
python3 scripts/geocanon_validate.py fixtures/geocanon/runtime/reference.bundle.json
python3 scripts/geocanon_runtime.py run \
  fixtures/geocanon/runtime/reference.bundle.json \
  fixtures/geocanon/runtime/reference.request.json \
  --output /tmp/geocanon-runtime-output.ppm \
  --result-out /tmp/geocanon-runtime-result.json
python3 scripts/geocanon_runtime.py validate-result \
  fixtures/geocanon/runtime/reference.bundle.json \
  fixtures/geocanon/runtime/reference.request.json \
  /tmp/geocanon-runtime-result.json \
  /tmp/geocanon-runtime-output.ppm
python3 scripts/geocanon_runtime_test.py
python3 scripts/geocanon_test.py
python3 scripts/validate.py --all
```
