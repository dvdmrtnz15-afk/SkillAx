#!/bin/bash
set -euo pipefail
umask 077

usage() {
  cat <<'EOF'
Usage: install-macos-launchagent.sh --registry /absolute/repos.v1.json [--interval seconds] [--load --expected-bundle-id 64hex] [--replace]

Stages a private, content-addressed TrueNorth Federation Sentinel bundle for an
explicit repository registry. The default local audit scope is full. The worker
never discovers broad roots, fetches, tests, commits, pushes, comments, merges,
deploys, grants authority, or executes product effects.

Without --load, nothing is written to ~/Library/LaunchAgents. Loading requires
the exact staged bundle ID to close the review-to-activation gap. --replace may
replace only an inactive, validated plist for the exact Sentinel label; unload
an already-running service separately before replacement.
EOF
}

fail() {
  printf '%s\n' "$1" >&2
  exit "${2:-2}"
}

registry=""
interval="21600"
load_agent="false"
replace_agent="false"
expected_bundle_id=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --registry)
      [[ $# -ge 2 && -n "$2" ]] || fail "--registry requires an absolute JSON path."
      registry="$2"
      shift 2
      ;;
    --interval)
      [[ $# -ge 2 && -n "$2" ]] || fail "--interval requires a decimal number of seconds."
      interval="$2"
      shift 2
      ;;
    --load)
      load_agent="true"
      shift
      ;;
    --expected-bundle-id)
      [[ $# -ge 2 && -n "$2" ]] || fail "--expected-bundle-id requires a lowercase 64-character SHA-256 value."
      expected_bundle_id="$2"
      shift 2
      ;;
    --replace)
      replace_agent="true"
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      usage >&2
      fail "Unknown option: $1"
      ;;
  esac
done

[[ "$(/usr/bin/uname -s)" == "Darwin" ]] || fail "This installer is for macOS."
[[ "$(/usr/bin/id -u)" != "0" ]] || fail "Do not run this per-user LaunchAgent installer with sudo or as root."
[[ -n "$registry" && "$registry" == /* && -f "$registry" ]] || fail "--registry must name an existing absolute JSON file."
[[ -n "${HOME:-}" && "$HOME" == /* && -d "$HOME" ]] || fail "HOME must be an existing absolute directory."
if [[ "$replace_agent" == "true" && "$load_agent" != "true" ]]; then
  fail "--replace requires --load."
fi
if [[ "$load_agent" == "true" && ! "$expected_bundle_id" =~ ^[0-9a-f]{64}$ ]]; then
  fail "--load requires --expected-bundle-id with the reviewed lowercase 64-character bundle ID."
fi
if [[ "$load_agent" != "true" && -n "$expected_bundle_id" ]]; then
  fail "--expected-bundle-id is accepted only with --load."
fi
if [[ "$load_agent" == "true" ]]; then
  fail "--load is disabled in this audit-only candidate pending durable activation reconciliation and linked-Mac lifecycle/TCC validation." 3
fi

python_candidate="$(command -v python3 || true)"
[[ -n "$python_candidate" ]] || fail "A reviewed Python 3.10 or newer interpreter is required."
if ! "$python_candidate" -I -X utf8 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  fail "A reviewed Python 3.10 or newer interpreter is required."
fi

script_dir="$(cd "$(dirname "$0")" && pwd)"
installer_path="$script_dir/$(basename "$0")"
engine_path="$(cd "$script_dir/../sentinel" && pwd)/sentinel.py"
runner_path="$(cd "$script_dir/../sentinel" && pwd)/macos_runner.py"

TN_REGISTRY="$registry" \
TN_INTERVAL="$interval" \
TN_LOAD="$load_agent" \
TN_REPLACE="$replace_agent" \
TN_EXPECTED_BUNDLE_ID="$expected_bundle_id" \
TN_HOME="$HOME" \
TN_INSTALLER_PATH="$installer_path" \
TN_ENGINE_PATH="$engine_path" \
TN_RUNNER_PATH="$runner_path" \
"$python_candidate" -I -X utf8 - <<'PY'
from __future__ import annotations

import datetime as dt
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid

BUNDLE_SCHEMA = "truenorth.federation-sentinel.bundle.v1"
REGISTRY_SCHEMA = "truenorth.federation-sentinel.local-repos.v1"
RUN_SCHEMA = "truenorth.federation-sentinel.local-run.v1"
EVIDENCE_SCHEMA = "truenorth.sentinel.review-evidence.v1"
LABEL = "com.truenorthapplications.federation-sentinel"
MIN_INTERVAL = 300
MAX_INTERVAL = 604800
MAX_REPOSITORIES = 128
EXPECTED_NONCLAIMS = [
    "A clean audit does not prove correctness or safety.",
    "Required-evidence checks establish exact nonempty section presence, not the factual adequacy of those sections.",
    "Workflow pattern checks are conservative and incomplete; they do not prove workflow safety.",
    "This evidence does not authorize an effect, merge, deployment, promotion, or memory write.",
    "Federation Sentinel does not replace repository-native tests, independent review, source ownership, or final-state verification.",
]
HEX64 = re.compile(r"[0-9a-f]{64}")
HEX40 = re.compile(r"[0-9a-f]{40}")
REPO_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}")
HTTPS_REMOTE = re.compile(r"https://github\.com/([A-Za-z0-9_.-]{1,100})/([A-Za-z0-9_.-]{1,100}?)(?:\.git)?")
SSH_REMOTE = re.compile(r"git@github\.com:([A-Za-z0-9_.-]{1,100})/([A-Za-z0-9_.-]{1,100}?)(?:\.git)?")


class InstallError(RuntimeError):
    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


def stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_value(value: object) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_regular_source(path: Path, label: str) -> bytes:
    try:
        info = path.lstat()
    except OSError as exc:
        raise InstallError(f"Cannot read {label}: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise InstallError(f"{label} must be a regular, non-symlink file: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise InstallError(f"Cannot read {label}: {exc}") from exc


def ensure_directory(path: Path, owner: int, mode: int | None = None) -> None:
    if path.exists() or path.is_symlink():
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise InstallError(f"Refusing non-directory or symlink path: {path}")
        if info.st_uid != owner:
            raise InstallError(f"Directory is not owned by the current user: {path}")
    else:
        path.mkdir(mode=mode or 0o700)
    if mode is not None:
        os.chmod(path, mode)


def ensure_home_tree(home: Path, owner: int) -> dict[str, Path]:
    library = home / "Library"
    ensure_directory(library, owner)
    application_support = library / "Application Support"
    ensure_directory(application_support, owner)
    true_north_support = application_support / "TrueNorth"
    ensure_directory(true_north_support, owner, 0o700)
    root = true_north_support / "FederationSentinel"
    ensure_directory(root, owner, 0o700)
    releases = root / "releases"
    state = root / "state"
    evidence = root / "evidence"
    ensure_directory(releases, owner, 0o700)
    ensure_directory(state, owner, 0o700)
    ensure_directory(evidence, owner, 0o700)
    logs_parent = library / "Logs"
    ensure_directory(logs_parent, owner)
    true_north_logs = logs_parent / "TrueNorth"
    ensure_directory(true_north_logs, owner, 0o700)
    logs = true_north_logs / "FederationSentinel"
    ensure_directory(logs, owner, 0o700)
    return {"root": root, "releases": releases, "state": state, "evidence": evidence, "logs": logs, "library": library}


def write_exclusive(path: Path, data: bytes, mode: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, mode)
    try:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
        os.fchmod(descriptor, mode)
    finally:
        os.close(descriptor)


def atomic_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        write_exclusive(temporary, data, mode)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def write_json_atomic(path: Path, value: dict[str, object], mode: int = 0o600) -> None:
    atomic_write(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"), mode)


def normalize_remote(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("remote must be a string")
    match = HTTPS_REMOTE.fullmatch(value) or SSH_REMOTE.fullmatch(value)
    if not match:
        raise ValueError("remote must be a canonical GitHub HTTPS or SSH repository URL")
    owner, repository = match.groups()
    return f"github.com/{owner.casefold()}/{repository.casefold()}"


def git_environment(home: Path) -> dict[str, str]:
    return {
        "HOME": str(home), "LANG": "C", "LC_ALL": "C",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_OPTIONAL_LOCKS": "0", "GIT_EXTERNAL_DIFF": "",
        "GIT_LITERAL_PATHSPECS": "1", "GIT_NO_REPLACE_OBJECTS": "1",
    }


def git_command(repo: Path, environment: dict[str, str], *arguments: str, timeout: int = 15) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["/usr/bin/git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "submodule.recurse=false", "-C", str(repo), *arguments],
            text=True, encoding="utf-8", errors="strict", stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=environment, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        raise InstallError(f"Git inspection failed for {repo}: {type(exc).__name__}") from exc


def raw_origin(repo: Path, environment: dict[str, str]) -> str:
    result = git_command(
        repo,
        environment,
        "config",
        "--local",
        "--no-includes",
        "--get-all",
        "remote.origin.url",
    )
    values = result.stdout.splitlines() if result.returncode == 0 else []
    if len(values) != 1 or not values[0]:
        raise InstallError(f"Repository {repo} must have exactly one raw local origin URL.")
    return values[0]


def require_canonical_worktree(repo: Path, environment: dict[str, str]) -> None:
    inside = git_command(repo, environment, "rev-parse", "--is-inside-work-tree")
    top = git_command(
        repo,
        environment,
        "rev-parse",
        "--path-format=absolute",
        "--show-toplevel",
    )
    git_dir = git_command(repo, environment, "rev-parse", "--absolute-git-dir")
    if inside.returncode != 0 or inside.stdout.strip() != "true" or top.returncode != 0 or git_dir.returncode != 0:
        raise InstallError(f"Repository {repo} is not a canonical Git working tree.")
    try:
        canonical_top = Path(top.stdout.strip()).resolve(strict=True)
        canonical_git_dir = Path(git_dir.stdout.strip()).resolve(strict=True)
    except OSError as exc:
        raise InstallError(f"Repository {repo} Git identity cannot be resolved.") from exc
    if canonical_top != repo or not canonical_git_dir.is_dir():
        raise InstallError(f"Repository {repo} path does not equal Git's canonical working-tree root.")


def validate_registry(
    registry_bytes: bytes,
    home: Path,
    protected_roots: tuple[Path, ...],
) -> tuple[list[dict[str, object]], dict[str, bytes]]:
    try:
        value = json.loads(registry_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InstallError(f"Invalid registry JSON: {exc}") from exc
    if not isinstance(value, dict) or set(value) != {"schema", "repositories"} or value.get("schema") != REGISTRY_SCHEMA:
        raise InstallError("Registry must contain only schema and repositories using the v1 schema.")
    repositories = value.get("repositories")
    if not isinstance(repositories, list) or not 1 <= len(repositories) <= MAX_REPOSITORIES:
        raise InstallError(f"Registry must contain 1-{MAX_REPOSITORIES} repositories.")
    environment = git_environment(home)
    forbidden = {Path("/"), home, Path("/Users"), Path("/System"), Path("/Library"), Path("/Volumes")}
    allowed_keys = {"id", "path", "expected_remote", "policy_sha256", "scope"}
    seen_ids: set[str] = set()
    seen_paths: set[Path] = set()
    normalized: list[dict[str, object]] = []
    policies: dict[str, bytes] = {}
    for entry in repositories:
        if not isinstance(entry, dict) or not set(entry).issubset(allowed_keys):
            raise InstallError("Each registry entry must contain only id, path, expected_remote, policy_sha256, and optional scope.")
        if not {"id", "path", "expected_remote", "policy_sha256"}.issubset(entry):
            raise InstallError("Each registry entry requires id, path, expected_remote, and policy_sha256.")
        repo_id = entry.get("id")
        raw_path = entry.get("path")
        expected_remote = entry.get("expected_remote")
        policy_sha = entry.get("policy_sha256")
        scope = entry.get("scope", "full")
        if (
            not isinstance(repo_id, str)
            or not REPO_ID.fullmatch(repo_id)
            or repo_id == "_fleet"
            or repo_id.casefold() in seen_ids
        ):
            raise InstallError(f"Invalid or duplicate repository id: {repo_id!r}")
        if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
            raise InstallError(f"Repository {repo_id} path must be absolute.")
        raw = Path(raw_path)
        if raw.is_symlink():
            raise InstallError(f"Repository {repo_id} path must not be a symlink.")
        try:
            path = raw.resolve(strict=True)
        except OSError as exc:
            raise InstallError(f"Repository {repo_id} path cannot be resolved: {exc}") from exc
        overlaps_protected = any(
            path == protected or protected in path.parents or path in protected.parents
            for protected in protected_roots
        )
        if path in forbidden or path.parent == Path("/") or overlaps_protected:
            raise InstallError(f"Repository {repo_id} uses a forbidden path: {path}")
        if path in seen_paths or not path.is_dir() or not (path / ".git").exists():
            raise InstallError(f"Repository {repo_id} is duplicate or not a Git checkout: {path}")
        require_canonical_worktree(path, environment)
        try:
            canonical_expected = normalize_remote(expected_remote)
        except ValueError as exc:
            raise InstallError(f"Repository {repo_id} expected_remote is invalid: {exc}") from exc
        if not isinstance(policy_sha, str) or not HEX64.fullmatch(policy_sha) or policy_sha == "0" * 64:
            raise InstallError(f"Repository {repo_id} requires a non-placeholder lowercase policy_sha256.")
        if scope != "full":
            raise InstallError(f"Repository {repo_id} async scope must be full.")
        try:
            canonical_actual = normalize_remote(raw_origin(path, environment))
        except ValueError as exc:
            raise InstallError(f"Repository {repo_id} origin is not a canonical GitHub remote.") from exc
        if canonical_actual != canonical_expected:
            raise InstallError(f"Repository {repo_id} origin does not match expected_remote.")
        policy_path = path / ".truenorth" / "sentinel.json"
        policy_bytes = read_regular_source(policy_path, f"repository {repo_id} policy")
        try:
            policy_path.resolve(strict=True).relative_to(path)
        except (OSError, ValueError) as exc:
            raise InstallError(f"Repository {repo_id} policy escapes the checkout.") from exc
        if sha256_bytes(policy_bytes) != policy_sha:
            raise InstallError(f"Repository {repo_id} policy digest does not match registry.")
        seen_ids.add(repo_id.casefold())
        seen_paths.add(path)
        policies[repo_id] = policy_bytes
        normalized.append({
            "id": repo_id,
            "path": str(path),
            "expected_remote": expected_remote,
            "policy_sha256": policy_sha,
            "scope": scope,
        })
    normalized.sort(key=lambda item: str(item["id"]))
    return normalized, policies


def file_inventory(root: Path, include_manifest: bool = False) -> tuple[dict[str, dict[str, object]], dict[str, int], int]:
    files: dict[str, dict[str, object]] = {}
    directories: dict[str, int] = {}
    root_info = root.lstat()
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.getuid():
        raise InstallError(f"Invalid bundle root: {root}")
    for current_text, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current = Path(current_text)
        for name in list(dirnames):
            path = current / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
                raise InstallError(f"Bundle contains a non-directory entry: {path.relative_to(root)}")
            directories[str(path.relative_to(root))] = stat.S_IMODE(info.st_mode)
        for name in filenames:
            path = current / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                raise InstallError(f"Bundle contains a non-regular file: {path.relative_to(root)}")
            relative = str(path.relative_to(root))
            if relative == "bundle-manifest.json" and not include_manifest:
                continue
            files[relative] = {"sha256": sha256_bytes(path.read_bytes()), "mode": stat.S_IMODE(info.st_mode)}
    return files, directories, stat.S_IMODE(root_info.st_mode)


def strict_bundle_signature(root: Path) -> dict[str, object]:
    files, directories, root_mode = file_inventory(root, include_manifest=True)
    return {"files": files, "directories": directories, "root_mode": root_mode}


def verify_sealed_bundle(root: Path, expected_bundle_id: str, expected_identity: dict[str, object]) -> None:
    manifest_path = root / "bundle-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallError(f"Bundle manifest is unreadable: {exc}") from exc
    if set(manifest) != {"schema", "bundle_id", "identity", "files", "directories"}:
        raise InstallError("Bundle manifest has unexpected fields.")
    if manifest["schema"] != BUNDLE_SCHEMA or manifest["bundle_id"] != expected_bundle_id or root.name != expected_bundle_id:
        raise InstallError("Bundle identity does not match its content-addressed path.")
    if manifest.get("identity") != expected_identity or digest_value(expected_identity) != expected_bundle_id:
        raise InstallError("Bundle identity metadata failed verification.")
    actual_files, actual_directories, root_mode = file_inventory(root, include_manifest=True)
    manifest_info = actual_files.pop("bundle-manifest.json", None)
    if manifest_info is None or manifest_info["mode"] != 0o400:
        raise InstallError("Bundle manifest permissions are invalid.")
    if root_mode != 0o500 or actual_files != manifest["files"] or actual_directories != manifest["directories"]:
        raise InstallError("Bundle file set, digest, or permissions failed verification.")


def make_tree_writable(root: Path) -> None:
    if not root.exists() or root.is_symlink():
        return
    for current_text, dirnames, filenames in os.walk(root, topdown=False, followlinks=False):
        current = Path(current_text)
        for name in filenames:
            try:
                os.chmod(current / name, 0o600)
            except OSError:
                pass
        for name in dirnames:
            try:
                os.chmod(current / name, 0o700)
            except OSError:
                pass
        try:
            os.chmod(current, 0o700)
        except OSError:
            pass


def service_loaded(service: str) -> bool:
    result = subprocess.run(["/bin/launchctl", "print", service], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=False)
    return result.returncode == 0


def wait_for_service(service: str, expected: bool, timeout_seconds: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if service_loaded(service) is expected:
            return True
        time.sleep(0.2)
    return service_loaded(service) is expected


def launchctl(arguments: list[str], label: str) -> None:
    try:
        result = subprocess.run(["/bin/launchctl", *arguments], text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallError(f"{label}: {type(exc).__name__}", 4) from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise InstallError(f"{label}: {detail}", 4)


def activate_bundle(paths: dict[str, Path], bundle_root: Path, bundle_id: str, candidate_plist: Path, replace: bool, owner: int) -> None:
    launch_agents = paths["library"] / "LaunchAgents"
    ensure_directory(launch_agents, owner)
    if stat.S_IMODE(launch_agents.lstat().st_mode) & 0o022:
        raise InstallError("~/Library/LaunchAgents must not be group- or world-writable.", 3)
    active_plist = launch_agents / f"{LABEL}.plist"
    domain = f"gui/{owner}"
    service = f"{domain}/{LABEL}"
    was_loaded = service_loaded(service)
    if was_loaded:
        raise InstallError(
            "The Sentinel LaunchAgent is already loaded; unload and verify it is inactive before replacement.",
            3,
        )
    had_plist = active_plist.exists() or active_plist.is_symlink()
    prior_bytes = None
    prior_sha = None
    if had_plist:
        info = active_plist.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_uid != owner
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise InstallError(f"Refusing unowned, non-private, or non-regular active plist: {active_plist}", 3)
        prior_bytes = active_plist.read_bytes()
        prior_sha = sha256_bytes(prior_bytes)
        try:
            prior_plist = plistlib.loads(prior_bytes)
        except Exception as exc:
            raise InstallError("The inactive prior plist is not valid plist data.", 3) from exc
        if not isinstance(prior_plist, dict) or prior_plist.get("Label") != LABEL:
            raise InstallError("The inactive prior plist does not bind the exact Sentinel label.", 3)
        if not replace:
            raise InstallError("An inactive Sentinel plist already exists; use --load --replace after review.", 3)
    elif replace:
        raise InstallError("--replace was requested but no inactive Sentinel plist exists.", 3)
    candidate_bytes = candidate_plist.read_bytes()
    candidate_sha = sha256_bytes(candidate_bytes)
    transaction_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + f"-{bundle_id[:12]}"
    transaction_dir = paths["state"] / "activation" / transaction_id
    transaction_dir.mkdir(parents=True, mode=0o700)
    if prior_bytes is not None:
        write_exclusive(transaction_dir / "prior.plist", prior_bytes, 0o600)
    active_mutated = False
    try:
        atomic_write(active_plist, candidate_bytes, 0o600)
        active_mutated = True
        if sha256_bytes(active_plist.read_bytes()) != candidate_sha:
            raise InstallError("Active plist digest does not match the candidate.", 4)
        launchctl(["bootstrap", domain, str(active_plist)], "Unable to bootstrap the candidate LaunchAgent")
        if not wait_for_service(service, True):
            raise InstallError("Candidate LaunchAgent did not appear after bootstrap.", 4)
        receipt = {"schema": "truenorth.federation-sentinel.activation.v1", "authority": "none", "bundle_id": bundle_id, "result": "activated", "previous_loaded": False, "previous_plist_present": had_plist, "previous_plist_sha256": prior_sha, "active_plist_sha256": candidate_sha, "completed_at": utc_now()}
        write_json_atomic(transaction_dir / "activation-receipt.json", receipt)
        print("LaunchAgent loaded from the reviewed content-addressed bundle.")
        return
    except Exception as activation_error:
        rollback_errors: list[str] = []
        try:
            if service_loaded(service):
                launchctl(["bootout", service], "Unable to stop the candidate during rollback")
                if not wait_for_service(service, False):
                    raise InstallError("Candidate remained loaded during rollback.", 5)
        except Exception as exc:
            rollback_errors.append(str(exc))
        try:
            if prior_bytes is not None:
                atomic_write(active_plist, prior_bytes, 0o600)
                if sha256_bytes(active_plist.read_bytes()) != prior_sha:
                    raise InstallError("Restored inactive plist digest mismatch.", 5)
            elif active_mutated or active_plist.exists() or active_plist.is_symlink():
                try:
                    active_plist.unlink()
                except FileNotFoundError:
                    pass
        except Exception as exc:
            rollback_errors.append(str(exc))
        try:
            if service_loaded(service):
                raise InstallError("Service is still loaded after rollback.", 5)
        except Exception as exc:
            rollback_errors.append(str(exc))
        rollback_ok = not rollback_errors
        receipt = {"schema": "truenorth.federation-sentinel.activation.v1", "authority": "none", "bundle_id": bundle_id, "result": "rollback_complete" if rollback_ok else "rollback_failed", "previous_loaded": False, "previous_plist_present": had_plist, "previous_plist_sha256": prior_sha, "activation_error": str(activation_error), "rollback_errors": rollback_errors, "completed_at": utc_now()}
        write_json_atomic(transaction_dir / "activation-receipt.json", receipt)
        if rollback_ok:
            raise InstallError(f"Candidate activation failed; prior inactive plist state restored: {activation_error}", 4) from activation_error
        raise InstallError("Candidate activation failed and rollback was incomplete: " + "; ".join(rollback_errors), 5) from activation_error


def installer_main() -> int:
    os.umask(0o077)
    owner = os.getuid()
    if owner == 0:
        raise InstallError("Do not run this installer as root.")
    try:
        interval = int(os.environ["TN_INTERVAL"], 10)
    except (KeyError, ValueError) as exc:
        raise InstallError("--interval must be a decimal integer.") from exc
    if not MIN_INTERVAL <= interval <= MAX_INTERVAL:
        raise InstallError(f"--interval must be between {MIN_INTERVAL} and {MAX_INTERVAL} seconds.")
    load_agent = os.environ.get("TN_LOAD") == "true"
    replace_agent = os.environ.get("TN_REPLACE") == "true"
    expected_bundle_id = os.environ.get("TN_EXPECTED_BUNDLE_ID", "")
    if replace_agent and not load_agent:
        raise InstallError("--replace requires --load.")
    if load_agent and not HEX64.fullmatch(expected_bundle_id):
        raise InstallError("--load requires an exact reviewed lowercase bundle ID.")
    if not load_agent and expected_bundle_id:
        raise InstallError("--expected-bundle-id is accepted only with --load.")
    raw_home = Path(os.environ["TN_HOME"])
    if not raw_home.is_absolute() or raw_home.is_symlink():
        raise InstallError("HOME must be an absolute, non-symlink directory.")
    home = raw_home.resolve(strict=True)
    if not home.is_dir() or home.stat().st_uid != owner:
        raise InstallError("HOME must be owned by the current user.")
    paths = ensure_home_tree(home, owner)
    lock_path = paths["root"] / "install.lock"
    lock_flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        lock_flags |= os.O_NOFOLLOW
    lock_fd = os.open(lock_path, lock_flags, 0o600)
    lock_handle = os.fdopen(lock_fd, "a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise InstallError("Another Federation Sentinel installation is already in progress.", 3) from exc
        installer_source = Path(os.environ["TN_INSTALLER_PATH"]).resolve(strict=True)
        engine_source = Path(os.environ["TN_ENGINE_PATH"]).resolve(strict=True)
        runner_source = Path(os.environ["TN_RUNNER_PATH"]).resolve(strict=True)
        registry_input = Path(os.environ["TN_REGISTRY"])
        if registry_input.is_symlink():
            raise InstallError("--registry must not be a symlink.")
        registry_source = registry_input.resolve(strict=True)
        installer_bytes = read_regular_source(installer_source, "installer source")
        engine_bytes = read_regular_source(engine_source, "Sentinel engine")
        runner_bytes = read_regular_source(runner_source, "macOS runner")
        registry_bytes = read_regular_source(registry_source, "repository registry")
        schema_root = engine_source.parent / "schemas"
        schema_sources = {"local-repos.v1.schema.json": read_regular_source(schema_root / "local-repos.v1.schema.json", "local registry schema"), "local-run.v1.schema.json": read_regular_source(schema_root / "local-run.v1.schema.json", "local run schema"), "sentinel-review-evidence.v1.schema.json": read_regular_source(schema_root / "sentinel-review-evidence.v1.schema.json", "review evidence schema")}
        normalized_entries, policies = validate_registry(
            registry_bytes,
            home,
            (paths["root"], paths["logs"]),
        )
        normalized_registry = {"schema": REGISTRY_SCHEMA, "repositories": normalized_entries}
        normalized_registry_bytes = (json.dumps(normalized_registry, indent=2, sort_keys=True) + "\n").encode("utf-8")
        python_executable = str(Path(sys.executable).resolve(strict=True))
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        identity: dict[str, object] = {"schema": BUNDLE_SCHEMA, "engine_sha256": sha256_bytes(engine_bytes), "installer_sha256": sha256_bytes(installer_bytes), "runner_sha256": sha256_bytes(runner_bytes), "registry_source_sha256": sha256_bytes(registry_bytes), "registry_normalized_sha256": sha256_bytes(normalized_registry_bytes), "schema_sources_sha256": {name: sha256_bytes(data) for name, data in sorted(schema_sources.items())}, "interval_seconds": interval, "python_executable": python_executable, "python_version": python_version, "python_mode": ["-I", "-X", "utf8"], "platform": sys.platform, "label": LABEL, "installation_root": str(paths["root"]), "state_dir": str(paths["state"]), "evidence_dir": str(paths["evidence"]), "log_dir": str(paths["logs"]), "registry_schema": REGISTRY_SCHEMA, "run_schema": RUN_SCHEMA, "evidence_schema": EVIDENCE_SCHEMA}
        bundle_id = digest_value(identity)
        if load_agent and bundle_id != expected_bundle_id:
            raise InstallError(
                "The recomputed bundle ID differs from --expected-bundle-id; review the current inputs before activation.",
                3,
            )
        bundle_root = paths["releases"] / bundle_id
        if bundle_root.is_symlink():
            raise InstallError(f"Refusing symlinked bundle path: {bundle_root}")
        stage = Path(tempfile.mkdtemp(prefix=".stage.", dir=paths["root"]))
        stage_promoted = False
        try:
            config = stage / "config"
            policy_dir = config / "policies"
            schemas = stage / "schemas"
            config.mkdir(mode=0o700)
            policy_dir.mkdir(mode=0o700)
            schemas.mkdir(mode=0o700)
            write_exclusive(stage / "sentinel.py", engine_bytes, 0o500)
            write_exclusive(stage / "run-all.py", runner_bytes, 0o500)
            write_exclusive(config / "repos.v1.json", normalized_registry_bytes, 0o400)
            for repo_id, policy_bytes in sorted(policies.items()):
                write_exclusive(policy_dir / f"{repo_id}.json", policy_bytes, 0o400)
            for name, schema_bytes in sorted(schema_sources.items()):
                write_exclusive(schemas / name, schema_bytes, 0o400)
            manifest_path = bundle_root / "bundle-manifest.json"
            program_arguments = [python_executable, "-I", "-X", "utf8", str(bundle_root / "run-all.py"), str(bundle_root / "config" / "repos.v1.json"), str(bundle_root / "sentinel.py"), str(paths["state"]), str(paths["evidence"]), str(manifest_path), bundle_id]
            plist_payload = {"Label": LABEL, "ProgramArguments": program_arguments, "RunAtLoad": True, "StartInterval": interval, "ProcessType": "Background", "StandardOutPath": str(paths["logs"] / "launchagent.out.log"), "StandardErrorPath": str(paths["logs"] / "launchagent.err.log")}
            plist_bytes = plistlib.dumps(plist_payload, sort_keys=True)
            candidate_relative = f"{LABEL}.plist"
            write_exclusive(stage / candidate_relative, plist_bytes, 0o400)
            lint = subprocess.run(["/usr/bin/plutil", "-lint", str(stage / candidate_relative)], text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, check=False)
            if lint.returncode != 0:
                raise InstallError("Generated LaunchAgent plist failed plutil validation.")
            for directory in (policy_dir, config, schemas):
                os.chmod(directory, 0o500)
            files, directories, _ = file_inventory(stage)
            manifest = {"schema": BUNDLE_SCHEMA, "bundle_id": bundle_id, "identity": identity, "files": files, "directories": directories}
            write_exclusive(stage / "bundle-manifest.json", (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"), 0o400)
            os.chmod(stage, 0o500)
            if bundle_root.exists():
                verify_sealed_bundle(bundle_root, bundle_id, identity)
                if strict_bundle_signature(bundle_root) != strict_bundle_signature(stage):
                    raise InstallError("Existing bundle differs from the exact staged candidate.")
            else:
                try:
                    os.rename(stage, bundle_root)
                    stage_promoted = True
                except OSError as exc:
                    if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                        raise
                    verify_sealed_bundle(bundle_root, bundle_id, identity)
                    if strict_bundle_signature(bundle_root) != strict_bundle_signature(stage):
                        raise InstallError("Concurrent installer produced a different bundle.") from exc
            verify_sealed_bundle(bundle_root, bundle_id, identity)
        finally:
            if not stage_promoted and stage.exists():
                make_tree_writable(stage)
                shutil.rmtree(stage)
        candidate_plist = bundle_root / f"{LABEL}.plist"
        print("Federation Sentinel staged (authority: none).")
        print(f"Bundle ID: {bundle_id}")
        print(f"Engine SHA-256: {identity['engine_sha256']}")
        print(f"Runner SHA-256: {identity['runner_sha256']}")
        print(f"Candidate plist: {candidate_plist}")
        if load_agent:
            activate_bundle(paths, bundle_root, bundle_id, candidate_plist, replace_agent, owner)
        else:
            print("LaunchAgent not loaded; no plist was written to ~/Library/LaunchAgents.")
        return 0
    finally:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        finally:
            lock_handle.close()


try:
    raise SystemExit(installer_main())
except InstallError as exc:
    print(f"Installer error: {exc}", file=sys.stderr)
    raise SystemExit(exc.code)
PY
