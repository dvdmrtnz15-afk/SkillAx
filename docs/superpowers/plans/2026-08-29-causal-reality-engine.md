# Causal Reality Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one reusable SkillAx L2 skill that evaluates generated realism from explicit causal world-state transitions instead of decorative imperfection.

**Architecture:** Keep persistent identity and relationship continuity in `persistent-character-world-system`. Add an audit-only `causal-reality-engine` that evaluates causal parents, cycles, counterfactual dependencies, and bounded imperfection density. Compose domain use cases through recipes rather than proliferating modality-specific skills.

**Tech Stack:** Markdown SKILL.md, JSON typed axioms/recipes, Python 3 standard library evaluator/tests.

**Spec:** `skills/causal-reality-engine/references/causal-reality-contract.md`

## Global Constraints

- Generic reusable logic only; no Solara-specific canon or product-owned identity vectors.
- `authority: none` and `effect_authority: none` on evaluator receipts.
- No personality, diagnosis, identity, or truth inference from handwriting or appearance.
- Visible imperfections require causal ancestry or explicit rejection.
- Modality variants remain recipes until independently reusable procedural knowledge is demonstrated.

---

### Task 1: Deterministic evaluator
**Files:** Create `skills/causal-reality-engine/scripts/test_engine.py`; create `skills/causal-reality-engine/scripts/engine.py`.
- [x] Write failing tests for orphan effects, cycles, counterfactual propagation, imperfection bounds, and authority-none receipts.
- [x] Run tests and observe missing-engine failure.
- [x] Implement minimal evaluator.
- [x] Run tests and observe all tests pass.

### Task 2: L2 skill package
**Files:** Create `skills/causal-reality-engine/SKILL.md`, `axioms.json`, and reference contract.
- [x] Encode 3–5 typed axioms with one job and refusal/safety boundaries.
- [x] Keep runtime export concise and transferable.

### Task 3: Fixtures and recipes
**Files:** Create `fixtures/causal-reality-engine/in.md`, `out.md`; create realism recipes under `recipes/`.
- [x] Cover one admitted causal scene plus sterile, theatrical, orphan, and inference-refusal cases.
- [x] Compose handwriting/camera/embodied-character use without creating additional skills.

### Task 4: Catalog integration and verification
**Files:** Modify `CATALOG.json`.
- [x] Register the ninth active app.
- [x] Run Python tests and JSON parse checks.
- [ ] Run repository-wide SkillAx validation and hosted CI on exact branch head.
