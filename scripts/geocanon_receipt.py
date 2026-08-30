#!/usr/bin/env python3
"""Create a deterministic GeoCanon GroundingReceipt after external gates pass.

The runtime adapter is advisory. When a runtime request/result pair is supplied,
this tool binds the validated runtime result into the receipt but does not
promote advisory observations into authoritative gate decisions. External gate
owners must still supply the final gate results.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


validator = load_module("geocanon_validate", ROOT / "scripts/geocanon_validate.py")
runtime = load_module("geocanon_runtime", ROOT / "scripts/geocanon_runtime.py")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("bundle", type=Path)
    p.add_argument("output_asset", type=Path)
    p.add_argument("--gates", type=Path, required=True, help="JSON object mapping gate names to PASS/FAIL/NOT_APPLICABLE")
    p.add_argument("--software", type=Path, help="Optional JSON array of tool/model/version/hash objects")
    p.add_argument("--transformations", type=Path, help="Optional JSON array describing deterministic transformations")
    p.add_argument("--runtime-request", type=Path, help="RuntimeAdapterRequest used to produce the output")
    p.add_argument("--runtime-result", type=Path, help="Validated advisory RuntimeAdapterResult")
    p.add_argument("--receipt-out", type=Path, required=True)
    args = p.parse_args()

    if (args.runtime_request is None) != (args.runtime_result is None):
        raise SystemExit("--runtime-request and --runtime-result must be supplied together")
    if not args.output_asset.is_file():
        raise SystemExit(f"Output asset not found: {args.output_asset}")

    bundle = read_json(args.bundle)
    ok, errors = validator.validate(bundle)
    if not ok:
        raise SystemExit("Bundle rejected before receipt minting:\n- " + "\n- ".join(errors))

    gate_results = read_json(args.gates)
    if not isinstance(gate_results, dict):
        raise SystemExit("--gates must contain a JSON object")
    required = set(bundle["scene_contract"]["required_gates"])
    missing = required - set(gate_results)
    unknown = set(gate_results) - validator.HARD_GATES
    if missing:
        raise SystemExit(f"Missing required gate result(s): {sorted(missing)}")
    if unknown:
        raise SystemExit(f"Unknown gate result(s): {sorted(unknown)}")

    runtime_result = None
    runtime_request = None
    if args.runtime_request is not None and args.runtime_result is not None:
        runtime_request = read_json(args.runtime_request)
        runtime_result = read_json(args.runtime_result)
        result_ok, result_errors = runtime.validate_result(
            bundle,
            runtime_request,
            runtime_result,
            args.output_asset,
            args.runtime_request.parent,
        )
        if not result_ok:
            raise SystemExit("Runtime result rejected before receipt minting:\n- " + "\n- ".join(result_errors))
        observations = (runtime_result.get("evaluation_submission") or {}).get("observations") or {}
        contradictions = sorted(
            gate
            for gate, observation in observations.items()
            if isinstance(observation, dict)
            and observation.get("status") == "FAIL"
            and gate_results.get(gate) == "PASS"
        )
        if contradictions:
            raise SystemExit(
                "Authoritative gate results contradict runtime FAIL observation(s): "
                + ", ".join(contradictions)
            )

    failed = sorted(g for g in required if gate_results.get(g) != "PASS")
    verdict = "GROUNDED" if not failed else "REJECTED"

    transformations = read_json(args.transformations) if args.transformations else []
    software = read_json(args.software) if args.software else []
    if not isinstance(transformations, list):
        raise SystemExit("--transformations must contain a JSON array")
    if not isinstance(software, list):
        raise SystemExit("--software must contain a JSON array")

    output_hash = validator.hashlib.sha256(args.output_asset.read_bytes()).hexdigest()
    receipt = {
        "receipt_version": "0.2",
        "contract_hash": validator.canonical_hash(bundle["scene_contract"]),
        "output_hash": output_hash,
        "evidence_hashes": sorted(e["content_hash"] for e in bundle["evidence"]),
        "gate_results": {k: gate_results[k] for k in sorted(gate_results)},
        "transformations": transformations,
        "software": software,
        "verdict": verdict,
    }
    if runtime_result is not None:
        receipt.update(
            {
                "runtime_job_id": runtime_result["job_id"],
                "runtime_result_hash": runtime_result["result_hash"],
                "render_mode": runtime_result["render_mode"],
            }
        )

    args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"GEOCANON RECEIPT {verdict}: {args.receipt_out}")
    return 0 if verdict == "GROUNDED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
