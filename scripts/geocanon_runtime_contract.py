#!/usr/bin/env python3
"""Fail-closed request admission for the GeoCanon reference runtime."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from geocanon_runtime_core import (
    EXPECTED_STAGES,
    Raster,
    RuntimeContractError,
    artifact_raster,
    bounded_float,
    integer,
    mask_fraction,
    number_triplet,
)

ROOT = Path(__file__).resolve().parents[1]


def _load_validator() -> Any:
    path = ROOT / "scripts/geocanon_validate.py"
    spec = importlib.util.spec_from_file_location("geocanon_validate_runtime", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load GeoCanon validator from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


validator = _load_validator()


def _evidence_index(bundle: dict) -> dict[str, dict]:
    return {
        item["evidence_id"]: item
        for item in bundle.get("evidence") or []
        if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
    }


def _collect_subject(subject: dict, base_dir: Path, plate: Raster, mutable_mask: Raster) -> dict[str, Any]:
    subject_id = subject.get("subject_id")
    if not isinstance(subject_id, str) or not subject_id:
        raise RuntimeContractError("Each subject requires a non-empty subject_id")
    _, image = artifact_raster(subject.get("image"), base_dir, channels=3, label=f"{subject_id}.image")
    _, mask = artifact_raster(
        subject.get("segmentation_mask"), base_dir, channels=1, label=f"{subject_id}.segmentation_mask"
    )
    if (image.width, image.height) != (mask.width, mask.height):
        raise RuntimeContractError(f"{subject_id} image/mask dimensions differ")

    occlusion = None
    if subject.get("occlusion_mask") is not None:
        _, occlusion = artifact_raster(
            subject.get("occlusion_mask"), base_dir, channels=1, label=f"{subject_id}.occlusion_mask"
        )
        if (image.width, image.height) != (occlusion.width, occlusion.height):
            raise RuntimeContractError(f"{subject_id} image/occlusion dimensions differ")

    placement = subject.get("placement")
    if not isinstance(placement, dict):
        raise RuntimeContractError(f"{subject_id}.placement must be an object")
    x0 = integer(placement.get("x"), f"{subject_id}.placement.x", 0)
    y0 = integer(placement.get("y"), f"{subject_id}.placement.y", 0)
    if x0 + image.width > plate.width or y0 + image.height > plate.height:
        raise RuntimeContractError(f"{subject_id} placement exceeds plate bounds")

    relight = subject.get("relight")
    if not isinstance(relight, dict):
        raise RuntimeContractError(f"{subject_id}.relight must be an object")
    gain = number_triplet(relight.get("gain"), f"{subject_id}.relight.gain")
    bias = number_triplet(relight.get("bias"), f"{subject_id}.relight.bias")
    if any(value < 0 or value > 4 for value in gain):
        raise RuntimeContractError(f"{subject_id}.relight.gain outside 0..4")
    if any(value < -255 or value > 255 for value in bias):
        raise RuntimeContractError(f"{subject_id}.relight.bias outside -255..255")

    shadow = subject.get("contact_shadow")
    if not isinstance(shadow, dict):
        raise RuntimeContractError(f"{subject_id}.contact_shadow must be an object")
    offset_x = integer(shadow.get("offset_x"), f"{subject_id}.contact_shadow.offset_x")
    offset_y = integer(shadow.get("offset_y"), f"{subject_id}.contact_shadow.offset_y")
    radius = integer(shadow.get("blur_radius"), f"{subject_id}.contact_shadow.blur_radius", 0)
    if radius > 16:
        raise RuntimeContractError(f"{subject_id}.contact_shadow.blur_radius exceeds 16")
    opacity = bounded_float(shadow.get("opacity"), f"{subject_id}.contact_shadow.opacity", 0, 1)

    active = [(x, y) for y in range(mask.height) for x in range(mask.width) if mask.sample(x, y) > 0]
    if not active:
        raise RuntimeContractError(f"{subject_id} segmentation mask is empty")
    for x, y in active:
        if mutable_mask.sample(x0 + x, y0 + y) <= 0:
            raise RuntimeContractError(f"{subject_id} subject footprint escapes mutable region")

    if opacity > 0:
        for x, y in active:
            center_x, center_y = x0 + x + offset_x, y0 + y + offset_y
            for sy in range(center_y - radius, center_y + radius + 1):
                for sx in range(center_x - radius, center_x + radius + 1):
                    if sx < 0 or sy < 0 or sx >= plate.width or sy >= plate.height:
                        raise RuntimeContractError(f"{subject_id} shadow footprint exceeds plate bounds")
                    if mutable_mask.sample(sx, sy) <= 0:
                        raise RuntimeContractError(f"{subject_id} shadow footprint escapes mutable region")

    return {
        "subject_id": subject_id,
        "image": image,
        "mask": mask,
        "occlusion": occlusion,
        "x": x0,
        "y": y0,
        "gain": gain,
        "bias": bias,
        "shadow": {"offset_x": offset_x, "offset_y": offset_y, "blur_radius": radius, "opacity": opacity},
        "raw": subject,
    }


def inspect_request(bundle: dict, request: dict, base_dir: Path) -> dict[str, Any]:
    bundle_ok, bundle_errors = validator.validate(bundle)
    if not bundle_ok:
        raise RuntimeContractError("Bundle failed GeoCanon admission: " + "; ".join(bundle_errors))
    if not isinstance(request, dict):
        raise RuntimeContractError("Runtime request must be an object")
    if request.get("runtime_version") != "0.1":
        raise RuntimeContractError("runtime_version must be 0.1")
    if request.get("render_mode") != "immutable_plate":
        raise RuntimeContractError("Reference runtime supports immutable_plate only")
    if request.get("adapter") != {"name": "stdlib-netpbm-reference", "version": "0.1"}:
        raise RuntimeContractError("Unsupported adapter identity")
    if tuple(request.get("stages") or []) != EXPECTED_STAGES:
        raise RuntimeContractError("Runtime stages must match the governed order exactly")

    contract = bundle.get("scene_contract") or {}
    contract_hash = validator.canonical_hash(contract)
    if request.get("contract_hash") != contract_hash:
        raise RuntimeContractError("Runtime request contract_hash mismatch")
    job_id = request.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise RuntimeContractError("Runtime request requires a non-empty job_id")

    plate_spec = request.get("plate")
    _, plate = artifact_raster(plate_spec, base_dir, channels=3, label="plate")
    evidence_id = plate_spec.get("evidence_id") if isinstance(plate_spec, dict) else None
    evidence = _evidence_index(bundle).get(evidence_id)
    if evidence is None:
        raise RuntimeContractError("Plate evidence_id is absent from the admitted bundle")
    if evidence.get("content_hash") != plate_spec.get("content_hash"):
        raise RuntimeContractError("Plate hash does not match admitted EvidenceNode")
    rights = evidence.get("rights") or {}
    decisions = (bundle.get("rights_manifest") or {}).get("evidence_decisions") or {}
    if rights.get("status") != "allowed" or decisions.get(evidence_id) != "allowed":
        raise RuntimeContractError("Plate evidence is not explicitly rights-admitted")
    if "derivative_generation" not in set(rights.get("permitted_uses") or []):
        raise RuntimeContractError("Plate evidence lacks derivative_generation permission")

    mutable = request.get("mutable_region")
    if not isinstance(mutable, dict):
        raise RuntimeContractError("mutable_region must be an object")
    if mutable.get("region_id") not in set(contract.get("mutable_regions") or []):
        raise RuntimeContractError("Runtime mutable region is not declared by SceneContract")
    _, mutable_mask = artifact_raster(mutable.get("mask"), base_dir, channels=1, label="mutable_region.mask")
    if (mutable_mask.width, mutable_mask.height) != (plate.width, plate.height):
        raise RuntimeContractError("Mutable mask dimensions must match plate")

    policy = request.get("policy")
    if not isinstance(policy, dict):
        raise RuntimeContractError("policy must be an object")
    if policy.get("preserve_immutable_pixels") is not True:
        raise RuntimeContractError("preserve_immutable_pixels must be true")
    max_fraction = bounded_float(policy.get("max_mutable_fraction"), "policy.max_mutable_fraction", 0, 1)
    if max_fraction <= 0 or max_fraction >= 1:
        raise RuntimeContractError("policy.max_mutable_fraction must be strictly between 0 and 1")
    fraction = mask_fraction(mutable_mask)
    if fraction <= 0:
        raise RuntimeContractError("Mutable mask is empty")
    if fraction >= 1:
        raise RuntimeContractError("Full-frame mutable masks are prohibited")
    if fraction > max_fraction + 1e-12:
        raise RuntimeContractError("Mutable mask exceeds max_mutable_fraction")

    raw_subjects = request.get("subjects")
    if not isinstance(raw_subjects, list) or not raw_subjects:
        raise RuntimeContractError("At least one subject is required")
    subjects: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_subject in raw_subjects:
        if not isinstance(raw_subject, dict):
            raise RuntimeContractError("Each subject must be an object")
        subject = _collect_subject(raw_subject, base_dir, plate, mutable_mask)
        if subject["subject_id"] in seen:
            raise RuntimeContractError(f"Duplicate subject_id: {subject['subject_id']}")
        seen.add(subject["subject_id"])
        subjects.append(subject)

    return {
        "plate": plate,
        "plate_spec": plate_spec,
        "mutable_mask": mutable_mask,
        "mutable_spec": mutable,
        "mutable_fraction": fraction,
        "subjects": subjects,
        "contract_hash": contract_hash,
        "job_id": job_id,
    }


def validate_request(bundle: dict, request: dict, base_dir: Path) -> tuple[bool, list[str]]:
    try:
        inspect_request(bundle, request, base_dir)
    except (RuntimeContractError, ValueError, OSError, json.JSONDecodeError) as exc:
        return False, [str(exc)]
    return True, []
