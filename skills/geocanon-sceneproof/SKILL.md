---
name: geocanon-sceneproof
description: Ground generated or edited visual scenes in a specific real-world place using admissible geospatial evidence, explicit camera/spatial constraints, temporal snapshots, rights manifests, hard validation gates, and provenance receipts. Use when location truth matters more than loose visual resemblance.
---

# GeoCanon / SceneProof

GeoCanon is an evidence-governance skill for real-world scene grounding. It does not grant authority to generate a scene merely because references exist. It compiles admissible evidence into a SceneContract and emits a GroundingReceipt only when hard gates pass.

## Core invariant

A scene is grounded only when all of the following are supported: exact place identity, admissible source rights, required spatial relationships, physically plausible requested view, temporal compatibility, reproducible transformations, and traceable provenance. Resemblance alone is insufficient.

## Architecture boundary

SkillAx distributes the portable schema, skill, adapters, fixtures, and evaluation contract. It is not the authority/control plane. Proof/admission belongs to the consuming proof kernel. Runtime/world-model systems consume receipts; evidence never self-promotes into canon or authority.

## Required objects

- `EvidenceNode`: immutable source observation plus hash, capture time, geospatial metadata, rights, and permitted uses.
- `RightsManifest`: aggregate admissibility decision for all evidence in a build.
- `LocationPassport`: resolved place identity, coordinates, OSM identifiers, aliases, adjacent anchors, and evidence graph.
- `SceneContract`: requested place/time/view/subject constraints and required invariants.
- `ViewCone`: camera origin/orientation/FOV plus uncertainty and visible anchors.
- `TemporalSnapshot`: requested time and compatible evidence interval.
- `GroundingReceipt`: hashes of contract/evidence/output, gate results, transformations, software/model identifiers, and final verdict.

Schemas live in `spec/geocanon/`.

## Evidence policy

Default allowlist:

1. User-owned/user-supplied imagery with sufficient permission.
2. OpenStreetMap-derived place/geometry metadata under applicable ODbL obligations.
3. Explicitly licensed/open imagery whose license permits the intended operation.
4. Provider APIs only within their terms and the recorded permitted-use scope.

Google Maps/Street View imagery is excluded from training, reconstruction, validation, derivative generation, and pixel-producing paths unless a future policy module proves an explicitly permitted use. Do not scrape it.

## Pipeline

1. Resolve place -> `LocationPassport`.
2. Ingest evidence -> immutable `EvidenceNode`s.
3. Evaluate rights -> `RightsManifest`; fail closed on unknown rights.
4. Select a `TemporalSnapshot` compatible with the request.
5. Estimate/register camera and structure -> `ViewCone` with uncertainty.
6. Compile request + evidence -> `SceneContract`.
7. Produce an immutable location plate or geometry-conditioned representation.
8. Composite/generate only inside the contract's mutable regions; preserve hard anchors.
9. Run hard gates: location, rights, spatial structure, view cone, temporal compatibility, persona/subject continuity when applicable, and provenance completeness.
10. Emit `GroundingReceipt`. A failed hard gate means `REJECT`, not a weighted average pass.

## Recommended adapters

Adapters are optional capability providers, not trusted authorities:

- Place/geometry: OSM, Nominatim, Overpass.
- Open street imagery: KartaView, Wikimedia Commons; Mapillary only according to current API/license terms.
- Registration/localization: HLoc, LightGlue, pycolmap/COLMAP.
- Reconstruction: COLMAP first; OpenMVG/OpenMVS or AliceVision as alternatives.
- Dense/novel-view production: NeRF/3D Gaussian Splatting only after the evidence governor is working and rights permit it.
- Retrieval/place recognition: DINO/CLIP-family embeddings, NetVLAD/CosPlace/MixVPR-class methods.
- Geometry conditioning: depth/segmentation/edges and compatible ControlNet-style conditioning.
- Provenance: C2PA-compatible manifest plus internal receipt hash chain.

Pin adapter versions and record executable/model hashes in receipts.

## MVP reference slice

First reference target: Little Village Starbucks, Chicago. Use user-owned imagery plus OSM-derived metadata. Localize/register references with HLoc/LightGlue and COLMAP where feasible. Freeze an immutable background/location plate, permit character compositing only in declared mutable masks, validate view-cone/structure/rights/temporal gates, then emit a receipt.

## Hard gates

- `G_LOCATION_IDENTITY`: resolved place must match contract.
- `G_RIGHTS`: every pixel/evidence dependency must have a permitted-use decision; unknown is failure.
- `G_SPATIAL`: required anchors and relative geometry remain within declared tolerances.
- `G_VIEW_CONE`: requested camera must be supported by evidence/reconstruction and uncertainty bounds.
- `G_TEMPORAL`: evidence snapshot is compatible with requested scene time or explicitly marked historical/uncertain.
- `G_SUBJECT_CANON`: when persistent characters are present, immutable identity traits and relationship/canon constraints pass the consuming character-world evaluator.
- `G_PROVENANCE`: source IDs, hashes, transformations, model/software hashes, output hash, and gate results are complete.

## Evaluation behavior

Treat earlier failed candidates as useful optimization trajectory, but never relax a hard gate to make a candidate pass. Promote repeated failure patterns into explicit invariants and regression fixtures. Separate photographic realism from geographic truth: a visually convincing image can still fail grounding.

## Output contract

Return the generated asset separately from its receipt. Human-facing metadata should distinguish:

- `GROUNDED`: all hard gates passed.
- `PARTIALLY_GROUNDED`: useful evidence exists but at least one requested claim is intentionally weakened/omitted; never present as exact truth.
- `REJECTED`: a hard gate failed.

Never claim exact real-world grounding without a `GROUNDED` receipt.