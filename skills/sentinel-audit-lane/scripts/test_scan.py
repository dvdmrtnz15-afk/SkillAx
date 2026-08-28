#!/usr/bin/env python3
"""Deterministic tests for the Sentinel scanner."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SCAN = Path(__file__).resolve().parent / "scan.py"
POLICY = SKILL_DIR / "examples" / "policy.yml"


def run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCAN), *args],
        cwd=cwd or SKILL_DIR,
        text=True,
        capture_output=True,
    )


def test_self_scan_authority_none() -> None:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "receipt.json"
        proc = run(["--root", str(SKILL_DIR), "--policy", str(POLICY), "--out", str(out), "--delivery-id", "test"])
        assert out.is_file(), proc.stderr
        receipt = json.loads(out.read_text(encoding="utf-8"))
        assert receipt["authority"] == "none"
        assert receipt["effect_authority"] == "none"
        assert receipt["receipt_class"] == "ContextReceipt"
        assert receipt["dedupe"]["delivery_id"] == "test"
        assert receipt["dedupe"]["situation_id"]
        assert receipt["dedupe"]["occurrence_id"]
        assert receipt["content_digest"].startswith("sha256:")


def test_stable_digest() -> None:
    with tempfile.TemporaryDirectory() as td:
        a = Path(td) / "a.json"
        b = Path(td) / "b.json"
        run(["--root", str(SKILL_DIR), "--policy", str(POLICY), "--out", str(a), "--delivery-id", "same"])
        run(["--root", str(SKILL_DIR), "--policy", str(POLICY), "--out", str(b), "--delivery-id", "same"])
        ra = json.loads(a.read_text(encoding="utf-8"))
        rb = json.loads(b.read_text(encoding="utf-8"))
        assert ra["content_digest"] == rb["content_digest"]
        assert ra["dedupe"]["situation_id"] == rb["dedupe"]["situation_id"]


def test_unpinned_caller_fails() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        wf = root / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "sentinel-caller.yml").write_text(
            "name: bad\non: push\njobs:\n  a:\n    uses: dvdmrtnz15-afk/SkillAx/.github/workflows/sentinel.yml@main\n",
            encoding="utf-8",
        )
        out = root / "receipt.json"
        proc = run(["--root", str(root), "--out", str(out), "--delivery-id", "pin"])
        receipt = json.loads(out.read_text(encoding="utf-8"))
        rules = {f["rule"] for f in receipt["findings"]}
        assert "engine-pin" in rules
        assert proc.returncode == 1


def test_authority_claim_fails() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "note.md").write_text("this receipt authorizes the effect of publish\n", encoding="utf-8")
        out = root / "receipt.json"
        proc = run(["--root", str(root), "--out", str(out), "--delivery-id", "auth"])
        receipt = json.loads(out.read_text(encoding="utf-8"))
        rules = {f["rule"] for f in receipt["findings"]}
        assert "authority-none" in rules
        assert proc.returncode == 1


def main() -> int:
    tests = [
        test_self_scan_authority_none,
        test_stable_digest,
        test_unpinned_caller_fails,
        test_authority_claim_fails,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"validated {len(tests)} sentinel test(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
