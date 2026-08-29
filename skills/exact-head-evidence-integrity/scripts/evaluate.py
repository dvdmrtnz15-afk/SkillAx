#!/usr/bin/env python3
"""Deterministic Exact-Head Evidence Integrity evaluator.

Classifies supplied repository evidence without granting effect authority.
The evaluator trusts explicit evidence fields; it does not infer a code cause
from workflow trigger, preview status, or a green check alone.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

AUTHORITY_NONE = "none"
RECEIPT_CLASS = "ExactHeadEvidenceReceipt"
HEX40 = set("0123456789abcdef")


def sha256_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def valid_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 40 and set(value.lower()) <= HEX40


def validate(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("job_id", "candidate_id", "repository", "base_sha", "head_sha", "evidence"):
        if key not in payload:
            errors.append(f"missing:{key}")
    if "base_sha" in payload and not valid_sha(payload["base_sha"]):
        errors.append("invalid:base_sha")
    if "head_sha" in payload and not valid_sha(payload["head_sha"]):
        errors.append("invalid:head_sha")
    if "evidence" in payload and not isinstance(payload["evidence"], list):
        errors.append("invalid:evidence")
    return errors


def evaluate(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    errors = validate(payload)
    if errors:
        receipt = {
            "receipt_class": RECEIPT_CLASS,
            "authority": AUTHORITY_NONE,
            "effect_authority": AUTHORITY_NONE,
            "disposition": "REJECTED_INTEGRITY",
            "diagnosis": "INVALID_SUBMISSION",
            "attribution": "unresolved",
            "vetoes": errors,
            "recommendation": "repair_evidence_contract",
            "nonclaims": ["not merge authority", "not deployment authority", "not promotion authority"],
        }
        receipt["content_digest"] = sha256_json(receipt)
        return 2, receipt

    head_sha = payload["head_sha"]
    evidence = payload["evidence"]
    vetoes: list[str] = []

    for item in evidence:
        if not isinstance(item, dict):
            vetoes.append("malformed_evidence_item")
            continue
        if item.get("sha") != head_sha:
            vetoes.append("evidence_bound_to_wrong_sha")
        if item.get("conclusion") == "success" and item.get("kind") == "repository_test" and not item.get("steps_executed"):
            vetoes.append("pass_without_executed_steps")

    if vetoes:
        receipt = build_receipt(
            payload,
            disposition="REJECTED_INTEGRITY",
            diagnosis="EVIDENCE_INTEGRITY_FAILURE",
            attribution="unresolved",
            vetoes=sorted(set(vetoes)),
            recommendation="repair_and_reverify_exact_head",
        )
        return 2, receipt

    repository_evidence = [
        item for item in evidence if isinstance(item, dict) and item.get("kind") == "repository_test"
    ]

    if not repository_evidence:
        receipt = build_receipt(
            payload,
            disposition="INCONCLUSIVE",
            diagnosis="INSUFFICIENT_REPOSITORY_PROOF",
            attribution="unresolved",
            vetoes=[],
            recommendation="collect_executed_repository_evidence",
        )
        return 1, receipt

    infra = [i for i in repository_evidence if i.get("conclusion") == "failure" and i.get("failure_scope") == "infrastructure"]
    if infra:
        return 0, build_receipt(
            payload,
            disposition="VERIFIED",
            diagnosis="INFRASTRUCTURE_FAILURE",
            attribution="infrastructure_not_code",
            vetoes=[],
            recommendation="repair_or_retry_runner_without_weakening_gate",
        )

    dependency = [i for i in repository_evidence if i.get("conclusion") == "failure" and i.get("failure_scope") == "dependency"]
    if dependency:
        return 0, build_receipt(
            payload,
            disposition="VERIFIED",
            diagnosis="DEPENDENCY_FAILURE",
            attribution="dependency_not_caller",
            vetoes=[],
            recommendation="repair_or_verify_dependency_then_retest_caller",
        )

    pr_success = any(
        i.get("trigger") == "pull_request" and i.get("conclusion") == "success" and i.get("steps_executed")
        for i in repository_evidence
    )
    push_workflow_failure = any(
        i.get("trigger") == "push" and i.get("conclusion") == "failure" and i.get("steps_executed") and i.get("failure_scope") == "workflow"
        for i in repository_evidence
    )
    if pr_success and push_workflow_failure:
        return 0, build_receipt(
            payload,
            disposition="VERIFIED",
            diagnosis="WORKFLOW_CONTEXT_BUG",
            attribution="workflow_context_not_code",
            vetoes=[],
            recommendation="apply_smallest_workflow_context_fix_and_reverify_same_head_logic",
        )

    code_failure = any(
        i.get("conclusion") == "failure" and i.get("steps_executed") and i.get("failure_scope") == "code"
        for i in repository_evidence
    )
    if code_failure:
        return 0, build_receipt(
            payload,
            disposition="VERIFIED",
            diagnosis="CODE_REGRESSION",
            attribution="candidate_or_repository_code",
            vetoes=[],
            recommendation="repair_code_without_weakening_required_gate",
        )

    success = any(
        i.get("conclusion") == "success" and i.get("steps_executed") for i in repository_evidence
    )
    if success:
        return 0, build_receipt(
            payload,
            disposition="VERIFIED",
            diagnosis="NO_REGRESSION_OBSERVED",
            attribution="exact_head_repository_evidence",
            vetoes=[],
            recommendation="eligible_for_human_review_not_merge_authority",
        )

    return 1, build_receipt(
        payload,
        disposition="INCONCLUSIVE",
        diagnosis="UNRESOLVED_FAILURE",
        attribution="unresolved",
        vetoes=[],
        recommendation="collect_bounded_diagnostic_evidence",
    )


def build_receipt(
    payload: dict[str, Any],
    *,
    disposition: str,
    diagnosis: str,
    attribution: str,
    vetoes: list[str],
    recommendation: str,
) -> dict[str, Any]:
    receipt = {
        "receipt_class": RECEIPT_CLASS,
        "authority": AUTHORITY_NONE,
        "effect_authority": AUTHORITY_NONE,
        "job_id": payload.get("job_id"),
        "candidate_id": payload.get("candidate_id"),
        "repository": payload.get("repository"),
        "base_sha": payload.get("base_sha"),
        "head_sha": payload.get("head_sha"),
        "evidence_digest": sha256_json(payload.get("evidence", [])),
        "disposition": disposition,
        "diagnosis": diagnosis,
        "attribution": attribution,
        "vetoes": vetoes,
        "recommendation": recommendation,
        "nonclaims": [
            "not merge authority",
            "not deployment authority",
            "not rebase authority",
            "not promotion authority",
        ],
    }
    receipt["content_digest"] = sha256_json(receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate exact-head repository evidence")
    parser.add_argument("--input", required=True, help="submission evidence JSON")
    parser.add_argument("--out", default="", help="receipt JSON output path")
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    code, receipt = evaluate(payload)
    text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(out.as_posix())
    else:
        sys.stdout.write(text)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
