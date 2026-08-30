#!/usr/bin/env python3
"""Mint a deterministic GeoCanon GroundingReceipt after external gates pass.

The tool does not decide visual truth. It validates the bundle and render plan,
requires every SceneContract hard gate to be PASS, and binds the receipt to the
contract, render plan, evidence, output bytes, transformations, and software.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts/geocanon_validate.py"
_spec = importlib.util.spec_from_file_location("geocanon_validate", VALIDATOR)
validator = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(validator)


def _load_json(path: Path, expected: type) -> object:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, expected):
        raise SystemExit(f"{path} must contain {expected.__name__}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("output_asset", type=Path)
    parser.add_argument("--render-plan", type=Path, required=True)
    parser.add_argument(
        "--gates",
        type=Path,
        required=True,
        help="JSON object mapping gate names to PASS/FAIL/NOT_APPLICABLE",
    )
    parser.add_argument("--software", type=Path, help="Optional JSON array of software/model records")
    parser.add_argument("--transformations", type=Path, help="Optional JSON array of transformations")
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args()

    if not args.output_asset.is_file():
        raise SystemExit(f"Output asset not found: {args.output_asset}")

    bundle = _load_json(args.bundle, dict)
    render_plan = _load_json(args.render_plan, dict)
    if bundle.get("render_plan") != render_plan:
        raise SystemExit("Bundle render_plan does not exactly match --render-plan")

    ok, errors = validator.validate(bundle, require_render_plan=True)
    if not ok:
        raise SystemExit("Bundle rejected before receipt minting:\n- " + "\n- ".join(errors))

    gate_results = _load_json(args.gates, dict)
    required = set(bundle["scene_contract"]["required_gates"])
    missing = sorted(required - set(gate_results))
    extra = sorted(set(gate_results) - validator.HARD_GATES)
    if missing:
        raise SystemExit(f"Missing required gate result(s): {missing}")
    if extra:
        raise SystemExit(f"Unknown gate result(s): {extra}")

    failed = sorted(gate for gate in required if gate_results.get(gate) != "PASS")
    verdict = "GROUNDED" if not failed else "REJECTED"

    transformations = _load_json(args.transformations, list) if args.transformations else []
    software = _load_json(args.software, list) if args.software else []
    output_hash = validator.hashlib.sha256(args.output_asset.read_bytes()).hexdigest()
    receipt = {
        "receipt_version": "0.2",
        "contract_hash": validator.canonical_hash(bundle["scene_contract"]),
        "render_plan_hash": validator.canonical_hash(render_plan),
        "render_mode": render_plan["render_mode"],
        "output_hash": output_hash,
        "evidence_hashes": sorted(item["content_hash"] for item in bundle["evidence"]),
        "gate_results": {key: gate_results[key] for key in sorted(gate_results)},
        "transformations": transformations,
        "software": software,
        "verdict": verdict,
    }

    args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"GEOCANON RECEIPT {verdict}: {args.receipt_out}")
    return 0 if verdict == "GROUNDED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
