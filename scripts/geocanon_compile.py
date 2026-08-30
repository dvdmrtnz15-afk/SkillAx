#!/usr/bin/env python3
"""Compile a deterministic, least-generative GeoCanon RenderPlan."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts/geocanon_validate.py"
_spec = importlib.util.spec_from_file_location("geocanon_validate", VALIDATOR)
validator = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(validator)



def compile_render_plan(bundle: dict[str, Any]) -> dict[str, Any]:
    """Validate a bundle and choose the least-generative admissible route.

    Raises:
        ValueError: when the bundle is invalid or no admissible route exists.
    """
    ok, errors = validator.validate(bundle)
    if not ok:
        raise ValueError("Bundle rejected before render routing:\n- " + "\n- ".join(errors))

    contract = bundle["scene_contract"]
    zone = contract["zone"]
    selected_mode, selected_ids = validator.select_render_route(bundle)

    return {
        "plan_version": "0.2",
        "contract_hash": validator.canonical_hash(contract),
        "location_id": contract["location_id"],
        "zone": zone,
        "render_mode": selected_mode,
        "evidence_ids": selected_ids,
        "immutable_anchors": list(contract.get("required_anchors") or []),
        "mutable_regions": list(contract.get("mutable_regions") or []),
        "target_snapshot": contract["target_snapshot"],
        "format": contract["format"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    plan = compile_render_plan(bundle)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"GEOCANON COMPILE {plan['render_mode']}: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
