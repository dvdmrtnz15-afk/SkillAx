#!/usr/bin/env python3
"""Read-only Sentinel scanner. Emits a ContextReceipt. Never authorizes effects."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

AUTHORITY_NONE = "none"
RECEIPT_CLASS = "ContextReceipt"

DEFAULT_EXCLUDES = {
    ".git",
    ".sentinel/engine",
    ".sentinel/receipts",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "__pycache__",
}

UNPINNED = re.compile(
    r"uses:\s*dvdmrtnz15-afk/SkillAx/.github/workflows/sentinel\.yml@(main|master|latest)\b"
)
FLOATING_ACTION = re.compile(
    r"uses:\s*dvdmrtnz15-afk/SkillAx/.github/workflows/sentinel\.yml\s*$", re.M
)
WRITE_VERBS = re.compile(
    r"\b(gh\s+pr\s+merge|git\s+push\s+--force|terraform\s+apply|kubectl\s+apply|"
    r"npm\s+publish|twine\s+upload|stripe\s+pay)\b",
    re.I,
)
SECOND_OS = re.compile(
    r"\b(new (kernel|fabric|court|brain|control plane os)|federation context gateway of record)\b",
    re.I,
)
CAPSULES = (
    "ContextPacket",
    "ContextPassport",
    "ContextReceipt",
    "ProofContext",
    "ComprehensionPacket",
    "EffectAuthorizationCapsule",
)
AUTHORITY_CLAIM = re.compile(
    r"\b(this (packet|receipt|capsule|scan) (authorizes|grants|permits) (the )?effect)\b",
    re.I,
)

TEXT_SUFFIXES = {
    ".md", ".txt", ".yml", ".yaml", ".json", ".py", ".ts", ".tsx", ".js", ".rs", ".toml", ".sh",
}


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def git_rev(root: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, stderr=subprocess.DEVNULL, text=True
        )
        return out.strip() or "unknown"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def git_repo_name(root: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], cwd=root, stderr=subprocess.DEVNULL, text=True
        )
        return Path(out.strip()).name
    except (subprocess.CalledProcessError, FileNotFoundError):
        return root.name


def load_policy(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {
            "profile_id": "default-review",
            "owner": "unspecified",
            "purpose": "review-only",
            "engine_pin": "local-tree",
            "exclude_paths": sorted(DEFAULT_EXCLUDES),
            "allowed_write_globs": [
                ".github/workflows/sentinel-caller.yml",
                ".sentinel/policy.yml",
                ".sentinel/receipts/",
            ],
            "nonclaims": ["not authorization", "not product state", "not canon promotion"],
        }
    raw = path.read_text(encoding="utf-8")
    data: dict[str, Any] = {}
    key = None
    acc: list[str] = []
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - "):
            acc.append(line[4:].strip())
            continue
        if key and acc:
            data[key] = acc
            acc = []
            key = None
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            k, v = k.strip(), v.strip()
            if v == "":
                key = k
                acc = []
            else:
                data[k] = v
    if key and acc:
        data[key] = acc
    data.setdefault("exclude_paths", sorted(DEFAULT_EXCLUDES))
    data.setdefault("nonclaims", ["not authorization", "not product state", "not canon promotion"])
    data.setdefault("engine_pin", "local-tree")
    return data


def excluded(rel: str, excludes: list[str]) -> bool:
    parts = Path(rel).parts
    if any(p in DEFAULT_EXCLUDES for p in parts):
        return True
    for ex in excludes:
        ex = ex.rstrip("/")
        if rel == ex or rel.startswith(ex + "/"):
            return True
    return False


def iter_files(root: Path, excludes: list[str]) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if excluded(rel, excludes):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        files.append(path)
    return sorted(files)


def scan_text(rel: str, text: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if UNPINNED.search(text) or FLOATING_ACTION.search(text):
        findings.append({
            "id": f"unpin:{rel}",
            "severity": "fail",
            "rule": "engine-pin",
            "path": rel,
            "detail": "Sentinel caller is not pinned to an immutable SHA.",
        })
    if WRITE_VERBS.search(text) and rel.startswith(".github/workflows/"):
        findings.append({
            "id": f"write:{rel}",
            "severity": "fail",
            "rule": "no-effect",
            "path": rel,
            "detail": "Workflow contains a production write verb.",
        })
    if SECOND_OS.search(text):
        findings.append({
            "id": f"os:{rel}",
            "severity": "fail",
            "rule": "no-second-os",
            "path": rel,
            "detail": "Introduces a first-class OS/kernel/fabric without a Concept Registry decision.",
        })
    if AUTHORITY_CLAIM.search(text):
        findings.append({
            "id": f"auth:{rel}",
            "severity": "fail",
            "rule": "authority-none",
            "path": rel,
            "detail": "Text claims a packet or receipt authorizes an effect.",
        })
    present = [name for name in CAPSULES if name in text]
    if "EffectAuthorizationCapsule" in present and "ContextReceipt" in present:
        if re.search(
            r"EffectAuthorizationCapsule.{0,40}ContextReceipt|ContextReceipt.{0,40}EffectAuthorizationCapsule",
            text,
        ):
            findings.append({
                "id": f"capsule:{rel}",
                "severity": "warn",
                "rule": "capsule-separation",
                "path": rel,
                "detail": "ContextReceipt and EffectAuthorizationCapsule appear in the same clause. Keep them distinct.",
            })
    return findings


def build_receipt(root: Path, policy: dict[str, Any], delivery_id: str) -> dict[str, Any]:
    excludes = list(policy.get("exclude_paths") or [])
    findings: list[dict[str, str]] = []
    files = iter_files(root, excludes)
    omissions: list[str] = []
    if not files:
        omissions.append("no-text-files-scanned")
    for path in files:
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            omissions.append(rel)
            continue
        findings.extend(scan_text(rel, text))
    revision = git_rev(root)
    repo = git_repo_name(root)
    engine_pin = str(policy.get("engine_pin") or "local-tree")
    policy_blob = json.dumps(policy, sort_keys=True, separators=(",", ":"))
    situation = sha256_text(f"{repo}:{revision}:{policy_blob}")[7:23]
    occurrence = sha256_text(delivery_id + situation + revision)[7:23]
    body = {
        "receipt_class": RECEIPT_CLASS,
        "authority": AUTHORITY_NONE,
        "effect_authority": AUTHORITY_NONE,
        "repo": repo,
        "revision": revision,
        "engine_pin": engine_pin,
        "policy_digest": sha256_text(policy_blob),
        "freshness": "current" if revision != "unknown" else "unknown",
        "findings": findings,
        "conflicts": sorted({f["rule"] for f in findings if f["severity"] == "fail"}),
        "omissions": omissions,
        "dedupe": {
            "delivery_id": delivery_id,
            "situation_id": situation,
            "occurrence_id": occurrence,
        },
        "nonclaims": list(policy.get("nonclaims") or []),
    }
    stable = json.dumps(body, sort_keys=True, separators=(",", ":"))
    body["content_digest"] = sha256_text(stable)
    return body


def assert_no_authority(receipt: dict[str, Any]) -> None:
    if receipt.get("authority") != "none" or receipt.get("effect_authority") != "none":
        raise SystemExit("sentinel fail-closed: receipt claimed authority")
    if receipt.get("receipt_class") != RECEIPT_CLASS:
        raise SystemExit("sentinel fail-closed: wrong receipt class")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sentinel read-only scanner")
    parser.add_argument("--root", default=".", help="checkout root")
    parser.add_argument("--policy", default="", help="path to policy profile")
    parser.add_argument("--out", default="", help="write receipt JSON here")
    parser.add_argument("--delivery-id", default="local")
    parser.add_argument("--assert-no-authority", default="", help="validate an existing receipt")
    args = parser.parse_args()
    if args.assert_no_authority:
        receipt = json.loads(Path(args.assert_no_authority).read_text(encoding="utf-8"))
        assert_no_authority(receipt)
        print("authority:none")
        return 0
    root = Path(args.root).resolve()
    policy_path = Path(args.policy) if args.policy else None
    if policy_path and not policy_path.is_absolute():
        policy_path = (root / policy_path) if not policy_path.exists() else policy_path
    policy = load_policy(policy_path if policy_path and policy_path.exists() else None)
    receipt = build_receipt(root, policy, args.delivery_id)
    assert_no_authority(receipt)
    text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(out.as_posix())
    else:
        sys.stdout.write(text)
    fails = [f for f in receipt["findings"] if f["severity"] == "fail"]
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
