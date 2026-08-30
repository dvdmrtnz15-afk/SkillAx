#!/usr/bin/env python3
"""Deterministic compositing and independent result validation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from geocanon_runtime_contract import inspect_request
from geocanon_runtime_core import (
    ALLOWED_STATUSES,
    EXPECTED_STAGES,
    OBSERVATION_GATES,
    Raster,
    RuntimeContractError,
    canonical_hash,
    hash_bytes,
    immutable_pixel_hash,
    netpbm_bytes,
    read_netpbm,
)


def _clamp8(value: float) -> int:
    return max(0, min(255, int(round(value))))


def _relight(subject: dict[str, Any]) -> Raster:
    source: Raster = subject["image"]
    gain, bias = subject["gain"], subject["bias"]
    pixels = [_clamp8(value * gain[i % 3] + bias[i % 3]) for i, value in enumerate(source.pixels)]
    return Raster(source.width, source.height, 3, tuple(pixels))


def _shadow_alpha(plate: Raster, subject: dict[str, Any]) -> Raster:
    source: Raster = subject["mask"]
    shadow = subject["shadow"]
    radius, opacity = shadow["blur_radius"], shadow["opacity"]
    values = [0.0] * (plate.width * plate.height)
    if opacity <= 0:
        return Raster(plate.width, plate.height, 1, tuple(0 for _ in values))
    kernel_area = (radius * 2 + 1) ** 2
    for sy in range(source.height):
        for sx in range(source.width):
            alpha = source.sample(sx, sy) / 255.0
            if alpha <= 0:
                continue
            cx = subject["x"] + sx + shadow["offset_x"]
            cy = subject["y"] + sy + shadow["offset_y"]
            contribution = alpha * opacity / kernel_area
            for py in range(cy - radius, cy + radius + 1):
                for px in range(cx - radius, cx + radius + 1):
                    index = py * plate.width + px
                    values[index] = min(1.0, values[index] + contribution)
    return Raster(plate.width, plate.height, 1, tuple(_clamp8(value * 255.0) for value in values))


def _blend(background: tuple[int, int, int], foreground: tuple[int, int, int], alpha: float) -> tuple[int, int, int]:
    return tuple(_clamp8(background[c] * (1 - alpha) + foreground[c] * alpha) for c in range(3))  # type: ignore[return-value]


def _apply_shadow(output: list[int], shadow: Raster, mutable_mask: Raster) -> None:
    for y in range(shadow.height):
        for x in range(shadow.width):
            alpha = shadow.sample(x, y) / 255.0
            if alpha <= 0 or mutable_mask.sample(x, y) <= 0:
                continue
            i = (y * shadow.width + x) * 3
            output[i : i + 3] = _blend((output[i], output[i + 1], output[i + 2]), (0, 0, 0), alpha)


def _apply_subject(output: list[int], relit: Raster, subject: dict[str, Any], mutable_mask: Raster) -> None:
    mask: Raster = subject["mask"]
    for sy in range(relit.height):
        for sx in range(relit.width):
            alpha = mask.sample(sx, sy) / 255.0
            if alpha <= 0:
                continue
            px, py = subject["x"] + sx, subject["y"] + sy
            if mutable_mask.sample(px, py) <= 0:
                raise RuntimeContractError(f"{subject['subject_id']} attempted immutable pixel mutation")
            i = (py * mutable_mask.width + px) * 3
            output[i : i + 3] = _blend(
                (output[i], output[i + 1], output[i + 2]), relit.rgb(sx, sy), alpha
            )


def _apply_occlusion(output: list[int], plate: Raster, subject: dict[str, Any]) -> None:
    mask: Raster | None = subject["occlusion"]
    if mask is None:
        return
    for sy in range(mask.height):
        for sx in range(mask.width):
            alpha = mask.sample(sx, sy) / 255.0
            if alpha <= 0:
                continue
            px, py = subject["x"] + sx, subject["y"] + sy
            i = (py * plate.width + px) * 3
            output[i : i + 3] = _blend(
                (output[i], output[i + 1], output[i + 2]), plate.rgb(px, py), alpha
            )


def _artifact_hash(kind: str, payload: object) -> str:
    return canonical_hash({"kind": kind, "payload": payload})


def _stage_artifacts(request: dict, context: dict[str, Any], relit: dict[str, Raster], shadows: dict[str, Raster], output_hash: str, integrity: dict) -> list[dict[str, str]]:
    subjects = context["subjects"]
    return [
        {
            "artifact_id": "stage-verify-inputs",
            "kind": "verification_manifest",
            "content_hash": _artifact_hash("verification_manifest", {
                "contract_hash": context["contract_hash"],
                "plate_hash": request["plate"]["content_hash"],
                "mutable_mask_hash": request["mutable_region"]["mask"]["content_hash"],
                "subject_input_hashes": [{
                    "subject_id": item["subject_id"],
                    "image": item["raw"]["image"]["content_hash"],
                    "segmentation": item["raw"]["segmentation_mask"]["content_hash"],
                    "occlusion": (item["raw"].get("occlusion_mask") or {}).get("content_hash"),
                } for item in subjects],
            }),
        },
        {
            "artifact_id": "stage-segment-subjects",
            "kind": "segmentation_manifest",
            "content_hash": _artifact_hash("segmentation_manifest", [{
                "subject_id": item["subject_id"],
                "mask_hash": item["raw"]["segmentation_mask"]["content_hash"],
                "placement": item["raw"]["placement"],
            } for item in subjects]),
        },
        {
            "artifact_id": "stage-photometric-relight",
            "kind": "relit_subjects",
            "content_hash": _artifact_hash("relit_subjects", [{
                "subject_id": item["subject_id"],
                "raster_hash": hash_bytes(netpbm_bytes(relit[item["subject_id"]])),
            } for item in subjects]),
        },
        {
            "artifact_id": "stage-contact-shadow",
            "kind": "contact_shadows",
            "content_hash": _artifact_hash("contact_shadows", [{
                "subject_id": item["subject_id"],
                "mask_hash": hash_bytes(netpbm_bytes(shadows[item["subject_id"]])),
            } for item in subjects]),
        },
        {
            "artifact_id": "stage-occlusion-repair",
            "kind": "occlusion_manifest",
            "content_hash": _artifact_hash("occlusion_manifest", [{
                "subject_id": item["subject_id"],
                "occlusion_hash": (item["raw"].get("occlusion_mask") or {}).get("content_hash"),
            } for item in subjects]),
        },
        {"artifact_id": "stage-composite", "kind": "final_composite", "content_hash": output_hash},
        {
            "artifact_id": "stage-evaluate-integrity",
            "kind": "integrity_evaluation",
            "content_hash": _artifact_hash("integrity_evaluation", integrity),
        },
    ]


def _advisory_observations() -> dict[str, dict[str, str]]:
    return {
        "G_LOCATION_IDENTITY": {"status": "UNKNOWN", "basis": "Reference raster adapter cannot establish real-world place identity."},
        "G_RIGHTS": {"status": "PASS", "basis": "Plate EvidenceNode and RightsManifest explicitly permit derivative generation."},
        "G_SPATIAL": {"status": "PASS", "basis": "All subject and shadow mutations are confined to the declared mutable mask; immutable pixels match the plate."},
        "G_VIEW_CONE": {"status": "UNKNOWN", "basis": "Reference raster adapter does not localize or solve camera pose."},
        "G_TEMPORAL": {"status": "UNKNOWN", "basis": "Temporal compatibility remains an upstream proof-kernel decision."},
        "G_SUBJECT_CANON": {"status": "UNKNOWN", "basis": "Persona identity and relationship canon require the external character-world evaluator."},
        "G_PROVENANCE": {"status": "PASS", "basis": "Inputs, output, stages, immutable region, and result are content-addressed."},
    }


def result_hash(result: dict) -> str:
    body = dict(result)
    body.pop("result_hash", None)
    return canonical_hash(body)


def execute_reference(bundle: dict, request: dict, base_dir: Path) -> tuple[bytes, dict]:
    context = inspect_request(bundle, request, base_dir)
    plate: Raster = context["plate"]
    mutable_mask: Raster = context["mutable_mask"]
    output = list(plate.pixels)
    relit: dict[str, Raster] = {}
    shadows: dict[str, Raster] = {}
    for subject in context["subjects"]:
        subject_id = subject["subject_id"]
        relit[subject_id] = _relight(subject)
        shadows[subject_id] = _shadow_alpha(plate, subject)
        _apply_shadow(output, shadows[subject_id], mutable_mask)
        _apply_subject(output, relit[subject_id], subject, mutable_mask)
        _apply_occlusion(output, plate, subject)

    output_raster = Raster(plate.width, plate.height, 3, tuple(output))
    output_bytes = netpbm_bytes(output_raster)
    output_hash = hash_bytes(output_bytes)
    before = immutable_pixel_hash(plate, mutable_mask)
    after = immutable_pixel_hash(output_raster, mutable_mask)
    integrity = {
        "dimensions_match_plate": True,
        "mutable_fraction": context["mutable_fraction"],
        "immutable_pixel_hash_before": before,
        "immutable_pixel_hash_after": after,
        "immutable_pixels_unchanged": before == after,
        "subject_count": len(context["subjects"]),
    }
    if before != after:
        raise RuntimeContractError("Reference render changed immutable pixels")
    result = {
        "runtime_version": "0.1",
        "job_id": context["job_id"],
        "contract_hash": context["contract_hash"],
        "render_mode": "immutable_plate",
        "plate_hash": request["plate"]["content_hash"],
        "output_hash": output_hash,
        "stage_artifacts": _stage_artifacts(request, context, relit, shadows, output_hash, integrity),
        "integrity": integrity,
        "evaluation_submission": {"authority": "advisory_only", "observations": _advisory_observations()},
    }
    result["result_hash"] = result_hash(result)
    return output_bytes, result


def _validate_observations(result: dict, errors: list[str]) -> None:
    if "verdict" in result or "gate_results" in result or "canon_updates" in result:
        errors.append("Runtime result attempts authority escalation")
    submission = result.get("evaluation_submission")
    if not isinstance(submission, dict):
        errors.append("Runtime result missing evaluation_submission")
        return
    if submission.get("authority") != "advisory_only":
        errors.append("Runtime evaluation authority must be advisory_only")
    observations = submission.get("observations")
    if not isinstance(observations, dict):
        errors.append("Runtime observations must be an object")
        return
    unknown = set(observations) - OBSERVATION_GATES
    if unknown:
        errors.append(f"Runtime observations contain unknown gates: {sorted(unknown)}")
    for gate, observation in observations.items():
        if not isinstance(observation, dict):
            errors.append(f"Runtime observation {gate} must be an object")
        elif observation.get("status") not in ALLOWED_STATUSES:
            errors.append(f"Runtime observation {gate} has invalid status")
        elif not isinstance(observation.get("basis"), str) or not observation.get("basis"):
            errors.append(f"Runtime observation {gate} requires a basis")


def validate_result(bundle: dict, request: dict, result: dict, output_path: Path, base_dir: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []
    try:
        expected_output, expected = execute_reference(bundle, request, base_dir)
    except (RuntimeContractError, ValueError, OSError, json.JSONDecodeError) as exc:
        return False, [f"Runtime request invalid: {exc}"]
    if not isinstance(result, dict):
        return False, ["Runtime result must be an object"]
    if not output_path.is_file():
        return False, [f"Runtime output not found: {output_path}"]
    try:
        actual_bytes = output_path.read_bytes()
        actual = read_netpbm(output_path)
    except (OSError, ValueError) as exc:
        return False, [f"Runtime output invalid: {exc}"]

    _validate_observations(result, errors)
    for field in ("runtime_version", "job_id", "contract_hash", "render_mode", "plate_hash"):
        if result.get(field) != expected.get(field):
            errors.append(f"Runtime result {field} mismatch")
    actual_hash = hash_bytes(actual_bytes)
    if result.get("output_hash") != actual_hash:
        errors.append("Runtime result output_hash does not match output asset")
    if actual_hash != expected["output_hash"] or actual_bytes != expected_output:
        errors.append("Runtime output differs from deterministic reference composite")

    try:
        context = inspect_request(bundle, request, base_dir)
        plate, mask = context["plate"], context["mutable_mask"]
        if (actual.width, actual.height, actual.channels) != (plate.width, plate.height, plate.channels):
            errors.append("Runtime output dimensions/channels differ from plate")
        else:
            before, after = immutable_pixel_hash(plate, mask), immutable_pixel_hash(actual, mask)
            recomputed = {
                "dimensions_match_plate": True,
                "mutable_fraction": context["mutable_fraction"],
                "immutable_pixel_hash_before": before,
                "immutable_pixel_hash_after": after,
                "immutable_pixels_unchanged": before == after,
                "subject_count": len(context["subjects"]),
            }
            if result.get("integrity") != recomputed:
                errors.append("Runtime integrity report does not match recomputed values")
            if before != after:
                errors.append("Runtime output changed immutable plate pixels")
    except (RuntimeContractError, ValueError, OSError) as exc:
        errors.append(f"Unable to recompute immutable integrity: {exc}")

    stages = result.get("stage_artifacts")
    if stages != expected.get("stage_artifacts"):
        errors.append("Runtime stage artifact ledger mismatch")
    if isinstance(stages, list):
        ids = [item.get("artifact_id") for item in stages if isinstance(item, dict)]
        if len(ids) != len(set(ids)):
            errors.append("Runtime stage artifact IDs must be unique")
        required = {f"stage-{stage.replace('_', '-')}" for stage in EXPECTED_STAGES}
        if set(ids) != required:
            errors.append("Runtime stage artifact coverage is incomplete")
    if result.get("result_hash") != result_hash(result):
        errors.append("Runtime result_hash mismatch")
    return not errors, errors
