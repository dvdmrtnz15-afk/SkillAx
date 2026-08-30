#!/usr/bin/env python3
"""Ingest a local evidence asset into a deterministic GeoEvidenceNode.

This is intentionally local-file first. It does not scrape provider imagery.
The caller must explicitly declare source type, rights status, and permitted
uses; unknown/omitted rights fail closed later in geocanon_validate.py.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import mimetypes
from pathlib import Path

ALLOWED_SOURCE_TYPES = {"user_owned", "open_data", "open_licensed", "provider_api", "other"}
ALLOWED_USES = {"metadata", "retrieval", "validation", "reconstruction", "derivative_generation", "display"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def infer_kind(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    if mime and mime.startswith("image/"):
        return "image"
    if mime and mime.startswith("video/"):
        return "video"
    return "other"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("asset", type=Path)
    p.add_argument("--evidence-id", required=True)
    p.add_argument("--source-type", required=True, choices=sorted(ALLOWED_SOURCE_TYPES))
    p.add_argument("--rights-status", default="unknown", choices=["allowed", "denied", "unknown"])
    p.add_argument("--use", action="append", dest="uses", default=[], choices=sorted(ALLOWED_USES))
    p.add_argument("--license", default=None)
    p.add_argument("--terms-uri", default=None)
    p.add_argument("--source-uri", default=None)
    p.add_argument("--captured-at", default=None)
    p.add_argument("--lat", type=float, default=None)
    p.add_argument("--lon", type=float, default=None)
    p.add_argument("--notes", default="")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    if not args.asset.is_file():
        raise SystemExit(f"Asset not found: {args.asset}")
    if (args.lat is None) ^ (args.lon is None):
        raise SystemExit("--lat and --lon must be supplied together")
    if not args.uses:
        raise SystemExit("At least one --use is required")

    node = {
        "evidence_id": args.evidence_id,
        "kind": infer_kind(args.asset),
        "content_hash": sha256_file(args.asset),
        "captured_at": args.captured_at,
        "acquired_at": iso_now(),
        "location": None if args.lat is None else {"lat": args.lat, "lon": args.lon},
        "source_uri": args.source_uri,
        "rights": {
            "status": args.rights_status,
            "source_type": args.source_type,
            "license": args.license,
            "terms_uri": args.terms_uri,
            "permitted_uses": sorted(set(args.uses)),
            "notes": args.notes,
        },
        "derived_from": [],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(node, indent=2, sort_keys=True) + "\n")
    print(f"GEOCANON INGEST {args.evidence_id} sha256={node['content_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
