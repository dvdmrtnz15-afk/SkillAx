#!/usr/bin/env python3
"""Adversarial regression tests for GeoCanon's fail-closed semantics."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/geocanon/little-village-starbucks.reference.json"
VALIDATOR = ROOT / "scripts/geocanon_validate.py"

spec = importlib.util.spec_from_file_location("geocanon_validate", VALIDATOR)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def load() -> dict:
    return json.loads(FIXTURE.read_text())


def expect_pass(name: str, bundle: dict) -> None:
    ok, errors = mod.validate(bundle)
    assert ok, f"{name}: expected PASS, got {errors}"


def expect_reject(name: str, bundle: dict, contains: str) -> None:
    ok, errors = mod.validate(bundle)
    assert not ok, f"{name}: expected REJECT"
    joined = "\n".join(errors)
    assert contains in joined, f"{name}: expected {contains!r} in {joined!r}"


def main() -> int:
    base = load()
    expect_pass("reference fixture", base)

    case = copy.deepcopy(base)
    case["location_passport"]["location_id"] = "place:wrong"
    expect_reject("location mismatch", case, "G_LOCATION_IDENTITY")

    case = copy.deepcopy(base)
    case["evidence"][0]["rights"]["status"] = "unknown"
    case["rights_manifest"]["evidence_decisions"]["ev-user-reference-set-001"] = "unknown"
    expect_reject("unknown rights", case, "G_RIGHTS")

    case = copy.deepcopy(base)
    case["rights_manifest"]["verdict"] = "FAIL"
    expect_reject("manifest fail", case, "rights_manifest verdict must be PASS")

    case = copy.deepcopy(base)
    e = case["evidence"][0]
    e["source_uri"] = "https://www.google.com/maps/@41.0,-87.0,3a"
    e["rights"]["source_type"] = "provider_api"
    e["rights"]["permitted_uses"] = ["validation", "reconstruction"]
    expect_reject("google pixel exclusion", case, "prohibited Google Maps/Street View pixel use")

    case = copy.deepcopy(base)
    case["evidence"][0]["content_hash"] = ""
    expect_reject("missing evidence hash", case, "G_PROVENANCE")

    case = copy.deepcopy(base)
    case["scene_contract"]["required_gates"] = ["G_SPATIAL"]
    expect_reject("mandatory gates omitted", case, "must require location, rights, and provenance")

    # Receipt claims must not be able to launder an invalid bundle into GROUNDED.
    case = copy.deepcopy(base)
    contract_hash = mod.canonical_hash(case["scene_contract"])
    case["grounding_receipt"] = {
        "receipt_version": "0.1",
        "contract_hash": contract_hash,
        "output_hash": "3" * 64,
        "evidence_hashes": [e["content_hash"] for e in case["evidence"]],
        "gate_results": {g: "PASS" for g in case["scene_contract"]["required_gates"]},
        "transformations": [],
        "software": [],
        "verdict": "GROUNDED",
    }
    expect_pass("coherent receipt", case)

    case["grounding_receipt"]["contract_hash"] = "4" * 64
    expect_reject("receipt hash mismatch", case, "contract_hash mismatch")

    print("GEOCANON REGRESSION PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
