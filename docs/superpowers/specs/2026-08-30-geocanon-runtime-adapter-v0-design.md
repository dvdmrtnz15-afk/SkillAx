# GeoCanon Runtime Adapter v0 — Design

## Purpose

GeoCanon/SceneProof v0 governs place identity, evidence rights, mutable regions, gates, and receipts. Runtime Adapter v0 supplies the next bounded layer: a deterministic reference implementation for inserting subject layers into an admitted immutable location plate without granting the adapter authority to redefine geography, canon, rights, or final grounding status.

The adapter is intentionally small. It demonstrates the protocol and invariants with stdlib-only ASCII Netpbm images (`P3` RGB and `P2` masks), making the full path executable in minimal CI. Production adapters may use OpenCV, Pillow, learned segmentation, relighting, shadow synthesis, or occlusion models, but must emit the same portable request/result contract and pass the same fail-closed validation.

## Architectural boundary

```text
SceneContract + RightsManifest + admitted plate
                    │
                    ▼
           RuntimeAdapterRequest
                    │
                    ▼
   untrusted capability providers / reference adapter
                    │
                    ▼
           RuntimeAdapterResult
      advisory observations + artifact hashes
                    │
                    ▼
              Proof kernel
      authoritative gate decisions + receipt
```

The runtime adapter may transform pixels only inside a SceneContract-declared mutable mask. It may not:

- replace, redraw, or reinterpret the location plate outside that mask;
- promote a generated image into location evidence;
- issue a `GROUNDED` verdict;
- rewrite `LocationPassport`, `SceneContract`, `RightsManifest`, or persona canon;
- convert advisory observations directly into authoritative gate decisions.

## Render mode

Runtime v0 supports only:

```text
immutable_plate
```

A caller cannot escalate to multiview reconstruction or constrained generation through this adapter. Those modes require separate capability contracts and evidence admission.

## Governed stage order

The request fixes this exact sequence:

1. `verify_inputs`
2. `segment_subjects`
3. `photometric_relight`
4. `contact_shadow`
5. `occlusion_repair`
6. `composite`
7. `evaluate_integrity`

The reference adapter consumes precomputed subject segmentation and optional occlusion masks. Learned models may produce these artifacts upstream, but the artifacts remain content-addressed, untrusted inputs.

## Input contract

`RuntimeAdapterRequest` binds:

- the exact `SceneContract` hash;
- an admitted plate EvidenceNode and local content hash;
- one SceneContract mutable-region identifier and full-frame mask;
- one or more subject RGB assets and segmentation masks;
- placement, channel gain/bias relighting, contact-shadow parameters, and optional occlusion masks;
- the exact stage order;
- a maximum mutable-pixel fraction;
- immutable-pixel preservation policy.

All local paths must be relative to the request directory and cannot traverse parent directories.

## Reference raster behavior

The reference adapter:

- verifies every file hash and declared dimension;
- checks plate evidence rights include `derivative_generation`;
- rejects any subject or shadow footprint outside the mutable mask;
- applies deterministic per-channel gain/bias to subject pixels;
- synthesizes a shifted/box-blurred contact shadow;
- composites subject pixels using the segmentation alpha;
- restores plate pixels using optional occlusion masks;
- hashes immutable plate pixels before and after rendering;
- writes a deterministic output and stage artifact ledger.

## Result contract

`RuntimeAdapterResult` contains:

- job, contract, plate, output, and result hashes;
- stage artifact IDs, kinds, and hashes;
- immutable-region before/after hashes;
- mutable coverage and subject count;
- advisory gate observations.

It deliberately omits a final verdict. The evaluator envelope is fixed to:

```json
{"authority": "advisory_only"}
```

Statuses are `PASS`, `FAIL`, or `UNKNOWN`. `UNKNOWN` is expected when the adapter cannot establish place identity, view-cone truth, temporal truth, or subject canon.

## Kernel-side validation

The result validator recomputes rather than trusts:

- request admissibility;
- output hash and dimensions;
- immutable-region pixel hashes;
- mutable fraction;
- subject count;
- required stage artifact coverage;
- plate and mutable-mask stage hashes;
- final composite hash;
- result hash;
- advisory-only authority semantics.

An attacker cannot mutate an immutable output pixel and repair only the self-reported hashes: the validator reloads the admitted plate and mask and performs its own pixel comparison.

## Receipt binding

`geocanon_receipt.py` accepts an optional runtime request/result pair. When supplied, it:

- validates the runtime result independently;
- binds `runtime_job_id`, `runtime_result_hash`, and `render_mode` into receipt v0.2;
- rejects a final authoritative `PASS` that contradicts a runtime `FAIL` observation;
- does not auto-promote runtime `PASS` or `UNKNOWN` observations into gate decisions.

## Reference fixtures

The repository includes tiny synthetic PPM/PGM assets. They verify runtime semantics only and make no real-world location claim. Production Little Village assets remain user-owned, externally stored, content-addressed evidence.

## Acceptance criteria

- Reference runtime executes with Python stdlib only.
- Immutable pixels remain byte-equivalent by governed pixel hash.
- Full-frame mutable masks are rejected by policy.
- Subject and shadow footprints outside the mutable mask are rejected.
- Output or result tampering is rejected.
- Runtime authority escalation is rejected.
- Receipt binds a valid runtime result and rejects known observation contradictions.
