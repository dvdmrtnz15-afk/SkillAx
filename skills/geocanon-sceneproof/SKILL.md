---
name: geocanon-sceneproof
description: Ground generated or edited visual scenes in a specific real-world place using admissible geospatial evidence, explicit camera/spatial constraints, temporal snapshots, rights manifests, hard validation gates, and provenance receipts. Use when location truth matters more than loose visual resemblance.
---

# GeoCanon / SceneProof

GeoCanon is an evidence-governance skill for real-world scene grounding. It compiles admissible evidence into a `SceneContract`, chooses the least-generative supported render path, and permits a `GroundingReceipt` only when every required hard gate passes.

## Core Mandate

A scene is grounded only when exact place identity, source rights, spatial structure, camera support, temporal compatibility, output format, render policy, subject/object continuity when applicable, and provenance are all supported. Visual resemblance alone never establishes truth, and no weighted score may compensate for a failed hard gate.

SkillAx distributes the schema, policy, fixtures, deterministic helper scripts, and evaluation contract. It is not the authority or publishing plane. Proof/admission belongs to the consuming proof kernel; evidence cannot self-promote into canon, memory, or execution authority.

## Operating Principles

- Type every source by evidence role and authority scope before it enters a render request.
- Give generated continuity assets zero truth authority.
- Fail closed on unknown, omitted, or contradictory rights.
- Keep interior and exterior zones separate and reject unsupported view cones.
- Freeze one temporal snapshot; current appearance cannot be inferred from stale sources.
- Prefer immutable plate insertion, then licensed multiview reconstruction, then constrained generation.
- When a usable immutable location plate exists, do not redraw the location.
- Permit edits only inside declared mutable regions and preserve declared anchors.
- Treat Google Maps and Street View as verification surfaces or permitted metadata sources, never as an unlicensed pixel corpus.
- Return the visual asset separately from its deterministic receipt.

## Required Objects

- `EvidenceNode`: immutable observation with role, authority, hash, capture time, zone, rights, permitted uses, and lineage.
- `RightsManifest`: exact admissibility decision for every evidence node.
- `LocationPassport`: place identity, address, coordinates, zones, invariants, prohibited mutations, and evidence graph.
- `SceneContract`: requested location zone, target snapshot, output format, anchors, mutable regions, render policy, and required gates.
- `ViewCone`: camera pose/FOV uncertainty plus required, visible, optional, and prohibited anchors.
- `RenderPlan`: deterministic selected mode, evidence IDs, immutable anchors, mutable regions, format, and contract hash.
- `GroundingReceipt`: contract/render/evidence/output hashes, gate results, transformations, software identifiers, render mode, and verdict.

Schemas live in `spec/geocanon/`.

## Evidence Policy

Default allowlist:

1. User-owned or user-supplied imagery with sufficient permission.
2. OpenStreetMap-derived place and geometry metadata under applicable ODbL obligations.
3. Explicitly licensed imagery whose license permits the intended operation.
4. Provider APIs only within recorded terms and permitted-use scope.

Evidence roles are not interchangeable. `location_plate`, `location_geometry`, and `location_appearance` may establish location truth when rights and temporal constraints pass. `persona_identity`, `object_geometry`, `lighting_reference`, and `camera_reference` establish only their declared scope. `generated_continuity` always has `authority: none`.

Google Maps or Street View pixels are excluded from training, validation, reconstruction, derivative generation, and other pixel-producing paths. Do not scrape or export them. Permitted metadata use must remain separately declared.

## Pipeline

1. Resolve place and load the `LocationPassport`.
2. Ingest sources as typed, hashed `EvidenceNode`s.
3. Evaluate rights and emit a fail-closed `RightsManifest`.
4. Freeze the requested temporal snapshot.
5. Validate zone, anchors, camera support, and evidence graph.
6. Compile the `SceneContract`.
7. Route to `immutable_plate`, `multiview_reconstruction`, or `constrained_generation` in that order.
8. Generate or composite only inside declared mutable regions.
9. Run all required hard gates.
10. Emit a receipt only when contract, render plan, evidence, output, and gate results agree.

## Render Routing

- `immutable_plate`: requires an admissible, zone-matching location plate permitting derivative generation and display.
- `multiview_reconstruction`: requires at least two admissible, zone-matching reconstruction sources.
- `constrained_generation`: requires admissible geometry plus appearance evidence and explicit policy permission.
- No admissible route means `REJECTED`.

Adapters such as OSM/Nominatim, HLoc, LightGlue, COLMAP, segmentation, compositing, NeRF, or Gaussian splatting remain optional capability providers. They submit evidence or evaluator results; they do not decide authority.

## MVP Reference Slice

The first regression target is Starbucks Coffee Company at 3105 W 26th St in Chicago's Little Village plaza. The repository fixture contains metadata and placeholder hashes only; user images are not committed. The reference route must choose an immutable user-owned exterior plate, preserve storefront/entrance/parking/plaza anchors, permit only the foreground subject mask to change, and reject generic or mixed-zone architecture.

## Hard Gates

- `G_LOCATION_IDENTITY`: contract and passport identify the same exact place.
- `G_RIGHTS`: every dependency is explicitly allowed for its operation.
- `G_SPATIAL`: required anchors, zone, adjacency, and structural relationships remain supported.
- `G_VIEW_CONE`: the requested camera view is supported within declared uncertainty.
- `G_TEMPORAL`: evidence is compatible with the target snapshot.
- `G_SUBJECT_CANON`: persistent-character identity and relationship constraints pass externally when applicable.
- `G_FORMAT`: output is exactly the contracted standalone asset shape.
- `G_RENDER_POLICY`: the least-generative admissible mode is selected.
- `G_OBJECT_INTEGRITY`: object and anatomy integrity pass externally when applicable.
- `G_PROVENANCE`: hashes, source IDs, transformations, software identifiers, and gate results are complete.

## Evaluation Behavior

Treat failed candidates as optimization evidence, but never relax a hard gate to admit them. Promote repeated failures into explicit invariants and regression fixtures. Separate photographic realism from geographic truth: a persuasive image may still be geographically false.

## Output Contract

Return the generated asset separately from its receipt. Human-facing states are:

- `GROUNDED`: every required hard gate passed.
- `PARTIALLY_GROUNDED`: useful evidence exists but an exact claim was intentionally weakened; never present it as exact truth.
- `REJECTED`: one or more hard gates failed.

Never claim exact real-world grounding without a coherent `GROUNDED` receipt.
