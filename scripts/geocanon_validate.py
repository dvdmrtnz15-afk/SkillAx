#!/usr/bin/env python3
"""Fail-closed semantic validator for a GeoCanon/SceneProof bundle.

The module is intentionally standard-library only so admission checks can run
in minimal CI environments. JSON Schema validates shape; this file enforces
cross-object security, grounding, temporal, routing, and provenance semantics.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

HARD_GATES = {
    "G_LOCATION_IDENTITY",
    "G_RIGHTS",
    "G_SPATIAL",
    "G_VIEW_CONE",
    "G_TEMPORAL",
    "G_SUBJECT_CANON",
    "G_FORMAT",
    "G_RENDER_POLICY",
    "G_OBJECT_INTEGRITY",
    "G_PROVENANCE",
}
MANDATORY_GATES = {
    "G_LOCATION_IDENTITY",
    "G_RIGHTS",
    "G_SPATIAL",
    "G_TEMPORAL",
    "G_FORMAT",
    "G_RENDER_POLICY",
    "G_PROVENANCE",
}
PIXEL_USES = {"validation", "reconstruction", "derivative_generation"}
LOCATION_ROLES = {"location_plate", "location_geometry", "location_appearance", "metadata"}
LOCATION_SCENE_ROLES = {"location_plate", "location_geometry", "location_appearance"}
GENERATED_ALLOWED_USES = {"retrieval", "display"}
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


def canonical_hash(obj: object) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def parse_iso(value: Any, label: str, errors: list[str], gate: str) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{gate}: {label} must be an ISO-8601 timestamp")
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{gate}: {label} is not valid ISO-8601")
        return None
    if parsed.tzinfo is None:
        errors.append(f"{gate}: {label} must include a timezone")
        return None
    return parsed.astimezone(dt.timezone.utc)


def _is_google_map_source(uri: str) -> bool:
    value = uri.lower()
    return any(
        token in value
        for token in (
            "google.com/maps",
            "maps.google.",
            "streetview",
            "street_view",
        )
    )


def _admitted_for_route(
    item: dict[str, Any],
    decisions: dict[str, str],
    zone: str,
    roles: set[str],
    required_uses: set[str],
) -> bool:
    rights = item.get("rights") or {}
    return (
        item.get("role") in roles
        and item.get("authority") == "location_truth"
        and item.get("zone") == zone
        and rights.get("status") == "allowed"
        and decisions.get(item.get("evidence_id")) == "allowed"
        and required_uses <= set(rights.get("permitted_uses") or [])
    )


def select_render_route(bundle: dict[str, Any]) -> tuple[str, list[str]]:
    """Return the deterministic least-generative admissible render route."""
    contract = bundle.get("scene_contract") or {}
    policy = contract.get("render_policy") or {}
    if policy.get("prefer_least_generative") is not True:
        raise ValueError("G_RENDER_POLICY: prefer_least_generative must be true")

    allowed_modes = set(policy.get("allowed_modes") or [])
    zone = contract.get("zone")
    evidence = bundle.get("evidence") or []
    decisions = (bundle.get("rights_manifest") or {}).get("evidence_decisions") or {}

    plates = sorted(
        item["evidence_id"]
        for item in evidence
        if isinstance(item, dict)
        and _admitted_for_route(
            item, decisions, zone, {"location_plate"}, {"derivative_generation", "display"}
        )
    )
    if plates and "immutable_plate" in allowed_modes:
        return "immutable_plate", [plates[0]]

    reconstruction = sorted(
        item["evidence_id"]
        for item in evidence
        if isinstance(item, dict)
        and _admitted_for_route(
            item,
            decisions,
            zone,
            {"location_plate", "location_geometry", "location_appearance"},
            {"reconstruction"},
        )
    )
    if len(reconstruction) >= 2 and "multiview_reconstruction" in allowed_modes:
        return "multiview_reconstruction", reconstruction[:2]

    geometry = sorted(
        item["evidence_id"]
        for item in evidence
        if isinstance(item, dict)
        and _admitted_for_route(
            item, decisions, zone, {"location_geometry"}, {"derivative_generation"}
        )
    )
    appearance = sorted(
        item["evidence_id"]
        for item in evidence
        if isinstance(item, dict)
        and _admitted_for_route(
            item,
            decisions,
            zone,
            {"location_appearance", "location_plate"},
            {"derivative_generation", "display"},
        )
    )
    if geometry and appearance and "constrained_generation" in allowed_modes:
        return "constrained_generation", sorted({geometry[0], appearance[0]})

    raise ValueError(
        "G_RENDER_POLICY: No admissible render route for the requested zone and rights scope"
    )


def _validate_format(contract: dict[str, Any], errors: list[str]) -> None:
    fmt = contract.get("format") or {}
    if fmt.get("image_count") != 1:
        errors.append("G_FORMAT: image_count must equal 1")
    if fmt.get("standalone") is not True:
        errors.append("G_FORMAT: standalone must be true")
    if fmt.get("collage") is not False:
        errors.append("G_FORMAT: collage must be false")
    if fmt.get("text_overlay") is not False:
        errors.append("G_FORMAT: text_overlay must be false")
    aspect = fmt.get("aspect_ratio")
    if not isinstance(aspect, str) or not re.fullmatch(r"[1-9][0-9]*:[1-9][0-9]*", aspect):
        errors.append("G_FORMAT: aspect_ratio must be a positive W:H ratio")


def _validate_view_cone(bundle: dict[str, Any], contract: dict[str, Any], errors: list[str]) -> None:
    required_gates = set(contract.get("required_gates") or [])
    view_cone = bundle.get("view_cone")
    if "G_VIEW_CONE" in required_gates and not isinstance(view_cone, dict):
        errors.append("G_VIEW_CONE: required view_cone is missing")
        return
    if not isinstance(view_cone, dict):
        return
    visible = set(view_cone.get("visible_anchors") or [])
    required = set(contract.get("required_anchors") or [])
    missing = sorted(required - visible)
    if missing:
        errors.append(f"G_VIEW_CONE: required anchors not visible: {missing}")
    forbidden = set(view_cone.get("must_not_be_visible") or [])
    overlap = sorted(visible & forbidden)
    if overlap:
        errors.append(f"G_VIEW_CONE: prohibited anchors marked visible: {overlap}")
    fov = view_cone.get("horizontal_fov_deg")
    if not isinstance(fov, (int, float)) or not (0 < fov <= 180):
        errors.append("G_VIEW_CONE: horizontal_fov_deg must be in (0, 180]")


def _validate_temporal(
    contract: dict[str, Any],
    evidence: list[dict[str, Any]],
    decisions: dict[str, str],
    errors: list[str],
) -> None:
    snapshot = contract.get("target_snapshot") or {}
    as_of = parse_iso(snapshot.get("as_of"), "target_snapshot.as_of", errors, "G_TEMPORAL")
    max_age = snapshot.get("max_appearance_age_days")
    if not isinstance(max_age, int) or max_age < 0:
        errors.append("G_TEMPORAL: max_appearance_age_days must be a non-negative integer")
        return
    if as_of is None:
        return

    zone = contract.get("zone")
    current_nodes = [
        item
        for item in evidence
        if item.get("authority") == "location_truth"
        and item.get("role") in {"location_plate", "location_appearance"}
        and item.get("zone") == zone
        and item.get("temporal_class") == "current_appearance"
        and decisions.get(item.get("evidence_id")) == "allowed"
    ]
    if not current_nodes:
        errors.append(f"G_TEMPORAL: no current appearance evidence supports zone {zone!r}")
        return

    compatible = False
    for item in current_nodes:
        captured = parse_iso(
            item.get("captured_at"),
            f"evidence {item.get('evidence_id')} captured_at",
            errors,
            "G_TEMPORAL",
        )
        if captured is None:
            continue
        age = as_of - captured
        if age.total_seconds() < 0:
            errors.append(f"G_TEMPORAL: evidence {item.get('evidence_id')} postdates target snapshot")
            continue
        if age <= dt.timedelta(days=max_age):
            compatible = True
    if not compatible:
        errors.append(f"G_TEMPORAL: no current appearance evidence is within {max_age} day(s) of target snapshot")


def validate(bundle: dict[str, Any], require_render_plan: bool = False) -> tuple[bool, list[str]]:
    errors: list[str] = []
    contract = bundle.get("scene_contract") or {}
    passport = bundle.get("location_passport") or {}
    evidence = bundle.get("evidence") or []
    rights_manifest = bundle.get("rights_manifest") or {}

    if not isinstance(contract, dict) or not isinstance(passport, dict):
        return False, ["G_PROVENANCE: scene_contract and location_passport must be objects"]
    if not isinstance(evidence, list):
        return False, ["G_PROVENANCE: evidence must be an array"]

    if contract.get("location_id") != passport.get("location_id"):
        errors.append("G_LOCATION_IDENTITY: contract/passport location_id mismatch")
    zone = contract.get("zone")
    zones = set(passport.get("zones") or [])
    if not zone or zone not in zones:
        errors.append(f"G_SPATIAL: contract zone {zone!r} is not declared by LocationPassport")

    evidence_ids = [item.get("evidence_id") for item in evidence if isinstance(item, dict)]
    if not evidence or len(evidence_ids) != len(evidence) or any(not value for value in evidence_ids):
        errors.append("G_PROVENANCE: evidence IDs must be present")
    if len(set(evidence_ids)) != len(evidence_ids):
        errors.append("G_PROVENANCE: evidence IDs must be unique")
    evidence_id_set = set(evidence_ids)

    passport_ids = set(passport.get("evidence_node_ids") or [])
    if passport_ids != evidence_id_set:
        missing = sorted(passport_ids - evidence_id_set)
        extra = sorted(evidence_id_set - passport_ids)
        errors.append(f"G_PROVENANCE: LocationPassport evidence graph mismatch missing={missing} extra={extra}")

    decisions = rights_manifest.get("evidence_decisions") or {}
    if not isinstance(decisions, dict):
        decisions = {}
        errors.append("G_RIGHTS: evidence_decisions must be an object")
    decision_ids = set(decisions)
    if decision_ids != evidence_id_set:
        missing = sorted(evidence_id_set - decision_ids)
        extra = sorted(decision_ids - evidence_id_set)
        errors.append(f"G_RIGHTS: rights decisions must exactly cover evidence missing={missing} extra={extra}")

    for item in evidence:
        if not isinstance(item, dict):
            errors.append("G_PROVENANCE: every evidence entry must be an object")
            continue
        eid = item.get("evidence_id") or "<missing>"
        rights = item.get("rights") or {}
        status = rights.get("status", "unknown")
        decision = decisions.get(item.get("evidence_id"))
        if status != "allowed" or decision != "allowed":
            errors.append(f"G_RIGHTS: {eid} is not explicitly allowed")

        content_hash = item.get("content_hash")
        if not isinstance(content_hash, str) or not SHA256_RE.fullmatch(content_hash):
            errors.append(f"G_PROVENANCE: invalid content_hash for {eid}")

        derived_from = set(item.get("derived_from") or [])
        unknown_parents = sorted(derived_from - evidence_id_set)
        if unknown_parents:
            errors.append(f"G_PROVENANCE: {eid} derives from unknown evidence {unknown_parents}")

        role = item.get("role")
        authority = item.get("authority")
        source_type = rights.get("source_type")
        uses = set(rights.get("permitted_uses") or [])
        if authority == "location_truth" and role not in LOCATION_ROLES:
            errors.append(f"G_RIGHTS: {eid} role {role!r} cannot hold location_truth authority")
        if source_type == "generated" or role == "generated_continuity":
            if source_type != "generated" or role != "generated_continuity" or authority != "none":
                errors.append(f"G_RIGHTS: generated evidence {eid} must be generated_continuity with authority none")
            disallowed = sorted(uses - GENERATED_ALLOWED_USES)
            if disallowed:
                errors.append(f"G_RIGHTS: generated evidence {eid} has prohibited uses {disallowed}")

        uri = item.get("source_uri") or ""
        if _is_google_map_source(uri) and uses & PIXEL_USES:
            errors.append(f"G_RIGHTS: prohibited Google Maps/Street View pixel use in {eid}")

        item_zone = item.get("zone")
        if item_zone is not None and item_zone not in zones:
            errors.append(f"G_SPATIAL: evidence {eid} uses undeclared zone {item_zone!r}")

    if rights_manifest.get("verdict") != "PASS":
        errors.append("G_RIGHTS: rights_manifest verdict must be PASS")

    required = set(contract.get("required_gates") or [])
    unknown = required - HARD_GATES
    if unknown:
        errors.append(f"G_PROVENANCE: SceneContract contains unknown gates: {sorted(unknown)}")
    missing_mandatory = sorted(MANDATORY_GATES - required)
    if missing_mandatory:
        errors.append(f"G_PROVENANCE: SceneContract omits mandatory gates: {missing_mandatory}")

    zone_support = [
        item
        for item in evidence
        if isinstance(item, dict)
        and item.get("authority") == "location_truth"
        and item.get("role") in LOCATION_SCENE_ROLES
        and item.get("zone") == zone
        and decisions.get(item.get("evidence_id")) == "allowed"
    ]
    if not zone_support:
        errors.append(f"G_SPATIAL: no location evidence supports contract zone {zone!r}")

    _validate_format(contract, errors)
    _validate_view_cone(bundle, contract, errors)
    _validate_temporal(contract, evidence, decisions, errors)

    render_plan = bundle.get("render_plan")
    if require_render_plan and not isinstance(render_plan, dict):
        errors.append("G_RENDER_POLICY: render_plan is required")
    if isinstance(render_plan, dict):
        if render_plan.get("contract_hash") != canonical_hash(contract):
            errors.append("G_PROVENANCE: render_plan contract_hash mismatch")
        if render_plan.get("location_id") != contract.get("location_id"):
            errors.append("G_LOCATION_IDENTITY: render_plan location_id mismatch")
        if render_plan.get("zone") != zone:
            errors.append("G_SPATIAL: render_plan zone mismatch")
        if render_plan.get("format") != contract.get("format"):
            errors.append("G_FORMAT: render_plan format mismatch")
        if render_plan.get("target_snapshot") != contract.get("target_snapshot"):
            errors.append("G_TEMPORAL: render_plan target_snapshot mismatch")
        mode = render_plan.get("render_mode")
        allowed_modes = set((contract.get("render_policy") or {}).get("allowed_modes") or [])
        if mode not in allowed_modes:
            errors.append(f"G_RENDER_POLICY: render mode {mode!r} is not allowed")
        selected_ids = set(render_plan.get("evidence_ids") or [])
        if not selected_ids or not selected_ids <= evidence_id_set:
            errors.append("G_PROVENANCE: render_plan evidence_ids must be a non-empty evidence subset")
        try:
            expected_mode, expected_ids = select_render_route(bundle)
        except ValueError as exc:
            errors.append(str(exc))
        else:
            if mode != expected_mode or sorted(selected_ids) != expected_ids:
                errors.append(
                    "G_RENDER_POLICY: render_plan is not the deterministic least-generative route"
                )

    receipt = bundle.get("grounding_receipt")
    if receipt:
        if not isinstance(receipt, dict):
            errors.append("G_PROVENANCE: grounding_receipt must be an object")
        else:
            results = receipt.get("gate_results") or {}
            for gate in required:
                if results.get(gate) != "PASS":
                    errors.append(f"{gate}: receipt does not record PASS")
            expected_contract_hash = canonical_hash(contract)
            if receipt.get("contract_hash") != expected_contract_hash:
                errors.append("G_PROVENANCE: receipt contract_hash mismatch")
            source_hashes = {item.get("content_hash") for item in evidence if isinstance(item, dict) and item.get("content_hash")}
            if set(receipt.get("evidence_hashes") or []) != source_hashes:
                errors.append("G_PROVENANCE: receipt evidence_hashes do not exactly match evidence")
            if isinstance(render_plan, dict):
                if receipt.get("render_plan_hash") != canonical_hash(render_plan):
                    errors.append("G_PROVENANCE: receipt render_plan_hash mismatch")
                if receipt.get("render_mode") != render_plan.get("render_mode"):
                    errors.append("G_RENDER_POLICY: receipt render_mode mismatch")
            else:
                errors.append("G_RENDER_POLICY: receipt requires a render_plan")
            if errors and receipt.get("verdict") == "GROUNDED":
                errors.append("G_PROVENANCE: receipt claims GROUNDED despite failed invariant(s)")

    return not errors, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--require-render-plan", action="store_true")
    args = parser.parse_args()
    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    ok, errors = validate(bundle, require_render_plan=args.require_render_plan)
    if ok:
        print("GEOCANON PASS")
        return 0
    print("GEOCANON REJECT", file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
