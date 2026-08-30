#!/usr/bin/env python3
"""Adversarial regressions for the GeoCanon immutable-plate runtime adapter."""
from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/geocanon/runtime"
RUNTIME_PATH = ROOT / "scripts/geocanon_runtime.py"
RECEIPT_PATH = ROOT / "scripts/geocanon_receipt.py"


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runtime = load_module("geocanon_runtime_test_target", RUNTIME_PATH)


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prepare() -> tuple[tempfile.TemporaryDirectory[str], Path, dict, dict]:
    temp = tempfile.TemporaryDirectory(prefix="geocanon-runtime-")
    target = Path(temp.name) / "runtime"
    shutil.copytree(FIXTURE, target)
    bundle = read_json(target / "reference.bundle.json")
    request = read_json(target / "reference.request.json")
    return temp, target, bundle, request


def expect_request_reject(
    name: str,
    mutate: Callable[[Path, dict, dict], None],
    contains: str,
) -> None:
    temp, target, bundle, request = prepare()
    try:
        mutate(target, bundle, request)
        ok, errors = runtime.validate_request(bundle, request, target)
        assert not ok, f"{name}: expected request rejection"
        joined = "\n".join(errors)
        assert contains.lower() in joined.lower(), f"{name}: expected {contains!r} in {joined!r}"
    finally:
        temp.cleanup()


def baseline_result(target: Path, bundle: dict, request: dict) -> tuple[Path, dict]:
    output_bytes, result = runtime.execute_reference(bundle, request, target)
    output = target / "output.ppm"
    output.write_bytes(output_bytes)
    ok, errors = runtime.validate_result(bundle, request, result, output, target)
    assert ok, f"baseline runtime result rejected: {errors}"
    return output, result


def all_pass_gates(bundle: dict) -> dict[str, str]:
    return {gate: "PASS" for gate in bundle["scene_contract"]["required_gates"]}


def run_receipt(
    target: Path,
    bundle: dict,
    request: dict,
    result: dict,
    output: Path,
    *,
    include_runtime: bool = True,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    bundle_path = target / "bundle-for-receipt.json"
    request_path = target / "request-for-receipt.json"
    result_path = target / "result-for-receipt.json"
    gates_path = target / "gates.json"
    receipt_path = target / "receipt.json"
    write_json(bundle_path, bundle)
    write_json(request_path, request)
    write_json(result_path, result)
    write_json(gates_path, all_pass_gates(bundle))
    command = [
        sys.executable,
        str(RECEIPT_PATH),
        str(bundle_path),
        str(output),
        "--gates",
        str(gates_path),
        "--receipt-out",
        str(receipt_path),
    ]
    if include_runtime:
        command.extend(["--runtime-request", str(request_path), "--runtime-result", str(result_path)])
    return subprocess.run(command, text=True, capture_output=True, check=False), receipt_path


def main() -> int:
    temp, target, bundle, request = prepare()
    try:
        ok, errors = runtime.validate_request(bundle, request, target)
        assert ok, f"reference request rejected: {errors}"
        _output, result = baseline_result(target, bundle, request)
        assert result["integrity"]["immutable_pixels_unchanged"] is True
        assert result["integrity"]["mutable_fraction"] < 0.5
        assert result["evaluation_submission"]["authority"] == "advisory_only"
        assert "verdict" not in result
    finally:
        temp.cleanup()

    expect_request_reject(
        "stage reorder",
        lambda _t, _b, r: r["stages"].reverse(),
        "governed order",
    )
    expect_request_reject(
        "render escalation",
        lambda _t, _b, r: r.__setitem__("render_mode", "constrained_generation"),
        "immutable_plate only",
    )
    expect_request_reject(
        "plate hash mismatch",
        lambda _t, _b, r: r["plate"].__setitem__("content_hash", "0" * 64),
        "content_hash mismatch",
    )

    def duplicate_subject(_target: Path, _bundle: dict, req: dict) -> None:
        req["subjects"].append(copy.deepcopy(req["subjects"][0]))

    expect_request_reject("duplicate subject", duplicate_subject, "duplicate subject_id")

    def escape_subject(_target: Path, _bundle: dict, req: dict) -> None:
        req["subjects"][0]["placement"] = {"x": 0, "y": 0}

    expect_request_reject("subject footprint escape", escape_subject, "subject footprint escapes")

    def escape_shadow(_target: Path, _bundle: dict, req: dict) -> None:
        req["subjects"][0]["contact_shadow"]["offset_x"] = -2

    expect_request_reject("shadow footprint escape", escape_shadow, "shadow footprint escapes")

    def full_frame_mask(target_dir: Path, _bundle: dict, req: dict) -> None:
        mask_path = target_dir / "assets/mutable-mask.pgm"
        mask = runtime.Raster(6, 6, 1, tuple([255] * 36))
        runtime.write_netpbm(mask_path, mask)
        req["mutable_region"]["mask"]["content_hash"] = runtime.hash_file(mask_path)

    expect_request_reject("full-frame mutable mask", full_frame_mask, "full-frame mutable masks")

    def path_traversal(_target: Path, _bundle: dict, req: dict) -> None:
        req["plate"]["path"] = "../plate.ppm"

    expect_request_reject("path traversal", path_traversal, "unsafe asset path")

    temp, target, bundle, request = prepare()
    try:
        output, result = baseline_result(target, bundle, request)

        case = copy.deepcopy(result)
        case["result_hash"] = "f" * 64
        ok, errors = runtime.validate_result(bundle, request, case, output, target)
        assert not ok and "result_hash mismatch" in "\n".join(errors)

        case = copy.deepcopy(result)
        case["verdict"] = "GROUNDED"
        case["result_hash"] = runtime._result_hash(case)
        ok, errors = runtime.validate_result(bundle, request, case, output, target)
        assert not ok and "authority escalation" in "\n".join(errors)

        case = copy.deepcopy(result)
        case["evaluation_submission"]["authority"] = "authoritative"
        case["result_hash"] = runtime._result_hash(case)
        ok, errors = runtime.validate_result(bundle, request, case, output, target)
        assert not ok and "advisory_only" in "\n".join(errors)

        case = copy.deepcopy(result)
        case["stage_artifacts"] = case["stage_artifacts"][:-1]
        case["result_hash"] = runtime._result_hash(case)
        ok, errors = runtime.validate_result(bundle, request, case, output, target)
        assert not ok and "stage artifact" in "\n".join(errors).lower()

        tampered = runtime.read_netpbm(output)
        pixels = list(tampered.pixels)
        pixels[0] = (pixels[0] + 1) % 256
        runtime.write_netpbm(output, runtime.Raster(tampered.width, tampered.height, 3, tuple(pixels)))
        case = copy.deepcopy(result)
        case["output_hash"] = runtime.hash_file(output)
        for artifact in case["stage_artifacts"]:
            if artifact["artifact_id"] == "stage-composite":
                artifact["content_hash"] = case["output_hash"]
        case["integrity"]["immutable_pixel_hash_after"] = case["integrity"]["immutable_pixel_hash_before"]
        case["integrity"]["immutable_pixels_unchanged"] = True
        case["result_hash"] = runtime._result_hash(case)
        ok, errors = runtime.validate_result(bundle, request, case, output, target)
        joined = "\n".join(errors).lower()
        assert not ok and ("immutable" in joined or "deterministic reference composite" in joined)
    finally:
        temp.cleanup()

    temp, target, bundle, request = prepare()
    try:
        output, result = baseline_result(target, bundle, request)
        completed, receipt_path = run_receipt(target, bundle, request, result, output)
        assert completed.returncode == 0, completed.stderr
        receipt = read_json(receipt_path)
        assert receipt["verdict"] == "GROUNDED"
        assert receipt["runtime_job_id"] == result["job_id"]
        assert receipt["runtime_result_hash"] == result["result_hash"]
        assert receipt["render_mode"] == "immutable_plate"

        legacy, legacy_path = run_receipt(target, bundle, request, result, output, include_runtime=False)
        assert legacy.returncode == 0, legacy.stderr
        legacy_receipt = read_json(legacy_path)
        assert "runtime_result_hash" not in legacy_receipt

        contradiction = copy.deepcopy(result)
        contradiction["evaluation_submission"]["observations"]["G_SPATIAL"] = {
            "status": "FAIL",
            "basis": "Advisory evaluator detected a spatial failure.",
        }
        contradiction["result_hash"] = runtime._result_hash(contradiction)
        ok, errors = runtime.validate_result(bundle, request, contradiction, output, target)
        assert ok, f"valid advisory FAIL envelope rejected: {errors}"
        completed, _ = run_receipt(target, bundle, request, contradiction, output)
        assert completed.returncode != 0
        assert "contradict" in completed.stderr.lower()
    finally:
        temp.cleanup()

    print("GEOCANON RUNTIME REGRESSION PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
