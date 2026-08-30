#!/usr/bin/env python3
"""Ingest a local asset as a typed, deterministic GeoCanon EvidenceNode.

The tool is local-file first and never scrapes provider imagery. The caller
must declare role, authority, rights, temporal class, and permitted uses.
Unknown rights fail later in the semantic validator; impossible authority
combinations fail immediately here.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import mimetypes
from pathlib import Path

ALLOWED_SOURCE_TYPES = {
    "user_owned",
    "open_data",
    "open_licensed",
    "provider_api",
    "generated",
    "other",
}
ALLOWED_USES = {
    "metadata",
    "retrieval",
    "validation",
    "reconstruction",
    "derivative_generation",
    "display",
}
ALLOWED_ROLES = {
    "location_plate",
    "location_geometry",
    "location_appearance",
    "persona_identity",
    "wardrobe",
    "object_geometry",
    "lighting_reference",
    "camera_reference",
    "negative_reference",
    "generated_continuity",
    "metadata",
}
ALLOWED_AUTHORITIES = {
    "location_truth",
    "subject_truth",
    "object_truth",
    "capture_reference",
    "none",
}
ALLOWED_TEMPORAL_CLASSES = {
    "structural",
    "current_appearance",
    "historical",
    "transient",
    "metadata",
}
LOCATION_ROLES = {"location_plate", "location_geometry", "location_appearance", "metadata"}
GENERATED_USES = {"retrieval", "display"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_timestamp(value: str | None, label: str) -> None:
    if value is None:
        return
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit(f"{label} must be valid ISO-8601") from exc
    if parsed.tzinfo is None:
        raise SystemExit(f"{label} must include a timezone")


def infer_kind(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    if mime and mime.startswith("image/"):
        return "image"
    if mime and mime.startswith("video/"):
        return "video"
    return "other"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("asset", type=Path)
    parser.add_argument("--evidence-id", required=True)
    parser.add_argument("--source-type", required=True, choices=sorted(ALLOWED_SOURCE_TYPES))
    parser.add_argument("--rights-status", default="unknown", choices=["allowed", "denied", "unknown"])
    parser.add_argument("--use", action="append", dest="uses", default=[], choices=sorted(ALLOWED_USES))
    parser.add_argument("--role", required=True, choices=sorted(ALLOWED_ROLES))
    parser.add_argument("--authority", required=True, choices=sorted(ALLOWED_AUTHORITIES))
    parser.add_argument("--temporal-class", required=True, choices=sorted(ALLOWED_TEMPORAL_CLASSES))
    parser.add_argument("--zone", default=None)
    parser.add_argument("--license", default=None)
    parser.add_argument("--terms-uri", default=None)
    parser.add_argument("--source-uri", default=None)
    parser.add_argument("--captured-at", default=None)
    parser.add_argument("--lat", type=float, default=None)
    parser.add_argument("--lon", type=float, default=None)
    parser.add_argument("--notes", default="")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if not args.asset.is_file():
        raise SystemExit(f"Asset not found: {args.asset}")
    if (args.lat is None) ^ (args.lon is None):
        raise SystemExit("--lat and --lon must be supplied together")
    if not args.uses:
        raise SystemExit("At least one --use is required")
    validate_timestamp(args.captured_at, "--captured-at")

    uses = set(args.uses)
    is_generated = args.source_type == "generated" or args.role == "generated_continuity"
    if is_generated:
        if not (
            args.source_type == "generated"
            and args.role == "generated_continuity"
            and args.authority == "none"
        ):
            raise SystemExit("generated evidence must use generated_continuity with authority none")
        disallowed = sorted(uses - GENERATED_USES)
        if disallowed:
            raise SystemExit(f"generated evidence has prohibited uses: {disallowed}")

    if args.authority == "location_truth" and args.role not in LOCATION_ROLES:
        raise SystemExit("location_truth authority requires a location or metadata role")
    if args.role in {"location_plate", "location_geometry", "location_appearance"} and not args.zone:
        raise SystemExit(f"role {args.role} requires --zone")
    if args.temporal_class == "current_appearance" and not args.captured_at:
        raise SystemExit("current_appearance evidence requires --captured-at")

    node = {
        "evidence_id": args.evidence_id,
        "kind": infer_kind(args.asset),
        "role": args.role,
        "authority": args.authority,
        "content_hash": sha256_file(args.asset),
        "captured_at": args.captured_at,
        "acquired_at": iso_now(),
        "location": None if args.lat is None else {"lat": args.lat, "lon": args.lon},
        "zone": args.zone,
        "temporal_class": args.temporal_class,
        "source_uri": args.source_uri,
        "rights": {
            "status": args.rights_status,
            "source_type": args.source_type,
            "license": args.license,
            "terms_uri": args.terms_uri,
            "permitted_uses": sorted(uses),
            "notes": args.notes,
        },
        "derived_from": [],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(node, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"GEOCANON INGEST {args.evidence_id} sha256={node['content_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
