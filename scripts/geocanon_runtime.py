#!/usr/bin/env python3
"""CLI and public API for the GeoCanon immutable-plate reference runtime."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from geocanon_runtime_contract import inspect_request, validate_request  # noqa: E402
from geocanon_runtime_core import (  # noqa: E402
    ALLOWED_STATUSES,
    EXPECTED_STAGES,
    OBSERVATION_GATES,
    Raster,
    RuntimeContractError,
    canonical_hash,
    hash_bytes,
    hash_file,
    immutable_pixel_hash,
    netpbm_bytes,
    read_netpbm,
    write_netpbm,
)
from geocanon_runtime_render import (  # noqa: E402
    execute_reference,
    result_hash,
    validate_result,
)

_result_hash = result_hash


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeContractError(f"Expected JSON object in {path}")
    return value


def _print_errors(prefix: str, errors: Iterable[str]) -> None:
    print(prefix, file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate-request")
    validate_parser.add_argument("bundle", type=Path)
    validate_parser.add_argument("request", type=Path)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("bundle", type=Path)
    run_parser.add_argument("request", type=Path)
    run_parser.add_argument("--output", type=Path, required=True)
    run_parser.add_argument("--result-out", type=Path, required=True)

    result_parser = subparsers.add_parser("validate-result")
    result_parser.add_argument("bundle", type=Path)
    result_parser.add_argument("request", type=Path)
    result_parser.add_argument("result", type=Path)
    result_parser.add_argument("output", type=Path)

    args = parser.parse_args()
    try:
        bundle = _read_json(args.bundle)
        request = _read_json(args.request)
    except (OSError, json.JSONDecodeError, RuntimeContractError) as exc:
        _print_errors("GEOCANON RUNTIME REJECT", [str(exc)])
        return 1
    base_dir = args.request.parent

    if args.command == "validate-request":
        ok, errors = validate_request(bundle, request, base_dir)
        if not ok:
            _print_errors("GEOCANON RUNTIME REQUEST REJECT", errors)
            return 1
        print("GEOCANON RUNTIME REQUEST PASS")
        return 0

    if args.command == "run":
        try:
            output_bytes, result = execute_reference(bundle, request, base_dir)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(output_bytes)
            args.result_out.parent.mkdir(parents=True, exist_ok=True)
            args.result_out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except (RuntimeContractError, ValueError, OSError) as exc:
            _print_errors("GEOCANON RUNTIME REJECT", [str(exc)])
            return 1
        print(f"GEOCANON RUNTIME PASS: {args.output}")
        return 0

    try:
        result = _read_json(args.result)
    except (OSError, json.JSONDecodeError, RuntimeContractError) as exc:
        _print_errors("GEOCANON RUNTIME RESULT REJECT", [str(exc)])
        return 1
    ok, errors = validate_result(bundle, request, result, args.output, base_dir)
    if not ok:
        _print_errors("GEOCANON RUNTIME RESULT REJECT", errors)
        return 1
    print("GEOCANON RUNTIME RESULT PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
