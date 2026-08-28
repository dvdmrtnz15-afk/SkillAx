#!/usr/bin/env python3
"""TrueNorth Federation Sentinel: deterministic, read-only repository audit.

Sentinel observes repository candidates and emits evidence. It does not grant
authority, approve promotion, mutate source, post comments, push, merge, or
execute production effects.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import html
import json
import os
from pathlib import Path
import posixpath
import re
import stat
import subprocess
import sys
from typing import Any, Iterable
from urllib.parse import quote_from_bytes

VERSION = "1.0.0-candidate"
POLICY_SCHEMA = "truenorth.sentinel.policy.v1"
REVIEW_EVIDENCE_SCHEMA = "truenorth.sentinel.review-evidence.v1"
SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
POLICY_KEYS = {
    "$schema", "schema", "profile", "enforcement", "fail_on",
    "max_file_bytes", "sensitive_globs", "required_evidence",
}

DEFAULT_POLICY: dict[str, Any] = {
    "schema": POLICY_SCHEMA,
    "profile": "baseline",
    "max_file_bytes": 5 * 1024 * 1024,
    "sensitive_globs": [],
    "required_evidence": [],
}

SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN (?:(?:RSA|EC|DSA|OPENSSH|ENCRYPTED|PGP) )?PRIVATE KEY(?: BLOCK)?-----"), "private key material"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key identifier"),
    (re.compile(r"\bgh[oprsu]_[A-Za-z0-9]{30,}\b"), "GitHub token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "GitHub fine-grained token"),
    (re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"), "GitLab token"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"), "Slack token"),
    (re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}\b"), "Stripe live key"),
    (re.compile(r"\bnpm_[A-Za-z0-9]{30,}\b"), "npm token"),
    (re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b"), "API key-like token"),
]

DANGEROUS_PATTERNS = [
    (re.compile(r"(?:curl|wget)[^\n|;]*\|\s*(?:sudo\s+)?(?:sh|bash)\b", re.I), "remote download piped to shell"),
    (re.compile(
        r"\brm\s+(?=[^\n]*(?:-[A-Za-z]*[rR][A-Za-z]*|--recursive))"
        r"(?=[^\n]*(?:-[A-Za-z]*f[A-Za-z]*|--force))"
        r"[^\n]*(?:\s(?:--\s+)?/|\s~|\$(?:HOME|\{HOME\}))"
    ), "broad recursive deletion"),
    (re.compile(r"\bgit\s+(?:reset\s+--hard|clean\s+-[^\n]*f)\b"), "destructive Git operation"),
    (re.compile(r"\bchmod\s+(?:-R\s+)?777\b"), "world-writable permissions"),
]

BIDI_CONTROLS = {chr(value) for value in (0x061C, 0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2066, 0x206A))}
CONFLICT_RE = re.compile(r"^(?:<{7}|={7}|>{7})(?:\s|$)", re.MULTILINE)
USES_RE = re.compile(r"^[ \t]*-?[ \t]*uses:[ \t]*([^\s#]+)", re.MULTILINE)
PERMISSION_NAMES = r"actions|attestations|checks|contents|deployments|discussions|id-token|issues|packages|pages|pull-requests|repository-projects|security-events|statuses"
WRITE_PERMISSION_RE = re.compile(
    rf"^[ \t]*(?:[\"']?permissions[\"']?[ \t]*:[ \t]*[\"']?write-all[\"']?|[\"']?(?:{PERMISSION_NAMES})[\"']?[ \t]*:[ \t]*[\"']?write[\"']?)[ \t]*(?:#.*)?$",
    re.MULTILINE,
)
PERMISSION_ENTRY_RE = re.compile(rf"^[ \t]*[\"']?(?:{PERMISSION_NAMES})[\"']?[ \t]*:[ \t]*([^#\n]*?)[ \t]*(?:#.*)?$", re.MULTILINE)
SAFE_PERMISSION_VALUE_RE = re.compile(r"[\"']?(?:read|none)[\"']?", re.I)
INLINE_WRITE_PERMISSION_RE = re.compile(r"[\"']?permissions[\"']?\s*:\s*\{[^}\n]*\bwrite\b[^}\n]*\}", re.I)
WORKFLOW_KEY_RE = re.compile(r"(?:^|[\[{,])\s*[\"']?(uses|permissions)[\"']?\s*:", re.MULTILINE)
PERMISSIONS_LINE_RE = re.compile(r"^[ \t]*[\"']?permissions[\"']?[ \t]*:[ \t]*([^#\n]*?)[ \t]*(?:#.*)?$", re.MULTILINE)
PRIVILEGED_TRIGGER_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:pull_request_target|workflow_run)(?![A-Za-z0-9_-])",
    re.IGNORECASE,
)
MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
EMPTY_EVIDENCE_RE = re.compile(r"^(?:todo|tbd|none|n/?a|placeholder)(?:[.!])?$", re.I)


class SentinelError(RuntimeError):
    pass


def git_environment() -> dict[str, str]:
    return {
        "HOME": os.environ.get("HOME", ""),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_EXTERNAL_DIFF": "",
        "GIT_LITERAL_PATHSPECS": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
    }


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "submodule.recurse=false", "-C", str(repo), *args],
        check=check,
        text=True,
        encoding="utf-8",
        errors="surrogateescape",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=git_environment(),
    )


def git_bytes(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "submodule.recurse=false", "-C", str(repo), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=git_environment(),
    )


def git_path(data: bytes) -> str:
    return data.decode("utf-8", errors="surrogateescape")


def evidence_path(path: str) -> str:
    """Return a reversible ASCII representation for any Git/filesystem path."""
    return quote_from_bytes(os.fsencode(path), safe="/ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


def safe_text(value: str) -> str:
    return value.encode("utf-8", errors="backslashreplace").decode("utf-8")


def git_status(repo: Path) -> bytes:
    result = git_bytes(repo, "status", "--porcelain=v1", "-z")
    if result.returncode != 0:
        raise SentinelError(f"cannot inspect working-tree status: {result.stderr.decode('utf-8', errors='replace').strip()}")
    return result.stdout


def require_canonical_worktree(repo: Path) -> None:
    inside = git(repo, "rev-parse", "--is-inside-work-tree", check=False)
    top = git(repo, "rev-parse", "--path-format=absolute", "--show-toplevel", check=False)
    if inside.returncode != 0 or inside.stdout.strip() != "true" or top.returncode != 0:
        raise SentinelError("repository is not a canonical Git working tree")
    try:
        canonical = Path(top.stdout.strip()).resolve(strict=True)
    except OSError as exc:
        raise SentinelError("canonical Git working-tree root cannot be resolved") from exc
    if canonical != repo:
        raise SentinelError("repository path does not equal Git's canonical working-tree root")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SentinelError(f"cannot load JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SentinelError(f"expected a JSON object in {path}")
    return value


def parse_json_bytes(data: bytes, source: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SentinelError(f"cannot load JSON from {source}: {exc}") from exc
    if not isinstance(value, dict):
        raise SentinelError(f"expected a JSON object in {source}")
    return value


def validate_policy_document(value: dict[str, Any]) -> None:
    unknown = set(value) - POLICY_KEYS
    if unknown:
        raise SentinelError(f"unknown policy keys: {', '.join(sorted(unknown))}")
    if value.get("schema") != POLICY_SCHEMA:
        raise SentinelError(f"policy schema must be {POLICY_SCHEMA}")
    if "profile" not in value:
        raise SentinelError("policy profile is required")
    if "$schema" in value and not isinstance(value["$schema"], str):
        raise SentinelError("policy $schema must be a string")
    profile = value["profile"]
    if not isinstance(profile, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,96}", profile):
        raise SentinelError("profile must be a stable 1-96 character identifier")
    if "enforcement" in value and value["enforcement"] != "audit":
        raise SentinelError("Sentinel v1 is audit-only; policy enforcement must be audit")
    if "fail_on" in value:
        fail_on = value["fail_on"]
        if not isinstance(fail_on, list) or not all(isinstance(item, str) and item in SEVERITY_ORDER for item in fail_on):
            raise SentinelError("fail_on must contain only supported severity strings")
        if len(fail_on) != len(set(fail_on)):
            raise SentinelError("fail_on entries must be unique")
    if "max_file_bytes" in value:
        maximum = value["max_file_bytes"]
        if type(maximum) is not int or not 1024 <= maximum <= 104857600:
            raise SentinelError("max_file_bytes must be an integer between 1024 and 104857600")
    for key, minimum in (("sensitive_globs", 1), ("required_evidence", 2)):
        if key not in value:
            continue
        items = value[key]
        if not isinstance(items, list) or not all(isinstance(item, str) and len(item) >= minimum for item in items):
            raise SentinelError(f"{key} must be a list of strings with minimum length {minimum}")
        if len(items) != len(set(items)):
            raise SentinelError(f"{key} entries must be unique")


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_commit(repo: Path, ref: str | None) -> str | None:
    if not ref:
        return None
    result = git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}", check=False)
    value = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise SentinelError(f"cannot resolve commit ref: {ref}")
    return value


def git_blob(repo: Path, ref: str, relative: str) -> tuple[bytes | None, str | None]:
    info = git_object_info(repo, ref, relative)
    if info is None:
        return None, None
    mode, object_type, object_id, _ = info
    if object_type != "blob":
        return None, mode
    blob = git_bytes(repo, "cat-file", "blob", object_id)
    if blob.returncode != 0:
        raise SentinelError(f"cannot read {relative} at {ref}: {blob.stderr.decode('utf-8', errors='replace').strip()}")
    return blob.stdout, mode


def git_object_info(repo: Path, ref: str, relative: str) -> tuple[str, str, str, int | None] | None:
    result = git_bytes(repo, "ls-tree", "-l", ref, "--", relative)
    line = result.stdout.rstrip(b"\n")
    if result.returncode != 0:
        raise SentinelError(
            f"cannot inspect {evidence_path(relative)} at {ref}: "
            f"{result.stderr.decode('utf-8', errors='replace').strip()}"
        )
    if not line:
        return None
    header = line.split(b"\t", 1)[0].split()
    if len(header) != 4:
        raise SentinelError(f"invalid Git tree entry for {evidence_path(relative)} at {ref}")
    mode = header[0].decode("ascii", errors="strict")
    object_type = header[1].decode("ascii", errors="strict")
    object_id = header[2].decode("ascii", errors="strict")
    size_text = header[3]
    try:
        size = None if size_text == b"-" else int(size_text)
    except ValueError as exc:
        raise SentinelError(f"invalid Git object size for {evidence_path(relative)} at {ref}") from exc
    return mode, object_type, object_id, size


def load_policy(
    repo: Path,
    config: str | None,
    enforcement: str | None,
    context: dict[str, Any],
    require_config: bool = False,
) -> tuple[dict[str, Any], str, str | None, bool]:
    if enforcement not in {None, "audit"}:
        raise SentinelError("Sentinel v1 is audit-only")
    policy = dict(DEFAULT_POLICY)
    policy_source = "embedded:baseline"
    config_relative: str | None = None
    bootstrap = False
    provided: dict[str, Any] | None = None
    if config:
        candidate = Path(config)
        if candidate.is_absolute():
            if context["event_name"] != "local":
                raise SentinelError("absolute policy paths are allowed only for local audits")
            if candidate.exists():
                provided = load_json(candidate)
                policy_source = f"working-tree:{candidate}"
            elif require_config:
                raise SentinelError(f"required policy does not exist: {candidate}")
        else:
            config_relative = posixpath.normpath(candidate.as_posix())
            if config_relative in {"", ".", ".."} or config_relative.startswith("../"):
                raise SentinelError("policy path must stay inside the repository")
            if context["is_pull_request"] and context["base"]:
                data, _ = git_blob(repo, context["base"], config_relative)
                if data is not None:
                    provided = parse_json_bytes(data, f"{context['base']}:{config_relative}")
                    policy_source = f"git:{context['base']}:{config_relative}"
                else:
                    head_data, _ = git_blob(repo, context["head"], config_relative)
                    if head_data is not None:
                        bootstrap = True
                        policy_source = "embedded:bootstrap"
                    elif require_config:
                        raise SentinelError(f"required policy is absent from base and head: {config_relative}")
            elif context["source_ref"]:
                data, _ = git_blob(repo, context["head"], config_relative)
                if data is not None:
                    provided = parse_json_bytes(data, f"{context['head']}:{config_relative}")
                    policy_source = f"git:{context['head']}:{config_relative}"
                elif require_config:
                    raise SentinelError(f"required policy does not exist at head: {config_relative}")
            else:
                config_path = repo / config_relative
                try:
                    config_path.resolve().relative_to(repo)
                except ValueError as exc:
                    raise SentinelError("relative policy path must resolve inside the repository") from exc
                if config_path.is_symlink():
                    raise SentinelError("relative policy path must not be a symbolic link")
                if config_path.exists():
                    provided = load_json(config_path)
                    policy_source = f"working-tree:{config_path}"
                elif require_config:
                    raise SentinelError(f"required policy does not exist: {config_path}")
        if provided is not None:
            validate_policy_document(provided)
            for key in ("schema", "profile", "max_file_bytes", "sensitive_globs", "required_evidence"):
                if key in provided:
                    policy[key] = provided[key]
    for key in ("sensitive_globs", "required_evidence"):
        value = policy.get(key)
        policy[key] = sorted(set(value))
    return policy, policy_source, config_relative, bootstrap


def event_context(
    repo: Path,
    base: str | None,
    head: str | None,
    event_path: str | None,
    repository_identity: str | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {}
    path_text = event_path or os.getenv("GITHUB_EVENT_PATH")
    if path_text:
        event_file = Path(path_text)
        if not event_file.exists():
            raise SentinelError(f"event payload does not exist: {event_file}")
        event = load_json(event_file)
    pull = event.get("pull_request") if isinstance(event.get("pull_request"), dict) else {}
    pull_base = pull.get("base", {})
    pull_head = pull.get("head", {})
    if pull and (not isinstance(pull_base, dict) or not isinstance(pull_head, dict)):
        raise SentinelError("pull-request base and head must be objects")
    base_sha = base or pull_base.get("sha") or event.get("before")
    head_sha = head or pull_head.get("sha") or event.get("after") or os.getenv("GITHUB_SHA")
    if base_sha is not None and not isinstance(base_sha, str):
        raise SentinelError("base commit ref must be a string or null")
    if head_sha is not None and not isinstance(head_sha, str):
        raise SentinelError("head commit ref must be a string or null")
    zero = "0" * 40
    if base_sha == zero:
        base_sha = None
    if not head_sha:
        head_sha = "HEAD"
    event_name = os.getenv("GITHUB_EVENT_NAME") or ("pull_request" if pull else "local")
    if repository_identity is not None:
        if event_name != "local" or event_path or base is not None or head is not None:
            raise SentinelError("explicit repository identity is allowed only for a local working-tree audit")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", repository_identity):
            raise SentinelError("repository identity must be a canonical owner/repository pair")
        if any(component in {".", ".."} for component in repository_identity.split("/")):
            raise SentinelError("repository identity contains a reserved path component")
    if pull and not base_sha:
        raise SentinelError("pull-request event is missing a base commit")
    base_resolved = resolve_commit(repo, base_sha)
    head_resolved = resolve_commit(repo, head_sha)
    source_ref = head_resolved if event_name != "local" or base is not None or head is not None else None
    body = pull.get("body") or ""
    if not isinstance(body, str):
        raise SentinelError("pull-request body must be a string or null")
    pull_request_number = pull.get("number") or event.get("number")
    if pull_request_number is not None and type(pull_request_number) is not int:
        raise SentinelError("pull-request number must be an integer or null")
    return {
        "event_name": event_name,
        "is_pull_request": bool(pull),
        "base": base_resolved,
        "head": head_resolved,
        "source_ref": source_ref,
        "repository": repository_identity or os.getenv("GITHUB_REPOSITORY") or evidence_path(repo.name),
        "pull_request_number": pull_request_number,
        "pull_request_body": body,
    }


def changed_paths(
    repo: Path,
    base: str | None,
    head: str,
    source_ref: str | None,
    scope: str,
) -> tuple[list[str], str]:
    if base:
        result = git_bytes(repo, "diff", "--no-ext-diff", "--name-only", "--no-renames", "-z", "--diff-filter=ACMRTUXBD", f"{base}...{head}")
        if result.returncode != 0:
            raise SentinelError(f"cannot compute exact diff scope {base}...{head}: {result.stderr.decode('utf-8', errors='replace').strip()}")
        return sorted(git_path(path) for path in result.stdout.split(b"\0") if path), "merge-base-diff"
    if source_ref:
        result = git_bytes(repo, "ls-tree", "-r", "--name-only", "-z", source_ref)
        if result.returncode != 0:
            raise SentinelError(f"cannot enumerate tree {source_ref}: {result.stderr.decode('utf-8', errors='replace').strip()}")
        return sorted(git_path(path) for path in result.stdout.split(b"\0") if path), "full-git-tree"
    if scope != "full":
        unstaged = git_bytes(repo, "diff", "--no-ext-diff", "--name-only", "--no-renames", "-z", "--diff-filter=ACMRTUXBD")
        staged = git_bytes(repo, "diff", "--no-ext-diff", "--cached", "--name-only", "--no-renames", "-z", "--diff-filter=ACMRTUXBD")
        untracked = git_bytes(repo, "ls-files", "--others", "--exclude-standard", "-z")
        if any(result.returncode != 0 for result in (unstaged, staged, untracked)):
            raise SentinelError("cannot compute local working-tree change scope")
        paths = {
            git_path(path)
            for result in (unstaged, staged, untracked)
            for path in result.stdout.split(b"\0")
            if path
        }
        return sorted(paths), "working-tree-changes"
    tracked_result = git_bytes(repo, "ls-files", "-z")
    untracked_result = git_bytes(repo, "ls-files", "--others", "--exclude-standard", "-z")
    if tracked_result.returncode != 0 or untracked_result.returncode != 0:
        raise SentinelError("cannot enumerate full local working tree")
    tracked = (git_path(path) for path in tracked_result.stdout.split(b"\0") if path)
    untracked = (git_path(path) for path in untracked_result.stdout.split(b"\0") if path)
    return sorted({path for path in (*tracked, *untracked) if path}), "full-working-tree"


def hash_file(path: Path) -> tuple[str, int]:
    value = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            value.update(chunk)
            size += len(chunk)
    return value.hexdigest(), size


def capture_candidate(repo: Path, relative: str, source_ref: str | None, max_bytes: int) -> dict[str, Any]:
    item: dict[str, Any] = {"path": relative, "evidence_path": evidence_path(relative)}
    if source_ref:
        info = git_object_info(repo, source_ref, relative)
        if info is None:
            return {**item, "state": "missing"}
        mode, object_type, object_id, size = info
        item.update({
            "state": "present", "mode": mode, "object_type": object_type,
            "git_object": object_id, "size": size,
        })
        if object_type == "blob" and size is not None and size <= max_bytes:
            data, _ = git_blob(repo, source_ref, relative)
            if data is None or len(data) != size:
                return {**item, "state": "unreadable:GitObjectSizeMismatch"}
            item["data"] = data
        return item

    path = repo / relative
    try:
        metadata = path.lstat()
        item["mode"] = format(metadata.st_mode, "o")
        item["size"] = metadata.st_size
        if stat.S_ISLNK(metadata.st_mode):
            target = os.readlink(path)
            data = os.fsencode(target)
            item.update({"state": "present", "mode": "120000", "object_type": "symlink", "data": data, "sha256": hashlib.sha256(data).hexdigest()})
        elif stat.S_ISREG(metadata.st_mode):
            item.update({"state": "present", "object_type": "blob"})
            if metadata.st_size <= max_bytes:
                data = path.read_bytes()
                if len(data) != metadata.st_size:
                    return {**item, "state": "unreadable:LocalSizeMismatch"}
                item["data"] = data
                item["sha256"] = hashlib.sha256(data).hexdigest()
            else:
                item["sha256"], captured_size = hash_file(path)
                if captured_size != metadata.st_size:
                    return {**item, "state": "unreadable:LocalSizeMismatch"}
        else:
            item.update({"state": "present", "object_type": "special"})
    except FileNotFoundError:
        item["state"] = "missing"
    except OSError as exc:
        item["state"] = f"unreadable:{type(exc).__name__}"
    return item


def capture_candidates(repo: Path, paths: Iterable[str], source_ref: str | None, max_bytes: int) -> list[dict[str, Any]]:
    return [capture_candidate(repo, relative, source_ref, max_bytes) for relative in sorted(paths)]


def candidate_manifest(entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for entry in entries:
        item = {"path": entry["evidence_path"], "state": entry["state"]}
        for key in ("mode", "object_type", "git_object", "size", "sha256"):
            if entry.get(key) is not None:
                item[key] = entry[key]
        manifest.append(item)
    return manifest


def candidate_digest(entries: Iterable[dict[str, Any]]) -> str:
    return digest(candidate_manifest(entries))


def is_workflow(path: str) -> bool:
    return path.startswith(".github/workflows/") and path.lower().endswith((".yml", ".yaml"))


def is_text(data: bytes) -> bool:
    if b"\0" in data[:8192]:
        return False
    return True


def finding(code: str, severity: str, message: str, path: str | None = None, line: int | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"code": code, "severity": severity, "message": message}
    if path:
        item["path"] = path
    if line:
        item["line"] = line
    return item


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def is_sensitive_path(relative: str) -> bool:
    lower = relative.lower()
    name = posixpath.basename(lower)
    return (
        name in {".env", ".envrc"} or name.startswith(".env.") or name.endswith(".env") or ".env." in name or
        name.endswith((".pem", ".key", ".p12", ".pfx"))
    )


def scan_captured_file(entry: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    relative = entry["path"]
    public_path = entry["evidence_path"]
    state = entry["state"]
    if state.startswith("unreadable:"):
        return [finding("SNT007", "critical", f"candidate file could not be read: {state}", public_path)]
    if state == "missing":
        return findings
    if is_sensitive_path(relative):
        findings.append(finding("SNT013", "high", "sensitive file type is tracked", public_path))
    object_type = entry.get("object_type")
    if object_type in {"commit", "special"} or entry.get("mode") == "160000":
        findings.append(finding("SNT014", "high", "gitlink, submodule, or special file requires separate bounded review", public_path))
        return findings
    size = entry.get("size")
    if isinstance(size, int) and size > int(policy["max_file_bytes"]):
        findings.append(finding("SNT005", "medium", f"changed file exceeds {policy['max_file_bytes']} bytes and was not content-scanned", public_path))
        return findings
    data = entry.get("data")
    if data is None:
        findings.append(finding("SNT007", "critical", "candidate file capture has no readable bytes", public_path))
        return findings
    if entry.get("mode") == "120000" or object_type == "symlink":
        target = data.decode("utf-8", errors="replace")
        normalized = posixpath.normpath(posixpath.join(posixpath.dirname(relative), target))
        if target.startswith("/") or normalized == ".." or normalized.startswith("../"):
            findings.append(finding("SNT006", "critical", "symlink resolves outside the repository", public_path))
        return findings
    text = data.decode("utf-8", errors="replace")
    for pattern, label in SECRET_PATTERNS:
        match = pattern.search(text)
        if match:
            findings.append(finding("SNT003", "critical", f"possible committed secret: {label}", public_path, line_of(text, match.start())))
    if not is_text(data):
        return findings
    match = CONFLICT_RE.search(text)
    if match:
        findings.append(finding("SNT001", "critical", "unresolved merge-conflict marker", public_path, line_of(text, match.start())))
    for char in sorted(BIDI_CONTROLS):
        offset = text.find(char)
        if offset >= 0:
            findings.append(finding("SNT002", "high", "bidirectional Unicode control character", public_path, line_of(text, offset)))
            break
    shell_text = re.sub(r"\\\r?\n", " ", text)
    for pattern, label in DANGEROUS_PATTERNS:
        match = pattern.search(shell_text)
        if match:
            findings.append(finding("SNT004", "high", label, public_path, line_of(shell_text, match.start())))
    if is_workflow(relative):
        fallback_required = False
        for match in USES_RE.finditer(text):
            target = match.group(1).strip("'\"")
            if target.startswith("./"):
                continue
            if target.startswith("docker://"):
                if not re.search(r"@sha256:[0-9a-fA-F]{64}$", target):
                    findings.append(finding("SNT010", "high", f"container action is not pinned to a SHA-256 digest: {target}", public_path, line_of(text, match.start())))
                continue
            ref = target.rsplit("@", 1)[1] if "@" in target else ""
            if not re.fullmatch(r"[0-9a-fA-F]{40}", ref):
                findings.append(finding("SNT010", "high", f"third-party action is not pinned to a full commit SHA: {target}", public_path, line_of(text, match.start())))
        for match in WRITE_PERMISSION_RE.finditer(text):
            findings.append(finding("SNT011", "high", f"workflow requests write permission: {match.group(0).strip()}", public_path, line_of(text, match.start())))
        for match in INLINE_WRITE_PERMISSION_RE.finditer(text):
            findings.append(finding("SNT011", "high", f"workflow requests inline write permission: {match.group(0).strip()}", public_path, line_of(text, match.start())))
        for match in PERMISSIONS_LINE_RE.finditer(text):
            value = match.group(1).strip().strip("'\"")
            if value and value not in {"read-all", "{}"} and not SAFE_PERMISSION_VALUE_RE.fullmatch(value):
                fallback_required = True
        for match in PERMISSION_ENTRY_RE.finditer(text):
            if not SAFE_PERMISSION_VALUE_RE.fullmatch(match.group(1).strip()) and not WRITE_PERMISSION_RE.fullmatch(match.group(0)):
                fallback_required = True
        for match in WORKFLOW_KEY_RE.finditer(text):
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_end = text.find("\n", match.end())
            line = text[line_start:] if line_end < 0 else text[line_start:line_end]
            if match.group(1).lower() == "uses" and not USES_RE.search(line):
                fallback_required = True
            if match.group(1).lower() == "permissions" and ("\"permissions\"" in line or "'permissions'" in line):
                fallback_required = True
        if fallback_required:
            findings.append(finding("SNT015", "high", "workflow contains action or permission syntax not safely parsed; manual review required", public_path))
        if PRIVILEGED_TRIGGER_RE.search(text) and re.search(r"\bcheckout\b", text):
            findings.append(finding("SNT012", "critical", "privileged workflow trigger combined with checkout requires manual threat review", public_path))
    return findings


def matches_glob(path: str, pattern: str) -> bool:
    path_lower = path.lower()
    pattern_lower = pattern.lower()
    if fnmatch.fnmatch(path_lower, pattern_lower):
        return True
    return pattern_lower.startswith("**/") and fnmatch.fnmatch(path_lower, pattern_lower[3:])


def heading_key(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def markdown_evidence_sections(body: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    active: str | None = None
    for line in body.splitlines():
        match = MARKDOWN_HEADING_RE.match(line)
        if match:
            active = heading_key(match.group(1))
            sections.setdefault(active, [])
        elif active is not None:
            sections[active].append(line)
    return {key: "\n".join(lines).strip() for key, lines in sections.items()}


def evidence_section_is_nonempty(value: str) -> bool:
    visible = re.sub(r"<!--[\s\S]*?-->", "", value).strip()
    return bool(visible) and not EMPTY_EVIDENCE_RE.fullmatch(visible)


def evidence_findings(paths: list[str], policy: dict[str, Any], body: str, local: bool = False) -> list[dict[str, Any]]:
    sensitive = sorted({path for path in paths if any(matches_glob(path, pattern) for pattern in policy["sensitive_globs"])})
    if not sensitive or not policy["required_evidence"]:
        return []
    if local:
        return [finding(
            "SNT020",
            "medium",
            "sensitive local change requires independent review evidence unavailable to the local observer",
            evidence_path(sensitive[0]),
        )]
    sections = markdown_evidence_sections(body)
    missing = [
        heading for heading in policy["required_evidence"]
        if not evidence_section_is_nonempty(sections.get(heading_key(heading), ""))
    ]
    if not missing:
        return []
    return [finding(
        "SNT020",
        "medium",
        "sensitive-path change is missing nonempty Markdown evidence sections: " + ", ".join(missing),
        evidence_path(sensitive[0]),
    )]


def diff_check(repo: Path, base: str | None, head: str) -> list[dict[str, Any]]:
    if not base:
        return []
    result = git(repo, "diff", "--no-ext-diff", "--check", f"{base}...{head}", check=False)
    if result.returncode == 0:
        return []
    message = safe_text(result.stdout.strip().splitlines()[0]) if result.stdout.strip() else "git diff --check failed"
    return [finding("SNT021", "medium", message)]


def markdown_inline(value: Any) -> str:
    value_text = str(value).replace("\r", " ").replace("\n", " ")
    escaped = html.escape(value_text, quote=True).replace("`", "&#96;")
    return escaped.translate(str.maketrans({"[": "&#91;", "]": "&#93;", "(": "&#40;", ")": "&#41;"}))


def markdown_report(receipt: dict[str, Any]) -> str:
    counts = receipt["summary"]["by_severity"]
    lines = [
        "# TrueNorth Federation Sentinel review",
        "",
        f"- Review status: `{markdown_inline(receipt['review_status'])}`",
        f"- Authority: `{receipt['authority']}`",
        f"- Profile: `{markdown_inline(receipt['subject']['profile'])}`",
        f"- Head: `{receipt['subject']['head']}`",
        f"- Source: `{receipt['subject']['source_mode']}` / `{receipt['subject']['scope_mode']}`",
        f"- Candidate digest: `{receipt['subject']['candidate_digest']}`",
        f"- Evidence digest: `{receipt['evidence_digest']}`",
        f"- Findings: critical {counts['critical']}, high {counts['high']}, medium {counts['medium']}, low {counts['low']}",
        "",
        "Federation Sentinel is an observer. This evidence is not approval, authorization, merge permission, or proof of production correctness.",
        "",
        "## Findings",
        "",
    ]
    if not receipt["findings"]:
        lines.append("No deterministic findings in the inspected scope.")
    else:
        for item in receipt["findings"]:
            location = markdown_inline(item.get("path", "repository"))
            if item.get("line"):
                location += f":{item['line']}"
            lines.append(f"- **{item['severity'].upper()} {item['code']}** — `{location}` — {markdown_inline(item['message'])}")
    lines.extend(["", f"Policy digest: `{receipt['engine']['policy_digest']}`", ""])
    return "\n".join(lines)


def output_path(value: str, repo: Path) -> Path:
    path = Path(value).expanduser().resolve()
    try:
        path.relative_to(repo)
    except ValueError:
        return path
    raise SentinelError(f"review evidence must be written outside the audited checkout: {path}")


def atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def audit(args: argparse.Namespace) -> int:
    os.umask(0o077)
    repo = Path(args.repo).expanduser().resolve()
    if not (repo / ".git").exists():
        raise SentinelError(f"not a Git checkout: {repo}")
    require_canonical_worktree(repo)
    context = event_context(
        repo, args.base, args.head, args.event_path, getattr(args, "repository_identity", None)
    )
    status_start = git_status(repo)
    checkout_head_start = resolve_commit(repo, "HEAD")
    if os.getenv("GITHUB_ACTIONS", "").lower() == "true":
        if checkout_head_start != context["head"]:
            raise SentinelError(f"GitHub checkout {checkout_head_start} does not match event head {context['head']}")
        if status_start:
            raise SentinelError("GitHub checkout is dirty before Sentinel inspection")
    policy, policy_source, config_relative, bootstrap = load_policy(
        repo, args.config, args.enforcement, context, args.require_config
    )
    paths, scope_mode = changed_paths(repo, context["base"], context["head"], context["source_ref"], args.scope)
    entries = capture_candidates(repo, paths, context["source_ref"], int(policy["max_file_bytes"]))
    findings: list[dict[str, Any]] = []
    for entry in entries:
        findings.extend(scan_captured_file(entry, policy))
    findings.extend(diff_check(repo, context["base"], context["head"]))
    if context["is_pull_request"]:
        findings.extend(evidence_findings(paths, policy, context["pull_request_body"]))
    elif context["source_ref"] is None:
        findings.extend(evidence_findings(paths, policy, "", local=True))
    if config_relative and config_relative in paths:
        findings.append(finding("SNT022", "critical", "Sentinel policy changed; independent policy review is required", evidence_path(config_relative)))
    if bootstrap:
        findings.append(finding(
            "SNT024", "medium",
            "BOOTSTRAP_REVIEW_REQUIRED: base has no Sentinel policy; embedded hygiene policy was used",
            evidence_path(config_relative) if config_relative else None,
        ))

    candidate_digest_value = candidate_digest(entries)
    status_end = git_status(repo)
    checkout_head_end = resolve_commit(repo, "HEAD")
    snapshot_stable = checkout_head_start == checkout_head_end and status_start == status_end
    end_capture_complete = True
    if context["source_ref"] is None:
        end_paths, _ = changed_paths(repo, context["base"], context["head"], context["source_ref"], args.scope)
        end_entries = capture_candidates(repo, end_paths, context["source_ref"], int(policy["max_file_bytes"]))
        end_capture_complete = all(not entry["state"].startswith("unreadable:") for entry in end_entries)
        snapshot_stable = snapshot_stable and paths == end_paths and candidate_manifest(entries) == candidate_manifest(end_entries)
    elif os.getenv("GITHUB_ACTIONS", "").lower() == "true":
        snapshot_stable = snapshot_stable and not status_end
    capture_complete = (
        all(not entry["state"].startswith("unreadable:") for entry in entries)
        and end_capture_complete
    )
    completion_status = "complete" if snapshot_stable and capture_complete else "incomplete"
    if completion_status == "incomplete":
        findings.append(finding(
            "SNT090", "critical",
            "candidate snapshot changed during inspection or could not be captured coherently; no clean conclusion is available",
        ))

    findings.sort(key=lambda item: (-SEVERITY_ORDER[item["severity"]], item.get("path", ""), item["code"]))
    counts = {severity: sum(1 for item in findings if item["severity"] == severity) for severity in SEVERITY_ORDER}
    review_status = "INCOMPLETE" if completion_status == "incomplete" else ("NO_FINDINGS" if not findings else "REVIEW_REQUIRED")
    deleted_paths = [entry["evidence_path"] for entry in entries if entry["state"] == "missing"]
    body_digest = hashlib.sha256(context["pull_request_body"].encode("utf-8")).hexdigest() if context["is_pull_request"] else None
    receipt: dict[str, Any] = {
        "schema": REVIEW_EVIDENCE_SCHEMA,
        "generated_at": utc_now(),
        "authority": "none",
        "effect_authorized": False,
        "promotion_authorized": False,
        "completion_status": completion_status,
        "review_status": review_status,
        "subject": {
            "repository": context["repository"],
            "base": context["base"],
            "head": context["head"],
            "event": context["event_name"],
            "pull_request_number": context["pull_request_number"],
            "pull_request_body_digest": body_digest,
            "profile": policy["profile"],
            "inspected_paths": [entry["evidence_path"] for entry in entries],
            "deleted_paths": deleted_paths,
            "scope_mode": scope_mode,
            "source_mode": "git-object" if context["source_ref"] else "working-tree",
            "path_encoding": "percent-encoded-bytes-v1",
            "snapshot_stable": snapshot_stable,
            "candidate_digest": candidate_digest_value,
        },
        "engine": {
            "name": "truenorth-federation-sentinel",
            "version": VERSION,
            "source_digest": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "policy_digest": digest(policy),
        },
        "summary": {"finding_count": len(findings), "by_severity": counts},
        "findings": findings,
        "nonclaims": [
            "A clean audit does not prove correctness or safety.",
            "Required-evidence checks establish exact nonempty section presence, not the factual adequacy of those sections.",
            "Workflow pattern checks are conservative and incomplete; they do not prove workflow safety.",
            "This evidence does not authorize an effect, merge, deployment, promotion, or memory write.",
            "Federation Sentinel does not replace repository-native tests, independent review, source ownership, or final-state verification.",
        ],
        "diagnostics": {
            "policy_source": policy_source,
            "working_tree_dirty": bool(status_start),
            "working_tree_status_digest": hashlib.sha256(status_start).hexdigest(),
            "working_tree_end_status_digest": hashlib.sha256(status_end).hexdigest(),
            "checkout_head_at_end": checkout_head_end,
            "snapshot_stable": snapshot_stable,
        },
    }
    receipt["evidence_digest"] = digest({
        key: value for key, value in receipt.items() if key not in {"generated_at", "diagnostics", "evidence_digest"}
    })
    receipt_path = output_path(args.evidence, repo)
    report_path = output_path(args.report, repo)
    atomic_write(receipt_path, json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=True) + "\n")
    atomic_write(report_path, markdown_report(receipt))
    print(f"Federation Sentinel: {review_status}; {len(findings)} finding(s)")
    return 3 if completion_status == "incomplete" else 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    command = sub.add_parser("audit", help="audit a Git checkout")
    command.add_argument("--repo", default=".")
    command.add_argument("--config")
    command.add_argument("--require-config", action="store_true")
    command.add_argument("--enforcement", choices=("audit",), help="compatibility flag; Sentinel v1 is audit-only")
    command.add_argument("--base")
    command.add_argument("--head")
    command.add_argument("--event-path")
    command.add_argument(
        "--repository-identity",
        help="canonical owner/repository identity for a local working-tree audit",
    )
    command.add_argument("--scope", choices=("auto", "full", "changes"), default="auto")
    command.add_argument("--evidence", required=True)
    command.add_argument("--report", required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "audit":
            return audit(args)
    except SentinelError as exc:
        print(f"Sentinel error: {exc}", file=sys.stderr)
        return 3
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
