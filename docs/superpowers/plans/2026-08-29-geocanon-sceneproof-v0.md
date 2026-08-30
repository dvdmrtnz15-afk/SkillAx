# GeoCanon / SceneProof v0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the fail-closed GeoCanon / SceneProof v0 kernel on the existing SkillAx feature branch and make the exact-head validation workflow pass.

**Architecture:** Extend the existing Python stdlib implementation rather than introducing a second runtime. JSON remains the portable interchange format; `geocanon_validate.py` owns semantic admission, `geocanon_compile.py` deterministically selects the least-generative admissible render mode, and `geocanon_receipt.py` mints a receipt only after all required hard gates pass.

**Tech Stack:** Python 3.12 standard library, JSON Schema 2020-12, Markdown skill contract, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-29-geocanon-sceneproof-v0-design.md`

## Global Constraints

- SkillAx remains a schema/skill distribution layer, not an authority or publishing plane.
- Python implementation must remain standard-library only.
- Unknown or omitted rights fail closed.
- Generated evidence has zero truth authority.
- Google Maps/Street View pixels are prohibited from validation, reconstruction, derivative generation, and other pixel-producing paths.
- When a usable immutable location plate exists, the compiler must choose `immutable_plate`.
- Reference social output is one standalone 9:16 image with no collage, grid, panels, storyboard, or unrequested text overlay.
- User-supplied images are not committed; the Little Village fixture remains metadata-only with placeholder hashes.
- No merge or deployment is performed by this plan.

---

### Task 1: Restore the SkillAx Contract and Freeze the Expanded Fixture

**Files:**
- Modify: `skills/geocanon-sceneproof/SKILL.md`
- Modify: `spec/geocanon/geocanon.schema.json`
- Modify: `fixtures/geocanon/little-village-starbucks.reference.json`

**Interfaces:**
- Consumes: existing GeoCanon v0 bundle fields.
- Produces: expanded bundle fields consumed by validator, compiler, and receipt scripts.

- [ ] **Step 1: Run the current skill validator and capture the expected failure**

Run:

```bash
python3 scripts/validate.py skills/geocanon-sceneproof
```

Expected: failure reporting missing `core mandate` and `operating principles`.

- [ ] **Step 2: Rename/add the required skill sections without weakening policy**

The skill must contain exact Markdown headings:

```markdown
## Core Mandate
## Operating Principles
```

`Core Mandate` states that exact grounding requires admitted rights, place identity, spatial support, temporal support, render-policy compliance, and provenance. `Operating Principles` states least-generative routing, typed evidence roles, zero generated authority, zone separation, immutable plates when available, and hard-gate rejection.

- [ ] **Step 3: Expand the schema and Little Village fixture**

Add exact fields used by later tasks:

```json
{
  "location_passport": {
    "canonical_address": "3105 W 26th St, Chicago, IL 60623",
    "zones": ["exterior_entrance", "exterior_patio", "interior_counter", "interior_mural_wall"],
    "structural_invariants": ["primary_storefront", "entrance_position", "parking_axis", "adjacent_plaza_context"],
    "prohibited_mutations": ["brick_corner_store", "downtown_streetwall", "generic_drive_through", "interior_exterior_blending"]
  },
  "scene_contract": {
    "zone": "exterior_entrance",
    "target_snapshot": {"as_of": "2026-08-29T00:00:00Z", "max_appearance_age_days": 180},
    "format": {"image_count": 1, "standalone": true, "aspect_ratio": "9:16", "collage": false, "text_overlay": false},
    "render_policy": {"allowed_modes": ["immutable_plate", "multiview_reconstruction", "constrained_generation"], "prefer_least_generative": true}
  }
}
```

Each evidence node gains `role`, `authority`, `zone`, and `temporal_class`.

- [ ] **Step 4: Run the skill validator**

Run:

```bash
python3 scripts/validate.py skills/geocanon-sceneproof
```

Expected: `OK geocanon-sceneproof` and exit code 0.

- [ ] **Step 5: Commit**

```bash
git add skills/geocanon-sceneproof/SKILL.md spec/geocanon/geocanon.schema.json fixtures/geocanon/little-village-starbucks.reference.json
git commit -m "feat: expand GeoCanon scene contract"
```

### Task 2: Add Failing Semantic Admission Regressions

**Files:**
- Modify: `scripts/geocanon_test.py`
- Test: `scripts/geocanon_test.py`

**Interfaces:**
- Consumes: `validate(bundle: dict) -> tuple[bool, list[str]]` from `scripts/geocanon_validate.py`.
- Produces: regression expectations that define the validator changes in Task 3.

- [ ] **Step 1: Add tests for generated authority, zone, time, format, view cone, and evidence graph**

Add independent cases that expect rejection when:

```python
case["evidence"][0]["role"] = "generated_continuity"
case["evidence"][0]["authority"] = "location_truth"
```

```python
case["scene_contract"]["zone"] = "interior_mural_wall"
```

```python
case["scene_contract"]["format"]["image_count"] = 6
case["scene_contract"]["format"]["collage"] = True
```

```python
case["view_cone"]["visible_anchors"].remove("primary_storefront")
```

```python
case["location_passport"]["evidence_node_ids"].append("ev-missing")
```

```python
case["evidence"][0]["captured_at"] = "2024-01-01T00:00:00Z"
```

Each case must assert the exact gate prefix (`G_RIGHTS`, `G_SPATIAL`, `G_FORMAT`, `G_VIEW_CONE`, `G_PROVENANCE`, or `G_TEMPORAL`).

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python3 scripts/geocanon_test.py
```

Expected: at least one new assertion fails because the current validator does not enforce the new invariant.

- [ ] **Step 3: Commit the red tests**

```bash
git add scripts/geocanon_test.py
git commit -m "test: define GeoCanon fail-closed admission"
```

### Task 3: Implement Fail-Closed Semantic Validation

**Files:**
- Modify: `scripts/geocanon_validate.py`
- Test: `scripts/geocanon_test.py`

**Interfaces:**
- Consumes: expanded GeoCanon bundle.
- Produces: `validate(bundle, require_render_plan=False)` plus reusable `canonical_hash`, ISO time parsing, evidence indexing, and admissibility helpers.

- [ ] **Step 1: Add expanded hard-gate and evidence constants**

Define:

```python
HARD_GATES = {
    "G_LOCATION_IDENTITY", "G_RIGHTS", "G_SPATIAL", "G_VIEW_CONE",
    "G_TEMPORAL", "G_SUBJECT_CANON", "G_FORMAT", "G_RENDER_POLICY",
    "G_OBJECT_INTEGRITY", "G_PROVENANCE",
}
MANDATORY_GATES = {
    "G_LOCATION_IDENTITY", "G_RIGHTS", "G_SPATIAL", "G_TEMPORAL",
    "G_FORMAT", "G_RENDER_POLICY", "G_PROVENANCE",
}
```

- [ ] **Step 2: Implement evidence graph, role, authority, zone, and rights checks**

The validator must reject:

- passport evidence IDs absent from the evidence array;
- rights decisions that omit or contradict an evidence node;
- generated evidence with authority other than `none`;
- `generated_continuity` used for location validation, reconstruction, or derivative generation;
- location truth evidence whose role is not location/metadata evidence;
- location evidence with a zone incompatible with the scene zone when used for exact appearance.

- [ ] **Step 3: Implement temporal, format, and view-cone checks**

Use timezone-aware ISO parsing. Reject stale current-appearance evidence older than `max_appearance_age_days`; require exact one-image standalone output; reject collage/text overlay; require contract anchors in `view_cone.visible_anchors`; reject overlap with `view_cone.must_not_be_visible`.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
python3 scripts/geocanon_validate.py fixtures/geocanon/little-village-starbucks.reference.json
python3 scripts/geocanon_test.py
```

Expected: `GEOCANON PASS` and `GEOCANON REGRESSION PASS`.

- [ ] **Step 5: Commit**

```bash
git add scripts/geocanon_validate.py scripts/geocanon_test.py
git commit -m "feat: enforce GeoCanon admission gates"
```

### Task 4: Build the Deterministic Render Router

**Files:**
- Create: `scripts/geocanon_compile.py`
- Modify: `scripts/geocanon_test.py`

**Interfaces:**
- Consumes: `validate(bundle)` and `canonical_hash(obj)` from `geocanon_validate.py`.
- Produces: `compile_render_plan(bundle: dict) -> dict` and CLI `python3 scripts/geocanon_compile.py BUNDLE --out PLAN`.

- [ ] **Step 1: Add compiler tests before implementation**

Tests must assert:

```python
plan = compiler.compile_render_plan(base)
assert plan["render_mode"] == "immutable_plate"
assert plan["evidence_ids"] == ["ev-user-reference-set-001"]
assert plan["mutable_regions"] == ["foreground_subject_mask"]
```

A second case removes the plate role and supplies two admissible reconstruction nodes; expected mode is `multiview_reconstruction`. A third supplies geometry plus appearance and permits generation; expected mode is `constrained_generation`. A fourth lacks admissible support and must raise `ValueError`.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python3 scripts/geocanon_test.py
```

Expected: import or attribute failure because `geocanon_compile.py` does not exist.

- [ ] **Step 3: Implement `compile_render_plan`**

The router must filter by rights decision, permitted uses, evidence role, authority, and zone. It must choose modes in this order:

```python
("immutable_plate", "multiview_reconstruction", "constrained_generation")
```

The returned plan contains:

```python
{
    "plan_version": "0.2",
    "contract_hash": canonical_hash(scene_contract),
    "location_id": scene_contract["location_id"],
    "zone": scene_contract["zone"],
    "render_mode": selected_mode,
    "evidence_ids": selected_ids,
    "immutable_anchors": scene_contract["required_anchors"],
    "mutable_regions": scene_contract["mutable_regions"],
    "target_snapshot": scene_contract["target_snapshot"],
    "format": scene_contract["format"]
}
```

- [ ] **Step 4: Run tests and CLI verification**

Run:

```bash
python3 scripts/geocanon_test.py
python3 scripts/geocanon_compile.py fixtures/geocanon/little-village-starbucks.reference.json --out /tmp/geocanon-plan.json
python3 -c 'import json; p=json.load(open("/tmp/geocanon-plan.json")); assert p["render_mode"] == "immutable_plate"'
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/geocanon_compile.py scripts/geocanon_test.py
git commit -m "feat: add deterministic GeoCanon render router"
```

### Task 5: Bind Ingest and Receipts to Typed Evidence and Render Plans

**Files:**
- Modify: `scripts/geocanon_ingest.py`
- Modify: `scripts/geocanon_receipt.py`
- Modify: `scripts/geocanon_test.py`

**Interfaces:**
- Consumes: typed evidence contract and compiler render plan.
- Produces: evidence nodes with explicit `role`, `authority`, `zone`, and `temporal_class`; receipts with `render_plan_hash` and `render_mode`.

- [ ] **Step 1: Add receipt tamper tests before implementation**

Create a render plan with the compiler, mint an in-memory coherent receipt shape, and assert validator rejection when `render_plan_hash` changes or when `render_mode` differs from the plan.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python3 scripts/geocanon_test.py
```

Expected: new receipt assertions fail because render-plan binding is not implemented.

- [ ] **Step 3: Extend ingest CLI**

Add required arguments:

```text
--role
--authority
--temporal-class
```

Add optional `--zone`. Reject `source_type=generated` unless `role=generated_continuity` and `authority=none`.

- [ ] **Step 4: Extend receipt CLI**

Add required `--render-plan`. Verify its `contract_hash`, include `render_plan_hash` and `render_mode`, and refuse `GROUNDED` if the selected mode violates the scene policy.

- [ ] **Step 5: Run tests**

Run:

```bash
python3 scripts/geocanon_test.py
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/geocanon_ingest.py scripts/geocanon_receipt.py scripts/geocanon_test.py
git commit -m "feat: bind evidence and receipts to render plans"
```

### Task 6: Wire Exact-Head Verification and Close the Draft Slice

**Files:**
- Modify: `.github/workflows/validate.yml`
- Modify: `skills/geocanon-sceneproof/SKILL.md`
- Modify: `docs/superpowers/specs/2026-08-29-geocanon-sceneproof-v0-design.md` only if implementation differs from the approved design.

**Interfaces:**
- Consumes: all previous task outputs.
- Produces: one CI path proving schema/skill semantics, compiler routing, and adversarial regressions.

- [ ] **Step 1: Add compiler smoke verification to CI**

Add:

```yaml
- run: python3 scripts/geocanon_compile.py fixtures/geocanon/little-village-starbucks.reference.json --out /tmp/geocanon-plan.json
```

Keep the existing repository validator, GeoCanon validator, and regression test commands.

- [ ] **Step 2: Run the exact local command sequence**

```bash
python3 scripts/validate.py --all
python3 scripts/rank_test.py
python3 scripts/measure.py packs/skillax --expect PASS
python3 skills/sentinel-audit-lane/scripts/test_scan.py
python3 scripts/geocanon_validate.py fixtures/geocanon/little-village-starbucks.reference.json
python3 scripts/geocanon_test.py
python3 scripts/geocanon_compile.py fixtures/geocanon/little-village-starbucks.reference.json --out /tmp/geocanon-plan.json
```

Expected: every command exits 0.

- [ ] **Step 3: Push and verify the exact branch head**

Verify GitHub Actions `validate / skills` passes for the new exact head SHA. Do not rely on an older run.

- [ ] **Step 4: Update PR #12 body with final scope and evidence**

Record the exact head SHA, commands run, regression coverage, architecture boundary, and remaining phase-two exclusions. Keep the PR draft unless the user explicitly authorizes advancing it.

- [ ] **Step 5: Final review checkpoint**

Confirm no merge or deployment occurred, no user images were committed, and no provider imagery was ingested.
