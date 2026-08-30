# GeoCanon / SceneProof v0 Design

## Purpose

GeoCanon / SceneProof is SkillAx's portable, fail-closed contract for grounding generated or edited visual scenes in a specific real-world place. It converts rights-cleared evidence into a deterministic scene contract, selects the least-generative admissible render path, rejects unsupported claims, and emits a receipt that downstream proof kernels can verify.

SkillAx distributes schemas, policy, deterministic helper scripts, fixtures, and regression tests. It does not become a location-authority plane, does not scrape providers, does not publish imagery, and does not allow evidence to self-promote into character canon or execution authority.

## V0 Scope

V0 implements six units:

1. `LocationPassport` — canonical place identity, address, zones, spatial anchors, temporal snapshot policy, and prohibited mutations.
2. `EvidenceNode` / `RightsManifest` — typed evidence roles, authority scope, content hashes, capture time, rights, permitted uses, and provenance lineage.
3. `SceneContract` / `ViewCone` — exact location zone, one-image output contract, required anchors, mutable regions, camera constraints, target snapshot, and hard gates.
4. `RenderRouter` — deterministic choice among `immutable_plate`, `multiview_reconstruction`, and `constrained_generation`, preferring the least-generative admissible mode.
5. `GateEvaluator` — stdlib semantic validation for rights, place identity, zone separation, temporal compatibility, format, render policy, evidence authority, view-cone support, and provenance.
6. `GroundingReceipt` — contract, render-plan, evidence, output, transformation, software, and gate-result hashes with a fail-closed verdict.

The Little Village Starbucks reference bundle is a non-production regression fixture. It uses placeholder hashes and metadata only; user images are not committed.

## Source and Rights Policy

Evidence roles are explicit and non-interchangeable:

- `location_plate`
- `location_geometry`
- `location_appearance`
- `persona_identity`
- `wardrobe`
- `object_geometry`
- `lighting_reference`
- `camera_reference`
- `negative_reference`
- `generated_continuity`
- `metadata`

Authority scopes are explicit:

- `location_truth`
- `subject_truth`
- `object_truth`
- `capture_reference`
- `none`

Generated evidence always has `authority: none`; it may support continuity but may not establish location, subject, or object truth. Google Maps or Street View pixels are excluded from validation, reconstruction, derivative generation, and other pixel-producing paths. Provider metadata may be used only when its recorded terms and permitted-use scope allow it.

Unknown rights fail closed. A rights-manifest decision must exactly cover each evidence node used by the bundle.

## Spatial and Temporal Model

A `LocationPassport` declares zones such as `exterior_entrance`, `exterior_patio`, `interior_counter`, and `interior_mural_wall`. Every location-bearing evidence node declares its zone. Interior and exterior evidence cannot be silently mixed.

The scene target snapshot contains an `as_of` timestamp and a maximum age for current appearance evidence. Structural or metadata evidence may be older when explicitly classified, but a current exact-scene claim requires at least one temporally compatible location plate or appearance node for the requested zone.

The `ViewCone` declares required, permitted, and prohibited visible anchors. Required scene anchors must be present in the view cone, and prohibited anchors must not appear in its visible set.

## Render Routing

Routing is deterministic and ordered:

1. Select `immutable_plate` when an admissible, zone-matching `location_plate` exists and permits derivative generation and display.
2. Otherwise select `multiview_reconstruction` when at least two admissible, zone-matching reconstruction sources exist.
3. Otherwise select `constrained_generation` only when both geometry and appearance evidence exist, rights permit the operation, and the scene policy allows it.
4. Otherwise reject the build.

When an admissible immutable plate exists, lower-authority full-frame regeneration is prohibited. The resulting render plan contains the selected mode, evidence IDs, immutable anchors, mutable regions, target snapshot, and contract hash.

## Hard Gates

V0 recognizes:

- `G_LOCATION_IDENTITY`
- `G_RIGHTS`
- `G_SPATIAL`
- `G_VIEW_CONE`
- `G_TEMPORAL`
- `G_SUBJECT_CANON`
- `G_FORMAT`
- `G_RENDER_POLICY`
- `G_OBJECT_INTEGRITY`
- `G_PROVENANCE`

Every scene must require location identity, rights, spatial, temporal, format, render policy, and provenance. Subject and object gates remain externally evaluated when applicable. A hard-gate failure cannot be averaged away by a visual score.

## Output Format Contract

The reference social-image contract is exactly one standalone image. It rejects collage, grid, panel, storyboard, and unrequested text-overlay output. The contract records aspect ratio, image count, and overlay policy.

## Determinism and Provenance

Canonical JSON uses sorted keys, compact separators, UTF-8, and SHA-256. The compiler emits a deterministic render plan for the same bundle. The receipt records:

- contract hash
- render-plan hash and selected mode
- output hash
- exact evidence hashes
- sorted hard-gate results
- transformations
- software/model identifiers
- final verdict

A receipt cannot launder an invalid bundle into `GROUNDED`.

## Architecture Boundary

The runtime flow is:

`ResolvePlace -> LoadPassport -> SelectEvidence -> FreezeSnapshot -> ValidateViewCone -> CompileContract -> RouteRender -> EvaluateGates -> EmitReceipt -> Accept/Reject`

Adapters such as OSM/Nominatim, HLoc, LightGlue, COLMAP, segmentation, compositing, or model providers remain optional capability providers outside the trusted kernel. They submit evidence and gate results; they do not decide authority.

## Acceptance Criteria

The implementation is accepted when:

- repository skill validation passes;
- the Little Village fixture validates;
- the compiler selects `immutable_plate` for the reference fixture;
- generated continuity evidence cannot establish location truth;
- wrong-zone, stale, malformed-format, view-cone, rights, Google-pixel, and render-policy regressions reject;
- coherent receipts pass and tampered contract/render/evidence hashes reject;
- all validation commands in `.github/workflows/validate.yml` pass on the exact branch head.
