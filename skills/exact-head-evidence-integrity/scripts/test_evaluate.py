#!/usr/bin/env python3
"""Deterministic acceptance tests for Exact-Head Evidence Integrity."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

EVALUATE = Path(__file__).resolve().parent / "evaluate.py"


def run_case(payload: dict) -> tuple[subprocess.CompletedProcess[str], dict]:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inp = root / "evidence.json"
        out = root / "receipt.json"
        inp.write_text(json.dumps(payload), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(EVALUATE), "--input", str(inp), "--out", str(out)],
            text=True,
            capture_output=True,
        )
        receipt = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
        return proc, receipt


def base_payload() -> dict:
    return {
        "job_id": "job-1",
        "candidate_id": "candidate-1",
        "repository": "owner/repo",
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "evidence": [],
    }


def test_zero_step_pass_is_integrity_rejection() -> None:
    p = base_payload()
    p["evidence"] = [{
        "kind": "repository_test",
        "sha": p["head_sha"],
        "trigger": "pull_request",
        "conclusion": "success",
        "steps_executed": False,
        "failure_scope": "unknown",
    }]
    proc, receipt = run_case(p)
    assert proc.returncode == 2
    assert receipt["disposition"] == "REJECTED_INTEGRITY"
    assert "pass_without_executed_steps" in receipt["vetoes"]


def test_preview_is_not_repository_proof() -> None:
    p = base_payload()
    p["evidence"] = [{
        "kind": "preview",
        "sha": p["head_sha"],
        "trigger": "pull_request",
        "conclusion": "success",
        "steps_executed": True,
        "failure_scope": "unknown",
    }]
    proc, receipt = run_case(p)
    assert proc.returncode == 1
    assert receipt["disposition"] == "INCONCLUSIVE"
    assert receipt["diagnosis"] == "INSUFFICIENT_REPOSITORY_PROOF"


def test_same_sha_pr_pass_push_workflow_fail_is_context_bug() -> None:
    p = base_payload()
    p["evidence"] = [
        {
            "kind": "repository_test",
            "sha": p["head_sha"],
            "trigger": "pull_request",
            "conclusion": "success",
            "steps_executed": True,
            "failure_scope": "code",
        },
        {
            "kind": "repository_test",
            "sha": p["head_sha"],
            "trigger": "push",
            "conclusion": "failure",
            "steps_executed": True,
            "failure_scope": "workflow",
        },
    ]
    proc, receipt = run_case(p)
    assert proc.returncode == 0
    assert receipt["diagnosis"] == "WORKFLOW_CONTEXT_BUG"
    assert receipt["disposition"] == "VERIFIED"


def test_dependency_failure_is_not_attributed_to_caller() -> None:
    p = base_payload()
    p["evidence"] = [{
        "kind": "repository_test",
        "sha": p["head_sha"],
        "trigger": "pull_request",
        "conclusion": "failure",
        "steps_executed": True,
        "failure_scope": "dependency",
    }]
    proc, receipt = run_case(p)
    assert proc.returncode == 0
    assert receipt["diagnosis"] == "DEPENDENCY_FAILURE"
    assert receipt["attribution"] == "dependency_not_caller"


def test_infrastructure_failure_is_distinct() -> None:
    p = base_payload()
    p["evidence"] = [{
        "kind": "repository_test",
        "sha": p["head_sha"],
        "trigger": "pull_request",
        "conclusion": "failure",
        "steps_executed": False,
        "failure_scope": "infrastructure",
    }]
    proc, receipt = run_case(p)
    assert proc.returncode == 0
    assert receipt["diagnosis"] == "INFRASTRUCTURE_FAILURE"
    assert receipt["disposition"] == "VERIFIED"


def test_stale_sha_is_integrity_rejection() -> None:
    p = base_payload()
    p["evidence"] = [{
        "kind": "repository_test",
        "sha": "c" * 40,
        "trigger": "pull_request",
        "conclusion": "success",
        "steps_executed": True,
        "failure_scope": "code",
    }]
    proc, receipt = run_case(p)
    assert proc.returncode == 2
    assert receipt["disposition"] == "REJECTED_INTEGRITY"
    assert "evidence_bound_to_wrong_sha" in receipt["vetoes"]


def test_real_code_failure_is_preserved() -> None:
    p = base_payload()
    p["evidence"] = [{
        "kind": "repository_test",
        "sha": p["head_sha"],
        "trigger": "pull_request",
        "conclusion": "failure",
        "steps_executed": True,
        "failure_scope": "code",
    }]
    proc, receipt = run_case(p)
    assert proc.returncode == 0
    assert receipt["diagnosis"] == "CODE_REGRESSION"
    assert receipt["disposition"] == "VERIFIED"


def test_receipt_never_grants_effect_authority() -> None:
    p = base_payload()
    p["evidence"] = [{
        "kind": "repository_test",
        "sha": p["head_sha"],
        "trigger": "pull_request",
        "conclusion": "success",
        "steps_executed": True,
        "failure_scope": "code",
    }]
    proc, receipt = run_case(p)
    assert proc.returncode == 0
    assert receipt["authority"] == "none"
    assert receipt["effect_authority"] == "none"
    assert receipt["recommendation"] != "merge"


def main() -> int:
    tests = [
        test_zero_step_pass_is_integrity_rejection,
        test_preview_is_not_repository_proof,
        test_same_sha_pr_pass_push_workflow_fail_is_context_bug,
        test_dependency_failure_is_not_attributed_to_caller,
        test_infrastructure_failure_is_distinct,
        test_stale_sha_is_integrity_rejection,
        test_real_code_failure_is_preserved,
        test_receipt_never_grants_effect_authority,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"validated {len(tests)} exact-head test(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
