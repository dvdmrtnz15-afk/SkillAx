#!/usr/bin/env python3
"""Fail-closed validator for a GeoCanon/SceneProof bundle.

Stdlib only so the invariant check can run in minimal CI environments.
Schema validation can be layered on separately; this validator enforces the
security/grounding semantics that JSON Schema alone cannot express.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

HARD_GATES = {
    "G_LOCATION_IDENTITY",
    "G_RIGHTS",
    "G_SPATIAL",
    "G_VIEW_CONE",
    "G_TEMPORAL",
    "G_SUBJECT_CANON",
    "G_PROVENANCE",
}
PIXEL_USES = {"validation", "reconstruction", "derivative_generation"}


def canonical_hash(obj: object) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def validate(bundle: dict) -> tuple[bool, list[str]]:
    errors: list[str] = []
    contract = bundle.get("scene_contract") or {}
    passport = bundle.get("location_passport") or {}
    evidence = bundle.get("evidence") or []
    rights_manifest = bundle.get("rights_manifest") or {}

    if contract.get("location_id") != passport.get("location_id"):
        errors.append("G_LOCATION_IDENTITY: contract/passport location_id mismatch")

    evidence_ids = [e.get("evidence_id") for e in evidence]
    if not evidence or any(not x for x in evidence_ids) or len(set(evidence_ids)) != len(evidence_ids):
        errors.append("G_PROVENANCE: evidence IDs must be present and unique")

    decisions = rights_manifest.get("evidence_decisions") or {}
    for e in evidence:
        eid = e.get("evidence_id")
        rights = e.get("rights") or {}
        status = rights.get("status", "unknown")
        if status != "allowed" or decisions.get(eid) != "allowed":
            errors.append(f"G_RIGHTS: {eid or '<missing>'} is not explicitly allowed")
        uri = (e.get("source_uri") or "").lower()
        uses = set(rights.get("permitted_uses") or [])
        # Architecture-level exclusion: Google map/street-view pixels cannot
        # silently enter validation/reconstruction/derivative paths.
        if ("google.com/maps" in uri or "streetview" in uri or "street_view" in uri) and uses & PIXEL_USES:
            errors.append(f"G_RIGHTS: prohibited Google Maps/Street View pixel use in {eid}")
        if not e.get("content_hash"):
            errors.append(f"G_PROVENANCE: missing content_hash for {eid}")

    if rights_manifest.get("verdict") != "PASS":
        errors.append("G_RIGHTS: rights_manifest verdict must be PASS")

    required = set(contract.get("required_gates") or [])
    unknown = required - HARD_GATES
    if unknown:
        errors.append(f"SceneContract contains unknown gates: {sorted(unknown)}")
    if "G_RIGHTS" not in required or "G_PROVENANCE" not in required or "G_LOCATION_IDENTITY" not in required:
        errors.append("SceneContract must require location, rights, and provenance gates")

    receipt = bundle.get("grounding_receipt")
    if receipt:
        results = receipt.get("gate_results") or {}
        for gate in required:
            if results.get(gate) != "PASS":
                errors.append(f"{gate}: receipt does not record PASS")
        expected_contract_hash = canonical_hash(contract)
        if receipt.get("contract_hash") != expected_contract_hash:
            errors.append("G_PROVENANCE: receipt contract_hash mismatch")
        source_hashes = {e.get("content_hash") for e in evidence if e.get("content_hash")}
        if set(receipt.get("evidence_hashes") or []) != source_hashes:
            errors.append("G_PROVENANCE: receipt evidence_hashes do not exactly match evidence")
        if errors and receipt.get("verdict") == "GROUNDED":
            errors.append("Receipt claims GROUNDED despite failed invariant(s)")

    return not errors, errors


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("bundle", type=Path)
    args = p.parse_args()
    bundle = json.loads(args.bundle.read_text())
    ok, errors = validate(bundle)
    if ok:
        print("GEOCANON PASS")
        return 0
    print("GEOCANON REJECT", file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
