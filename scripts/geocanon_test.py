#!/usr/bin/env python3
"""Adversarial regression tests for GeoCanon's fail-closed semantics."""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/geocanon/little-village-starbucks.reference.json"
VALIDATOR = ROOT / "scripts/geocanon_validate.py"

spec = importlib.util.spec_from_file_location("geocanon_validate", VALIDATOR)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)

COMPILER = ROOT / "scripts/geocanon_compile.py"
compiler_spec = importlib.util.spec_from_file_location("geocanon_compile", COMPILER)
compiler = importlib.util.module_from_spec(compiler_spec)
assert compiler_spec and compiler_spec.loader
compiler_spec.loader.exec_module(compiler)


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
    expect_reject("mandatory gates omitted", case, "omits mandatory gates")

    case = copy.deepcopy(base)
    case["evidence"][0]["rights"]["source_type"] = "generated"
    case["evidence"][0]["role"] = "generated_continuity"
    case["evidence"][0]["authority"] = "location_truth"
    expect_reject("generated authority", case, "G_RIGHTS")

    case = copy.deepcopy(base)
    case["scene_contract"]["zone"] = "interior_mural_wall"
    expect_reject("zone contamination", case, "G_SPATIAL")

    case = copy.deepcopy(base)
    case["scene_contract"]["format"]["image_count"] = 6
    case["scene_contract"]["format"]["collage"] = True
    expect_reject("collage output", case, "G_FORMAT")

    case = copy.deepcopy(base)
    case["view_cone"]["visible_anchors"].remove("primary_storefront")
    expect_reject("view cone missing anchor", case, "G_VIEW_CONE")

    case = copy.deepcopy(base)
    case["location_passport"]["evidence_node_ids"].append("ev-missing")
    expect_reject("missing evidence graph node", case, "G_PROVENANCE")

    case = copy.deepcopy(base)
    case["evidence"][0]["captured_at"] = "2024-01-01T00:00:00Z"
    expect_reject("stale current appearance", case, "G_TEMPORAL")

    plan = compiler.compile_render_plan(base)
    assert plan["render_mode"] == "immutable_plate", plan
    assert plan["evidence_ids"] == ["ev-user-reference-set-001"], plan
    assert plan["mutable_regions"] == ["foreground_subject_mask"], plan

    case = copy.deepcopy(base)
    case["render_plan"] = compiler.compile_render_plan(case)
    case["render_plan"]["render_mode"] = "constrained_generation"
    expect_reject("non-minimal render plan", case, "least-generative")

    case = copy.deepcopy(base)
    template = case["evidence"][0]
    geom1 = copy.deepcopy(template)
    geom1.update({
        "evidence_id": "ev-geom-001",
        "role": "location_geometry",
        "temporal_class": "structural",
        "captured_at": "2025-08-29T00:00:00Z",
        "content_hash": "3" * 64,
    })
    geom1["rights"]["permitted_uses"] = ["retrieval", "validation", "reconstruction"]
    geom2 = copy.deepcopy(geom1)
    geom2.update({"evidence_id": "ev-geom-002", "content_hash": "4" * 64})
    appearance = copy.deepcopy(template)
    appearance.update({
        "evidence_id": "ev-appearance-001",
        "role": "location_appearance",
        "content_hash": "5" * 64,
    })
    appearance["rights"]["permitted_uses"] = ["retrieval", "validation", "display"]
    metadata = copy.deepcopy(case["evidence"][1])
    case["evidence"] = [geom1, geom2, appearance, metadata]
    ids = [e["evidence_id"] for e in case["evidence"]]
    case["location_passport"]["evidence_node_ids"] = ids
    case["rights_manifest"]["evidence_decisions"] = {eid: "allowed" for eid in ids}
    plan = compiler.compile_render_plan(case)
    assert plan["render_mode"] == "multiview_reconstruction", plan
    assert plan["evidence_ids"] == ["ev-geom-001", "ev-geom-002"], plan

    case = copy.deepcopy(base)
    geometry = copy.deepcopy(case["evidence"][0])
    geometry.update({
        "evidence_id": "ev-geometry-001",
        "role": "location_geometry",
        "temporal_class": "structural",
        "captured_at": "2025-08-29T00:00:00Z",
        "content_hash": "6" * 64,
    })
    geometry["rights"]["permitted_uses"] = ["retrieval", "validation", "derivative_generation"]
    appearance = copy.deepcopy(case["evidence"][0])
    appearance.update({
        "evidence_id": "ev-appearance-001",
        "role": "location_appearance",
        "content_hash": "7" * 64,
    })
    appearance["rights"]["permitted_uses"] = ["retrieval", "validation", "derivative_generation", "display"]
    metadata = copy.deepcopy(case["evidence"][1])
    case["evidence"] = [geometry, appearance, metadata]
    ids = [e["evidence_id"] for e in case["evidence"]]
    case["location_passport"]["evidence_node_ids"] = ids
    case["rights_manifest"]["evidence_decisions"] = {eid: "allowed" for eid in ids}
    plan = compiler.compile_render_plan(case)
    assert plan["render_mode"] == "constrained_generation", plan
    assert plan["evidence_ids"] == ["ev-appearance-001", "ev-geometry-001"], plan

    case = copy.deepcopy(base)
    case["evidence"][0]["role"] = "location_appearance"
    case["evidence"][0]["rights"]["permitted_uses"] = ["retrieval", "validation", "display"]
    try:
        compiler.compile_render_plan(case)
    except ValueError as exc:
        assert "No admissible render route" in str(exc), exc
    else:
        raise AssertionError("unsupported route: expected ValueError")

    case = copy.deepcopy(base)
    case["render_plan"] = compiler.compile_render_plan(case)
    case["grounding_receipt"] = {
        "receipt_version": "0.2",
        "contract_hash": mod.canonical_hash(case["scene_contract"]),
        "render_plan_hash": mod.canonical_hash(case["render_plan"]),
        "render_mode": case["render_plan"]["render_mode"],
        "output_hash": "8" * 64,
        "evidence_hashes": sorted(e["content_hash"] for e in case["evidence"]),
        "gate_results": {g: "PASS" for g in case["scene_contract"]["required_gates"]},
        "transformations": [],
        "software": [],
        "verdict": "GROUNDED",
    }
    expect_pass("coherent render-bound receipt", case)

    case["grounding_receipt"]["render_plan_hash"] = "9" * 64
    expect_reject("receipt render plan hash mismatch", case, "render_plan_hash mismatch")

    case = copy.deepcopy(base)
    case["render_plan"] = compiler.compile_render_plan(case)
    case["grounding_receipt"] = {
        "receipt_version": "0.2",
        "contract_hash": mod.canonical_hash(case["scene_contract"]),
        "render_plan_hash": mod.canonical_hash(case["render_plan"]),
        "render_mode": "constrained_generation",
        "output_hash": "8" * 64,
        "evidence_hashes": sorted(e["content_hash"] for e in case["evidence"]),
        "gate_results": {g: "PASS" for g in case["scene_contract"]["required_gates"]},
        "transformations": [],
        "software": [],
        "verdict": "GROUNDED",
    }
    expect_reject("receipt render mode mismatch", case, "G_RENDER_POLICY")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        asset = tmp_path / "reference.jpg"
        asset.write_bytes(b"geocanon-fixture")
        node_path = tmp_path / "node.json"
        ingest = subprocess.run(
            [
                sys.executable, str(ROOT / "scripts/geocanon_ingest.py"), str(asset),
                "--evidence-id", "ev-local-001",
                "--source-type", "user_owned",
                "--rights-status", "allowed",
                "--use", "derivative_generation",
                "--use", "display",
                "--role", "location_plate",
                "--authority", "location_truth",
                "--temporal-class", "current_appearance",
                "--zone", "exterior_entrance",
                "--captured-at", "2026-08-29T00:00:00Z",
                "--out", str(node_path),
            ],
            text=True, capture_output=True, check=False,
        )
        assert ingest.returncode == 0, ingest.stderr
        node = json.loads(node_path.read_text())
        assert node["role"] == "location_plate", node
        assert node["authority"] == "location_truth", node
        assert node["zone"] == "exterior_entrance", node

        bad_node_path = tmp_path / "bad-node.json"
        bad_ingest = subprocess.run(
            [
                sys.executable, str(ROOT / "scripts/geocanon_ingest.py"), str(asset),
                "--evidence-id", "ev-generated-001",
                "--source-type", "generated",
                "--rights-status", "allowed",
                "--use", "display",
                "--role", "generated_continuity",
                "--authority", "location_truth",
                "--temporal-class", "current_appearance",
                "--out", str(bad_node_path),
            ],
            text=True, capture_output=True, check=False,
        )
        assert bad_ingest.returncode != 0, bad_ingest.stdout
        assert "authority none" in (bad_ingest.stderr + bad_ingest.stdout), bad_ingest

        receipt_bundle = copy.deepcopy(base)
        receipt_bundle["render_plan"] = compiler.compile_render_plan(receipt_bundle)
        bundle_path = tmp_path / "bundle.json"
        bundle_path.write_text(json.dumps(receipt_bundle))
        plan_path = tmp_path / "plan.json"
        plan_path.write_text(json.dumps(receipt_bundle["render_plan"]))
        output_path = tmp_path / "output.png"
        output_path.write_bytes(b"rendered-output")
        gates_path = tmp_path / "gates.json"
        gates_path.write_text(json.dumps({g: "PASS" for g in base["scene_contract"]["required_gates"]}))
        receipt_path = tmp_path / "receipt.json"
        minted = subprocess.run(
            [
                sys.executable, str(ROOT / "scripts/geocanon_receipt.py"),
                str(bundle_path), str(output_path),
                "--render-plan", str(plan_path),
                "--gates", str(gates_path),
                "--receipt-out", str(receipt_path),
            ],
            text=True, capture_output=True, check=False,
        )
        assert minted.returncode == 0, minted.stderr
        receipt = json.loads(receipt_path.read_text())
        assert receipt["render_plan_hash"] == mod.canonical_hash(receipt_bundle["render_plan"]), receipt
        assert receipt["render_mode"] == "immutable_plate", receipt

    print("GEOCANON REGRESSION PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
