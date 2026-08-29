---
name: exact-head-evidence-integrity
description: Classify GitHub PR and CI evidence against an exact repository head without treating previews, zero-step checks, dependency failures, or infrastructure failures as code proof. Use for merge-readiness analysis, CI diagnosis, stale-head detection, and evidence-bound review receipts.
---

# Exact-Head Evidence Integrity

Evaluate repository evidence before making a PR or CI claim. The skill classifies what the evidence proves; it never grants effect authority.

## Core mandate

1. Bind every evaluation to `job_id`, `candidate_id`, repository, base SHA, and exact head SHA.
2. Reject evidence attached to another head.
3. Reject a claimed repository pass when no real repository test steps executed.
4. Never treat a preview deployment as repository correctness proof.
5. Separate code regression, workflow-context failure, dependency failure, and infrastructure failure.
6. Emit a deterministic receipt with `authority: none` and `effect_authority: none`.

## Operating principles

- Evidence first. Trigger names and green badges are not diagnoses.
- Same SHA is necessary for direct comparison; it is not sufficient to infer cause.
- `failure_scope` must come from bounded evidence or an upstream deterministic classifier. Do not invent it from intuition.
- A dependency-engine failure is not automatically a caller failure.
- A runner or zero-step infrastructure failure is not a code regression.
- Stale-head or wrong-head evidence is an integrity veto, not a warning.
- Gate weakening is never a valid repair strategy.
- `VERIFIED` means the diagnosis is supported by the submitted evidence. It does not mean merge, deploy, rebase, or promotion is authorized.

## Input contract

Supply JSON with these top-level fields:

```json
{
  "job_id": "job-123",
  "candidate_id": "candidate-1",
  "repository": "owner/repo",
  "base_sha": "40-hex-sha",
  "head_sha": "40-hex-sha",
  "evidence": []
}
```

Each evidence item uses:

- `kind`: `repository_test` or `preview`
- `sha`: exact commit tested
- `trigger`: for example `pull_request`, `push`, or `workflow_dispatch`
- `conclusion`: `success`, `failure`, or another explicit check state
- `steps_executed`: boolean
- `failure_scope`: `code`, `workflow`, `dependency`, `infrastructure`, or `unknown`

## Deterministic diagnoses

The first slice supports these benchmark families:

- zero-step check reporting success → `REJECTED_INTEGRITY`
- preview-only success → `INSUFFICIENT_REPOSITORY_PROOF`
- same-head PR success plus push workflow failure → `WORKFLOW_CONTEXT_BUG`
- dependency-scoped failure → `DEPENDENCY_FAILURE`
- infrastructure-scoped failure → `INFRASTRUCTURE_FAILURE`
- evidence from another SHA → `REJECTED_INTEGRITY`
- executed code-scoped failure → `CODE_REGRESSION`
- executed exact-head repository success with no contradictory failure → `NO_REGRESSION_OBSERVED`

## Run

```bash
python3 skills/exact-head-evidence-integrity/scripts/evaluate.py \
  --input evidence.json \
  --out receipt.json
```

Run deterministic acceptance tests with:

```bash
python3 skills/exact-head-evidence-integrity/scripts/test_evaluate.py
```

## Receipt semantics

Exit code `0` means the submitted evidence supports a bounded diagnosis. Exit code `1` means evidence is inconclusive. Exit code `2` means an integrity veto occurred. Every output remains non-authorizing.

The receipt preserves exact target identity, an evidence digest, diagnosis, attribution, vetoes, a bounded next recommendation, and explicit nonclaims.

## Refusals

- Do not infer merge readiness from preview status.
- Do not bind evidence from one SHA to another.
- Do not call an infrastructure outage a regression.
- Do not blame a caller for a dependency failure without caller-specific evidence.
- Do not fabricate executed steps, review evidence, or failure scope.
- Do not recommend weakening a required gate to obtain green status.
- Do not merge, deploy, rebase, or promote from this receipt.

## Architecture binding

This skill implements the first SkillAx evaluator slice for Organism Automated Alignment Research chapter 16, Exact-Head Evidence Integrity. It consumes the frozen submit-artifact identity and evidence boundary and produces a non-promoting evaluation receipt. ProofKernel admission and any effect authorization remain downstream and external.
