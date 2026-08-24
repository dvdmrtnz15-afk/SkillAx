#!/usr/bin/env python3
"""Run frozen hybrid rank fixtures. Exit 1 on mismatch."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ("consult booking dual site", "consultative-service-operations-os"),
    ("ssrf agent recovery", "sovereign-control-plane"),
    ("vertical six-second reels", "cinematic-narrative-engine"),
    ("high stakes legal policy document under constraints", "structured-document-compliance-agent"),
    ("plan meals with allergens and quotas", "constraint-based-planning-engine"),
    ("make this email warmer", "human-adaptive-communication"),
    ("card", "none"),
]


def load_line(query: str, mode: str = "hybrid") -> str:
    out = subprocess.check_output(
        [sys.executable, str(ROOT / "scripts" / "rank.py"), query, "--mode", mode],
        text=True,
    )
    for line in out.splitlines():
        if line.startswith("LOAD="):
            return line.split("=", 1)[1].replace(" TIE", "")
    raise SystemExit(f"no LOAD line for {query!r}\n{out}")


def main() -> None:
    failed = 0
    for query, expect in CASES:
        got = load_line(query, "hybrid")
        ok = got == expect or (expect == "none" and got.startswith("none"))
        mark = "OK" if ok else "FAIL"
        print(f"{mark}\t{query!r}\texpect={expect}\tgot={got}")
        if not ok:
            failed += 1
    if failed:
        raise SystemExit(failed)


if __name__ == "__main__":
    main()
