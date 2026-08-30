#!/usr/bin/env python3
"""Create a deterministic GeoCanon GroundingReceipt after external gates pass.

This tool does not decide whether visual/spatial gates are true; callers must
supply gate results from their evaluators. It refuses to mint GROUNDED unless
all SceneContract-required gates are PASS and the evidence bundle already
passes geocanon_validate.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts/geocanon_validate.py"
spec = importlib.util.spec_from_file_location("geocanon_validate", VALIDATOR)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("bundle", type=Path)
    p.add_argument("output_asset", type=Path)
    p.add_argument("--gates", type=Path, required=True, help="JSON object mapping gate names to PASS/FAIL/NOT_APPLICABLE")
    p.add_argument("--software", type=Path, help="Optional JSON array of tool/model/version/hash objects")
    p.add_argument("--transformations", type=Path, help="Optional JSON array describing deterministic transformations")
    p.add_argument("--receipt-out", type=Path, required=True)
    args = p.parse_args()

    bundle = json.loads(args.bundle.read_text())
    ok, errors = mod.validate(bundle)
    if not ok:
        raise SystemExit("Bundle rejected before receipt minting:\n- " + "\n- ".join(errors))

    gate_results = json.loads(args.gates.read_text())
    required = set(bundle["scene_contract"]["required_gates"])
    missing = required - set(gate_results)
    if missing:
        raise SystemExit(f"Missing required gate result(s): {sorted(missing)}")

    failed = sorted(g for g in required if gate_results.get(g) != "PASS")
    verdict = "GROUNDED" if not failed else "REJECTED"

    output_hash = mod.hashlib.sha256(args.output_asset.read_bytes()).hexdigest()
    receipt = {
        "receipt_version": "0.1",
        "contract_hash": mod.canonical_hash(bundle["scene_contract"]),
        "output_hash": output_hash,
        "evidence_hashes": sorted(e["content_hash"] for e in bundle["evidence"]),
        "gate_results": {k: gate_results[k] for k in sorted(gate_results)},
        "transformations": json.loads(args.transformations.read_text()) if args.transformations else [],
        "software": json.loads(args.software.read_text()) if args.software else [],
        "verdict": verdict,
    }

    args.receipt_out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"GEOCANON RECEIPT {verdict}: {args.receipt_out}")
    return 0 if verdict == "GROUNDED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
