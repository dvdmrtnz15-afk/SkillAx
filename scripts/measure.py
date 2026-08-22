#!/usr/bin/env python3
"""SCAN measure: pure function from pack → verdict + id.

PASS requires hex id. PENDING never prints a Skill Code.
--publish writes catalog/live.json only on PASS + hex.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

TYPES = {"job", "refuse", "load", "bind", "safety"}
CALLS = {
    "skillax": "000.10.01",
    "sovereign-control-plane": "100.00.01",
    "cinematic-narrative-engine": "200.00.01",
    "consultative-service-operations-os": "300.00.01",
    "constraint-based-planning-engine": "400.00.01",
    "structured-document-compliance-agent": "500.00.01",
    "persistent-character-world-system": "600.00.01",
    "extract-audit-kernel": "800.00.01",
}


def upc_check(body10: str) -> str:
    digits = [int(c) for c in body10]
    odd = sum(digits[0::2]) * 3
    even = sum(digits[1::2])
    return str((10 - (odd + even) % 10) % 10)


def skill_code(call: str) -> str:
    a, b, c = call.split(".")
    body = f"{int(a):03d}{int(b):03d}{int(c):04d}"
    return "0" + body + upc_check(body)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def canonical(call: str, name: str, axioms: dict, out_text: str) -> bytes:
    bag = {
        "call": call,
        "name": name,
        "axioms": axioms,
        "out": out_text.replace("\r\n", "\n"),
    }
    raw = json.dumps(bag, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return raw.encode("utf-8")


def must_phrases(out_text: str) -> list[str]:
    found = []
    for line in out_text.splitlines():
        line = line.strip()
        m = re.match(r"MUST(?:-REFUSE)?:\s*(.+)$", line, re.I)
        if m:
            found.append(m.group(1).strip().lower())
    return found


def axiom_blob(axioms: dict) -> str:
    parts = []
    for ax in axioms.get("axioms", []):
        parts.append(f"{ax.get('type','')} {ax.get('text','')}")
    return " ".join(parts).lower()


def measure(pack: Path, catalog: dict) -> dict:
    checks = []
    axioms_path = pack / "axioms.json"
    out_path = pack / "out.md"
    name = pack.name
    call = CALLS.get(name, "")

    if not axioms_path.exists() or not out_path.exists() or not call:
        return {
            "verdict": "HOLD",
            "id": "PENDING",
            "why": "unmeasurable: need axioms.json, out.md, and a call number",
            "checks": checks,
            "print": "NO",
        }

    axioms = load_json(axioms_path)
    out_text = out_path.read_text(encoding="utf-8")
    rows = axioms.get("axioms", [])
    types = [r.get("type") for r in rows]

    if not (3 <= len(rows) <= 5):
        checks.append("FAIL axiom count")
    if types.count("job") != 1:
        checks.append("FAIL need exactly one job")
    if types.count("refuse") < 1:
        checks.append("FAIL need a refuse")
    if any(t not in TYPES for t in types):
        checks.append("FAIL unknown type")
    if axioms.get("skill") and axioms["skill"] != name:
        checks.append("FAIL skill name mismatch")

    blob = axiom_blob(axioms)
    phrases = must_phrases(out_text)
    if not phrases:
        checks.append("FAIL out.md has no MUST lines")
    for p in phrases:
        if p not in blob:
            checks.append(f"FAIL missing refuse/shape: {p}")

    bag = canonical(call, name, axioms, out_text)
    hex_id = hashlib.sha256(bag).hexdigest()

    live = catalog.get("rows", [])
    for row in live:
        if row.get("status") != "live":
            continue
        if row.get("call") == call and row.get("id") != hex_id:
            return {
                "verdict": "COUNTERFEIT",
                "id": hex_id,
                "call": call,
                "name": name,
                "why": "live call bound to a different id",
                "checks": checks,
                "print": "NO",
            }
        if row.get("id") == hex_id and row.get("call") != call:
            return {
                "verdict": "COUNTERFEIT",
                "id": hex_id,
                "call": call,
                "name": name,
                "why": "id rebound to a different call",
                "checks": checks,
                "print": "NO",
            }

    if checks:
        return {
            "verdict": "FAIL",
            "id": hex_id,
            "call": call,
            "name": name,
            "why": checks[0],
            "checks": checks,
            "print": "NO",
        }

    code = skill_code(call)
    payload = f"SA6/{call}/{name}/{hex_id}"
    return {
        "verdict": "PASS",
        "id": hex_id,
        "call": call,
        "name": name,
        "code": code,
        "payload": payload,
        "why": "law holds",
        "checks": ["PASS structure", "PASS fixture", "PASS identity"],
        "print": "YES",
    }


def publish(result: dict, catalog: dict, cat_path: Path) -> dict:
    if result.get("verdict") != "PASS":
        result["published"] = "REFUSED"
        result["why_publish"] = f"publish requires PASS, got {result.get('verdict')}"
        return result
    if result.get("id") in (None, "", "PENDING"):
        result["published"] = "REFUSED"
        result["why_publish"] = "publish requires hex id"
        result["print"] = "NO"
        return result

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = {
        "call": result["call"],
        "name": result["name"],
        "id": result["id"],
        "code": result["code"],
        "payload": result["payload"],
        "status": "live",
        "measured_at": now,
    }
    rows = list(catalog.get("rows", []))
    for i, existing in enumerate(rows):
        if existing.get("call") == row["call"] and existing.get("status") == "live":
            if existing.get("id") == row["id"]:
                rows[i] = {**existing, "measured_at": now}
                catalog["rows"] = rows
                write_json(cat_path, catalog)
                result["published"] = "IDEMPOTENT"
                result["catalog"] = str(cat_path)
                return result
            result["published"] = "REFUSED"
            result["why_publish"] = "live call has a different id; retire first"
            return result
        if existing.get("id") == row["id"] and existing.get("call") != row["call"]:
            result["published"] = "REFUSED"
            result["why_publish"] = "id already bound to another call"
            return result

    rows.append(row)
    catalog["rows"] = rows
    write_json(cat_path, catalog)
    result["published"] = "WRITTEN"
    result["catalog"] = str(cat_path)
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pack", help="directory with axioms.json and out.md")
    ap.add_argument("--catalog", default=None)
    ap.add_argument("--expect", default=None, help="required verdict")
    ap.add_argument(
        "--publish",
        action="store_true",
        help="write catalog/live.json only if verdict is PASS and id is hex",
    )
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    pack = Path(args.pack)
    if not pack.is_absolute():
        pack = (root / pack).resolve()
    cat_path = Path(args.catalog) if args.catalog else root / "catalog" / "live.json"
    catalog = load_json(cat_path) if cat_path.exists() else {"rows": []}
    result = measure(pack, catalog)
    if args.publish:
        result = publish(result, catalog, cat_path)
        if result.get("published") == "REFUSED":
            print(json.dumps(result, indent=2))
            raise SystemExit(2)
    print(json.dumps(result, indent=2))
    if args.expect and result["verdict"] != args.expect:
        raise SystemExit(f"expected {args.expect} got {result['verdict']}")
    if result["verdict"] in {"FAIL", "COUNTERFEIT"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
