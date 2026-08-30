---
name: causal-reality-engine
description: Use when generated images, video, handwriting, artifacts, environments, or embodied behavior look superficially realistic but contain decorative randomness, implausible wear, inconsistent physics, continuity breaks, or unexplained imperfections.
---

# Causal Reality Engine

## Core Mandate

Evaluate or specify realism as a causal history, not as a bag of defects.

Optimize for four interacting constraints:

1. Observable effects have plausible causal ancestry.
2. Material, tool, motion, environment, time, and capture state remain mutually compatible.
3. Imperfection stays inside a context-appropriate budget rather than becoming sterile or theatrically distressed.
4. Evaluation emits evidence only and never grants effect authority.

## Operating Principles

- Build `cause -> transition -> effect -> observation` chains before adding visible defects.
- Preserve persistent identity constraints supplied by the caller; do not invent or rewrite them.
- Use counterfactual checks: removing a cause should remove or alter its downstream evidence.
- Treat tool depletion, curing/drying, substrate response, contact, motion, lighting, sensor behavior, and artifact history as stateful processes when relevant.
- Prefer heterogeneous human marks and residues only when their causal histories differ; avoid cloned noise.
- Refuse graphology-style claims: handwriting or appearance cannot establish personality, diagnosis, identity, honesty, or mental state.
- Keep product-specific character vectors and proprietary references outside this generic skill.

## Analysis Sequence

1. Declare the world state, actor/tool/material state, environment, time, and observer/capture state needed for the task.
2. Enumerate consequential visible effects and assign each a causal parent chain.
3. Check for orphan effects, impossible cycles, contradictory states, and continuity breaks.
4. Run counterfactual tests on important causes.
5. Score imperfection density against the scene's opportunity budget.
6. Emit an audit result or generation constraints with `authority: none` and `effect_authority: none`.

## Response Shape

For substantive work return:

- `Causal State`: relevant causes and transitions.
- `Visible Evidence`: effects and observations.
- `Counterfactuals`: what should change if key causes are removed.
- `Findings`: orphan, cycle, continuity, material, capture, or imperfection-budget failures.
- `Receipt`: `ADMITTED` or `REJECTED`, plus `authority: none` and `effect_authority: none`.

Use `scripts/engine.py` when a deterministic graph check is needed. Read `references/causal-reality-contract.md` for the canonical invariants.
