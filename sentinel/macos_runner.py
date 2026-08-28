from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import signal
import stat
import subprocess
import sys
import time
from urllib.parse import quote_from_bytes
import uuid

BUNDLE_SCHEMA = "truenorth.federation-sentinel.bundle.v1"
REGISTRY_SCHEMA = "truenorth.federation-sentinel.local-repos.v1"
RUN_SCHEMA = "truenorth.federation-sentinel.local-run.v1"
EVIDENCE_SCHEMA = "truenorth.sentinel.review-evidence.v1"
LABEL = "com.truenorthapplications.federation-sentinel"
HEX64 = re.compile(r"[0-9a-f]{64}")
HEX40 = re.compile(r"[0-9a-f]{40}")
RUN_ID = re.compile(r"[0-9]{8}T[0-9]{6}\.[0-9]{6}Z-[0-9a-f]{8}")
REPO_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}")
HTTPS_REMOTE = re.compile(r"https://github\.com/([A-Za-z0-9_.-]{1,100})/([A-Za-z0-9_.-]{1,100}?)(?:\.git)?")
SSH_REMOTE = re.compile(r"git@github\.com:([A-Za-z0-9_.-]{1,100})/([A-Za-z0-9_.-]{1,100}?)(?:\.git)?")
POLICY_SCHEMA = "truenorth.sentinel.policy.v1"
REPOSITORY_TIMEOUT_SECONDS = 300
TERMINATION_GRACE_SECONDS = 5
ACTIVE_WORKER = None
TERMINATION_SIGNAL = None
EXPECTED_NONCLAIMS = [
    "A clean audit does not prove correctness or safety.",
    "Required-evidence checks establish exact nonempty section presence, not the factual adequacy of those sections.",
    "Workflow pattern checks are conservative and incomplete; they do not prove workflow safety.",
    "This evidence does not authorize an effect, merge, deployment, promotion, or memory write.",
    "Federation Sentinel does not replace repository-native tests, independent review, source ownership, or final-state verification.",
]


class Blocked(RuntimeError):
    pass


class Failed(RuntimeError):
    pass


def stable_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_value(value):
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def sha256_file(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_exclusive(path, data, mode=0o600):
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


def atomic_write(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        write_exclusive(temporary, data, mode)
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def write_json(path, value):
    atomic_write(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def inspect_tree(root):
    root_info = root.lstat()
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.getuid():
        raise Blocked("bundle_root_invalid")
    files = {}
    directories = {}
    for current_text, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current = Path(current_text)
        for name in list(dirnames):
            path = current / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
                raise Blocked(f"bundle_non_directory:{path.relative_to(root)}")
            directories[str(path.relative_to(root))] = stat.S_IMODE(info.st_mode)
        for name in filenames:
            path = current / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                raise Blocked(f"bundle_non_regular_file:{path.relative_to(root)}")
            relative = str(path.relative_to(root))
            files[relative] = {"sha256": sha256_file(path), "mode": stat.S_IMODE(info.st_mode)}
    return files, directories, stat.S_IMODE(root_info.st_mode)


def verify_bundle(manifest_path, bundle_id, registry_path, engine_path, state_root, evidence_root):
    root = manifest_path.parent
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        registry_bytes = registry_path.read_bytes()
        registry = json.loads(registry_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Blocked("bundle_contract_unreadable") from exc
    if set(manifest) != {"schema", "bundle_id", "identity", "files", "directories"}:
        raise Blocked("bundle_manifest_shape_invalid")
    if manifest["schema"] != BUNDLE_SCHEMA or manifest["bundle_id"] != bundle_id or root.name != bundle_id:
        raise Blocked("bundle_identity_mismatch")
    identity = manifest.get("identity")
    if not isinstance(identity, dict) or digest_value(identity) != bundle_id:
        raise Blocked("bundle_identity_digest_mismatch")
    if identity.get("python_executable") != str(Path(sys.executable).resolve()):
        raise Blocked("python_executable_drift")
    current_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if identity.get("python_version") != current_version:
        raise Blocked("python_version_drift")
    if identity.get("python_mode") != ["-I", "-X", "utf8"] or not sys.flags.isolated or not sys.flags.utf8_mode:
        raise Blocked("python_isolation_missing")
    if Path(identity.get("installation_root", "")) != root.parent.parent:
        raise Blocked("installation_root_mismatch")
    if registry_path != root / "config" / "repos.v1.json" or engine_path != root / "sentinel.py":
        raise Blocked("bundle_argument_path_mismatch")
    if state_root != Path(identity.get("state_dir", "")) or evidence_root != Path(identity.get("evidence_dir", "")):
        raise Blocked("runtime_state_path_mismatch")
    for runtime_path in (state_root, evidence_root):
        try:
            runtime_info = runtime_path.lstat()
        except OSError as exc:
            raise Blocked("runtime_directory_unreadable") from exc
        if (
            stat.S_ISLNK(runtime_info.st_mode)
            or not stat.S_ISDIR(runtime_info.st_mode)
            or runtime_info.st_uid != os.getuid()
            or stat.S_IMODE(runtime_info.st_mode) != 0o700
        ):
            raise Blocked("runtime_directory_invalid")

    if set(registry) != {"schema", "repositories"} or registry.get("schema") != REGISTRY_SCHEMA:
        raise Blocked("registry_shape_invalid")
    entries = registry.get("repositories")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 128:
        raise Blocked("registry_entries_invalid")
    entry_keys = {"id", "path", "expected_remote", "policy_sha256", "scope"}
    seen_ids = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != entry_keys:
            raise Blocked("registry_entry_shape_invalid")
        repo_id = entry.get("id")
        if (
            not isinstance(repo_id, str)
            or not REPO_ID.fullmatch(repo_id)
            or repo_id == "_fleet"
            or repo_id.casefold() in seen_ids
        ):
            raise Blocked("registry_repo_id_invalid")
        if not isinstance(entry.get("path"), str) or not Path(entry["path"]).is_absolute():
            raise Blocked("registry_repo_path_invalid")
        normalized_remote(entry.get("expected_remote"))
        if not isinstance(entry.get("policy_sha256"), str) or not HEX64.fullmatch(entry["policy_sha256"]):
            raise Blocked("registry_policy_digest_invalid")
        if entry.get("scope") != "full":
            raise Blocked("registry_async_scope_invalid")
        seen_ids.add(repo_id.casefold())

    actual_files, actual_directories, root_mode = inspect_tree(root)
    if root_mode != 0o500 or stat.S_IMODE(manifest_path.stat().st_mode) != 0o400:
        raise Blocked("bundle_permissions_invalid")
    expected_manifest_files = manifest.get("files")
    expected_manifest_directories = manifest.get("directories")
    if not isinstance(expected_manifest_files, dict) or not isinstance(expected_manifest_directories, dict):
        raise Blocked("bundle_inventory_invalid")
    manifest_entry = actual_files.pop("bundle-manifest.json", None)
    if manifest_entry is None or manifest_entry.get("mode") != 0o400:
        raise Blocked("bundle_manifest_missing_from_inventory")
    if actual_files != expected_manifest_files or actual_directories != expected_manifest_directories:
        raise Blocked("bundle_manifest_inventory_mismatch")

    expected_modes = {
        "sentinel.py": 0o500,
        "run-all.py": 0o500,
        "config/repos.v1.json": 0o400,
        f"{LABEL}.plist": 0o400,
        "schemas/local-repos.v1.schema.json": 0o400,
        "schemas/local-run.v1.schema.json": 0o400,
        "schemas/sentinel-review-evidence.v1.schema.json": 0o400,
    }
    for entry in entries:
        expected_modes[f"config/policies/{entry['id']}.json"] = 0o400
    if set(actual_files) != set(expected_modes):
        raise Blocked("bundle_exact_file_set_mismatch")
    if any(actual_files[path].get("mode") != mode for path, mode in expected_modes.items()):
        raise Blocked("bundle_file_mode_mismatch")
    expected_directories = {"config": 0o500, "config/policies": 0o500, "schemas": 0o500}
    if actual_directories != expected_directories:
        raise Blocked("bundle_directory_set_or_mode_mismatch")

    if actual_files["sentinel.py"]["sha256"] != identity.get("engine_sha256"):
        raise Blocked("engine_digest_mismatch")
    if actual_files["run-all.py"]["sha256"] != identity.get("runner_sha256"):
        raise Blocked("runner_digest_mismatch")
    if actual_files["config/repos.v1.json"]["sha256"] != identity.get("registry_normalized_sha256"):
        raise Blocked("registry_digest_mismatch")
    if hashlib.sha256(registry_bytes).hexdigest() != identity.get("registry_normalized_sha256"):
        raise Blocked("registry_bytes_digest_mismatch")
    schema_hashes = identity.get("schema_sources_sha256")
    if not isinstance(schema_hashes, dict) or set(schema_hashes) != {
        "local-repos.v1.schema.json",
        "local-run.v1.schema.json",
        "sentinel-review-evidence.v1.schema.json",
    }:
        raise Blocked("schema_identity_invalid")
    for name, expected_hash in schema_hashes.items():
        if actual_files[f"schemas/{name}"]["sha256"] != expected_hash:
            raise Blocked("schema_digest_mismatch")
    for entry in entries:
        if actual_files[f"config/policies/{entry['id']}.json"]["sha256"] != entry["policy_sha256"]:
            raise Blocked("policy_snapshot_digest_mismatch")

    plist_path = root / f"{LABEL}.plist"
    try:
        plist = plistlib.loads(plist_path.read_bytes())
    except Exception as exc:
        raise Blocked("bundle_plist_invalid") from exc
    expected_arguments = [
        str(Path(sys.executable).resolve()), "-I", "-X", "utf8",
        str(root / "run-all.py"), str(registry_path), str(engine_path),
        str(state_root), str(evidence_root), str(manifest_path), bundle_id,
    ]
    expected_plist = {
        "Label": LABEL,
        "ProgramArguments": expected_arguments,
        "RunAtLoad": True,
        "StartInterval": identity.get("interval_seconds"),
        "ProcessType": "Background",
        "StandardOutPath": str(Path(identity.get("log_dir", "")) / "launchagent.out.log"),
        "StandardErrorPath": str(Path(identity.get("log_dir", "")) / "launchagent.err.log"),
    }
    if plist != expected_plist:
        raise Blocked("bundle_plist_mismatch")
    return manifest, registry


def git_environment(home):
    return {"HOME": str(home), "LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_OPTIONAL_LOCKS": "0", "GIT_EXTERNAL_DIFF": "", "GIT_LITERAL_PATHSPECS": "1", "GIT_NO_REPLACE_OBJECTS": "1"}


def git(repo, environment, *arguments, timeout=30):
    try:
        result = subprocess.run(
            ["/usr/bin/git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "submodule.recurse=false", "-C", str(repo), *arguments],
            text=True, encoding="utf-8", errors="strict", stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=environment, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        raise Blocked(f"git_inspection_failed:{type(exc).__name__}") from exc
    if result.returncode != 0:
        raise Blocked(f"git_inspection_failed:{arguments[0] if arguments else 'unknown'}")
    return result.stdout


def normalized_remote(value):
    if not isinstance(value, str):
        raise Blocked("repository_origin_not_canonical_github")
    match = HTTPS_REMOTE.fullmatch(value) or SSH_REMOTE.fullmatch(value)
    if not match:
        raise Blocked("repository_origin_not_canonical_github")
    owner, repository = match.groups()
    return f"github.com/{owner.casefold()}/{repository.casefold()}"


def raw_origin(repo, environment):
    value = git(
        repo,
        environment,
        "config",
        "--local",
        "--no-includes",
        "--get-all",
        "remote.origin.url",
        timeout=15,
    )
    values = value.splitlines()
    if len(values) != 1 or not values[0]:
        raise Blocked("repository_origin_count_invalid")
    return values[0]


def repository_git_identity(repo, environment):
    inside = git(repo, environment, "rev-parse", "--is-inside-work-tree").strip()
    top = git(
        repo, environment, "rev-parse", "--path-format=absolute", "--show-toplevel"
    ).strip()
    git_dir = git(repo, environment, "rev-parse", "--absolute-git-dir").strip()
    try:
        canonical_top = Path(top).resolve(strict=True)
        canonical_git_dir = Path(git_dir).resolve(strict=True)
    except OSError as exc:
        raise Blocked("repository_git_identity_unresolvable") from exc
    if inside != "true" or canonical_top != repo or not canonical_git_dir.is_dir():
        raise Blocked("repository_worktree_root_mismatch")
    return {"worktree": str(canonical_top), "git_dir": str(canonical_git_dir)}


def selected_paths(repo, environment, scope):
    if scope != "full":
        raise Blocked("unsupported_scope")
    tracked = git(repo, environment, "ls-files", "-z").split("\0")
    untracked = git(repo, environment, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
    return sorted({path for path in (*tracked, *untracked) if path})


def hash_regular(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def candidate_manifest(repo, paths):
    manifest = []
    for relative in paths:
        path = repo / relative
        encoded = quote_from_bytes(
            os.fsencode(relative),
            safe="/ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~",
        )
        item = {"path": encoded}
        try:
            metadata = path.lstat()
            item["mode"] = format(metadata.st_mode, "o")
            item["size"] = metadata.st_size
            if stat.S_ISLNK(metadata.st_mode):
                data = os.fsencode(os.readlink(path))
                item.update({
                    "state": "present", "mode": "120000", "object_type": "symlink",
                    "sha256": hashlib.sha256(data).hexdigest(),
                })
            elif stat.S_ISREG(metadata.st_mode):
                item.update({"state": "present", "object_type": "blob", "sha256": hash_regular(path)})
            else:
                item.update({"state": "present", "object_type": "special"})
        except FileNotFoundError:
            item = {"path": encoded, "state": "missing"}
        except OSError as exc:
            item["state"] = f"unreadable:{type(exc).__name__}"
        manifest.append(item)
    return manifest


def capture_repository(repo, environment, scope):
    head_before = git(repo, environment, "rev-parse", "--verify", "HEAD^{commit}").strip()
    status_before = git(repo, environment, "status", "--porcelain=v1", "-z")
    paths = selected_paths(repo, environment, scope)
    manifest = candidate_manifest(repo, paths)
    head_after = git(repo, environment, "rev-parse", "--verify", "HEAD^{commit}").strip()
    status_after = git(repo, environment, "status", "--porcelain=v1", "-z")
    if not HEX40.fullmatch(head_before) or head_before != head_after or status_before != status_after:
        raise Blocked("repository_changed_during_snapshot")
    evidence_paths = [
        quote_from_bytes(
            os.fsencode(path),
            safe="/ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~",
        )
        for path in paths
    ]
    deleted_paths = [
        item["path"] for item in manifest if item.get("state") == "missing"
    ]
    return {
        "head": head_before,
        "paths": paths,
        "evidence_paths": evidence_paths,
        "deleted_paths": deleted_paths,
        "candidate_digest": digest_value(manifest),
        "status_digest": hashlib.sha256(status_before.encode("utf-8")).hexdigest(),
        "working_tree_dirty": bool(status_before),
    }


def effective_policy(policy_snapshot):
    try:
        provided = json.loads(policy_snapshot.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Failed("policy_snapshot_unreadable") from exc
    allowed = {
        "$schema", "schema", "profile", "enforcement", "fail_on",
        "max_file_bytes", "sensitive_globs", "required_evidence",
    }
    if not isinstance(provided, dict) or set(provided) - allowed:
        raise Failed("policy_shape_invalid")
    if provided.get("schema") != POLICY_SCHEMA:
        raise Failed("policy_schema_invalid")
    profile = provided.get("profile")
    if not isinstance(profile, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,96}", profile):
        raise Failed("policy_profile_invalid")
    if "$schema" in provided and not isinstance(provided["$schema"], str):
        raise Failed("policy_schema_reference_invalid")
    if "enforcement" in provided and provided["enforcement"] != "audit":
        raise Failed("policy_enforcement_invalid")
    if "fail_on" in provided:
        fail_on = provided["fail_on"]
        if (
            not isinstance(fail_on, list)
            or any(item not in {"low", "medium", "high", "critical"} for item in fail_on)
            or len(fail_on) != len(set(fail_on))
        ):
            raise Failed("policy_fail_on_invalid")
    maximum = provided.get("max_file_bytes", 5 * 1024 * 1024)
    if type(maximum) is not int or not 1024 <= maximum <= 104857600:
        raise Failed("policy_max_file_bytes_invalid")
    normalized = {
        "schema": POLICY_SCHEMA,
        "profile": profile,
        "max_file_bytes": maximum,
        "sensitive_globs": [],
        "required_evidence": [],
    }
    for key, minimum in (("sensitive_globs", 1), ("required_evidence", 2)):
        items = provided.get(key, [])
        if (
            not isinstance(items, list)
            or any(not isinstance(item, str) or len(item) < minimum for item in items)
            or len(items) != len(set(items))
        ):
            raise Failed(f"policy_{key}_invalid")
        normalized[key] = sorted(set(items))
    return normalized


def parse_timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value
    ):
        raise Failed("evidence_generated_at_invalid")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except ValueError as exc:
        raise Failed("evidence_generated_at_invalid") from exc
    if parsed.utcoffset() != dt.timedelta(0):
        raise Failed("evidence_generated_at_invalid")


def validate_evidence(path, report_path, expected_engine_sha, expected_scope, snapshot, repository_name, policy_snapshot):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Failed("evidence_unreadable") from exc
    expected_top = {"schema", "generated_at", "authority", "effect_authorized", "promotion_authorized", "completion_status", "review_status", "subject", "engine", "summary", "findings", "nonclaims", "diagnostics", "evidence_digest"}
    if not isinstance(value, dict) or set(value) != expected_top:
        raise Failed("evidence_shape_invalid")
    parse_timestamp(value.get("generated_at"))
    if value.get("schema") != EVIDENCE_SCHEMA or value.get("authority") != "none":
        raise Failed("evidence_authority_invalid")
    if value.get("effect_authorized") is not False or value.get("promotion_authorized") is not False:
        raise Failed("evidence_authorization_invalid")
    if value.get("nonclaims") != EXPECTED_NONCLAIMS:
        raise Failed("evidence_nonclaims_invalid")
    subject = value.get("subject")
    expected_subject_keys = {"repository", "base", "head", "event", "pull_request_number", "pull_request_body_digest", "profile", "inspected_paths", "deleted_paths", "scope_mode", "source_mode", "path_encoding", "snapshot_stable", "candidate_digest"}
    if not isinstance(subject, dict) or set(subject) != expected_subject_keys:
        raise Failed("evidence_subject_invalid")
    if expected_scope != "full":
        raise Failed("evidence_scope_unsupported")
    expected_scope_mode = "full-working-tree"
    if subject.get("repository") != repository_name or subject.get("head") != snapshot["head"]:
        raise Failed("evidence_subject_identity_mismatch")
    if subject.get("base") is not None:
        raise Failed("evidence_local_base_invalid")
    if subject.get("event") != "local" or subject.get("source_mode") != "working-tree":
        raise Failed("evidence_source_mode_invalid")
    if subject.get("pull_request_number") is not None or subject.get("pull_request_body_digest") is not None:
        raise Failed("evidence_local_pull_request_fields_invalid")
    if subject.get("path_encoding") != "percent-encoded-bytes-v1" or subject.get("snapshot_stable") is not True:
        raise Failed("evidence_snapshot_state_invalid")
    if (
        subject.get("scope_mode") != expected_scope_mode
        or subject.get("inspected_paths") != snapshot["evidence_paths"]
        or len(subject.get("inspected_paths", [])) != len(set(subject.get("inspected_paths", [])))
    ):
        raise Failed("evidence_scope_mismatch")
    if subject.get("candidate_digest") != snapshot["candidate_digest"]:
        raise Failed("evidence_candidate_digest_mismatch")
    if (
        subject.get("deleted_paths") != snapshot["deleted_paths"]
        or len(subject.get("deleted_paths", [])) != len(set(subject.get("deleted_paths", [])))
    ):
        raise Failed("evidence_deleted_paths_invalid")
    policy = effective_policy(policy_snapshot)
    if subject.get("profile") != policy["profile"]:
        raise Failed("evidence_policy_profile_mismatch")
    engine = value.get("engine")
    if not isinstance(engine, dict) or set(engine) != {"name", "version", "source_digest", "policy_digest"}:
        raise Failed("evidence_engine_invalid")
    if engine.get("name") != "truenorth-federation-sentinel" or engine.get("source_digest") != expected_engine_sha:
        raise Failed("evidence_engine_digest_mismatch")
    if not isinstance(engine.get("version"), str) or not engine["version"]:
        raise Failed("evidence_engine_metadata_invalid")
    if engine.get("policy_digest") != digest_value(policy):
        raise Failed("evidence_policy_digest_mismatch")
    findings = value.get("findings")
    summary = value.get("summary")
    if (
        not isinstance(findings, list)
        or not isinstance(summary, dict)
        or set(summary) != {"finding_count", "by_severity"}
        or type(summary.get("finding_count")) is not int
        or not isinstance(summary.get("by_severity"), dict)
        or set(summary["by_severity"]) != {"critical", "high", "medium", "low"}
        or any(type(summary["by_severity"].get(key)) is not int for key in ("critical", "high", "medium", "low"))
    ):
        raise Failed("evidence_summary_invalid")
    severities = {"critical", "high", "medium", "low"}
    counts = {severity: 0 for severity in severities}
    for finding in findings:
        if not isinstance(finding, dict):
            raise Failed("evidence_finding_invalid")
        expected_finding_keys = {"code", "severity", "message"}
        if "path" in finding:
            expected_finding_keys.add("path")
        if "line" in finding:
            expected_finding_keys.add("line")
        if set(finding) != expected_finding_keys:
            raise Failed("evidence_finding_shape_invalid")
        if (
            not isinstance(finding.get("code"), str)
            or not re.fullmatch(r"SNT[0-9]{3}", finding["code"])
            or finding.get("severity") not in severities
            or not isinstance(finding.get("message"), str)
            or not finding["message"]
            or ("path" in finding and not isinstance(finding["path"], str))
            or ("line" in finding and (type(finding["line"]) is not int or finding["line"] < 1))
        ):
            raise Failed("evidence_finding_invalid")
        counts[finding["severity"]] += 1
    if summary != {"finding_count": len(findings), "by_severity": counts}:
        raise Failed("evidence_summary_mismatch")
    if value.get("completion_status") != "complete":
        raise Failed("evidence_incomplete")
    expected_review = "NO_FINDINGS" if not findings else "REVIEW_REQUIRED"
    if value.get("review_status") != expected_review:
        raise Failed("evidence_review_status_mismatch")
    diagnostics = value.get("diagnostics")
    if not isinstance(diagnostics, dict) or set(diagnostics) != {"policy_source", "working_tree_dirty", "working_tree_status_digest", "working_tree_end_status_digest", "checkout_head_at_end", "snapshot_stable"}:
        raise Failed("evidence_diagnostics_invalid")
    if diagnostics.get("policy_source") != f"working-tree:{policy_snapshot}":
        raise Failed("evidence_policy_source_mismatch")
    if diagnostics.get("working_tree_dirty") is not snapshot["working_tree_dirty"] or diagnostics.get("working_tree_status_digest") != snapshot["status_digest"]:
        raise Failed("evidence_working_tree_mismatch")
    if diagnostics.get("working_tree_end_status_digest") != snapshot["status_digest"] or diagnostics.get("checkout_head_at_end") != snapshot["head"] or diagnostics.get("snapshot_stable") is not True:
        raise Failed("evidence_end_snapshot_mismatch")
    sealed = {key: item for key, item in value.items() if key not in {"generated_at", "diagnostics", "evidence_digest"}}
    if value.get("evidence_digest") != digest_value(sealed):
        raise Failed("evidence_digest_invalid")
    try:
        report_text = report_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Failed("report_unreadable") from exc
    if not report_text.strip():
        raise Failed("report_empty")
    required_report_fragments = (
        f"- Evidence digest: `{value['evidence_digest']}`",
        f"- Head: `{snapshot['head']}`",
        f"- Profile: `{policy['profile']}`",
        "- Authority: `none`",
    )
    if any(fragment not in report_text for fragment in required_report_fragments):
        raise Failed("report_evidence_binding_invalid")
    return value, hashlib.sha256(report_text.encode("utf-8")).hexdigest()


def ensure_private_directory(path, create=False):
    try:
        info = path.lstat()
    except FileNotFoundError:
        if not create:
            raise Blocked(f"private_directory_missing:{path.name}")
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            pass
        info = path.lstat()
    except OSError as exc:
        raise Blocked(f"private_directory_unreadable:{path.name}") from exc
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise Blocked(f"private_directory_invalid:{path.name}")
    return path


def validate_runtime_identifiers(repo_id, run_id, bundle_id):
    if repo_id != "_fleet" and (
        not isinstance(repo_id, str)
        or not REPO_ID.fullmatch(repo_id)
        or repo_id.casefold() == "_fleet"
    ):
        raise Blocked("runtime_repo_id_invalid")
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise Blocked("runtime_run_id_invalid")
    if not isinstance(bundle_id, str) or not HEX64.fullmatch(bundle_id):
        raise Blocked("runtime_bundle_id_invalid")


def validated_evidence_root(evidence_root):
    if not evidence_root.is_absolute():
        raise Blocked("evidence_root_not_absolute")
    ensure_private_directory(evidence_root)
    try:
        resolved = evidence_root.resolve(strict=True)
    except OSError as exc:
        raise Blocked("evidence_root_unresolvable") from exc
    if resolved != evidence_root:
        raise Blocked("evidence_root_path_mismatch")
    return resolved


def regular_digest(path):
    try:
        info = path.lstat()
    except OSError:
        return None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        return None
    return sha256_file(path)


def private_regular_digest(path):
    try:
        info = path.lstat()
    except OSError as exc:
        raise Blocked(f"private_file_unreadable:{path.name}") from exc
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise Blocked(f"private_file_invalid:{path.name}")
    return sha256_file(path)


def validate_complete_status(evidence_root, repo_id, run_id, bundle_id):
    validate_runtime_identifiers(repo_id, run_id, bundle_id)
    base = validated_evidence_root(evidence_root)
    output = base / repo_id / run_id
    ensure_private_directory(base / repo_id)
    ensure_private_directory(output)
    status_path = output / "runner-status.json"
    status_sha = private_regular_digest(status_path)
    try:
        value = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Blocked("worker_status_unreadable") from exc
    expected_keys = {
        "schema", "authority", "effect_authorized", "promotion_authorized",
        "repo_id", "run_id", "bundle_id", "state", "reason", "exit_code",
        "started_at", "finished_at", "head", "candidate_digest",
        "evidence_sha256", "report_sha256", "review_status",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise Blocked("worker_status_shape_invalid")
    if (
        value.get("schema") != RUN_SCHEMA
        or value.get("authority") != "none"
        or value.get("effect_authorized") is not False
        or value.get("promotion_authorized") is not False
        or value.get("repo_id") != repo_id
        or value.get("run_id") != run_id
        or value.get("bundle_id") != bundle_id
        or value.get("state") != "complete"
        or value.get("reason") is not None
        or type(value.get("exit_code")) is not int
        or value.get("exit_code") != 0
        or not HEX40.fullmatch(str(value.get("head", "")))
        or not HEX64.fullmatch(str(value.get("candidate_digest", "")))
        or value.get("review_status") not in {"NO_FINDINGS", "REVIEW_REQUIRED"}
    ):
        raise Blocked("worker_status_contract_invalid")
    parse_timestamp(value.get("started_at"))
    parse_timestamp(value.get("finished_at"))
    if not status_sha:
        raise Blocked("worker_status_digest_invalid")
    evidence_sha = private_regular_digest(output / "sentinel-review-evidence.json")
    report_sha = private_regular_digest(output / "sentinel-report.md")
    if value.get("evidence_sha256") != evidence_sha or value.get("report_sha256") != report_sha:
        raise Blocked("worker_status_artifact_digest_mismatch")
    return value


def status_template(repo_id, run_id, bundle_id, started_at=None):
    started = started_at or utc_now()
    return {
        "schema": RUN_SCHEMA,
        "authority": "none",
        "effect_authorized": False,
        "promotion_authorized": False,
        "repo_id": repo_id,
        "run_id": run_id,
        "bundle_id": bundle_id,
        "state": "blocked",
        "reason": None,
        "exit_code": None,
        "started_at": started,
        "finished_at": started,
    }


def repository_output(evidence_root, repo_id, run_id, allow_existing=False):
    validate_runtime_identifiers(repo_id, run_id, "0" * 64)
    base = validated_evidence_root(evidence_root)
    repo_root = ensure_private_directory(base / repo_id, create=True)
    output = repo_root / run_id
    try:
        output.relative_to(base)
    except ValueError as exc:
        raise Blocked("repository_output_escapes_evidence_root") from exc
    if allow_existing and output.exists():
        ensure_private_directory(output)
    else:
        try:
            output.mkdir(mode=0o700)
        except FileExistsError as exc:
            raise Blocked("repository_output_already_exists") from exc
        ensure_private_directory(output)
    return repo_root, output


def fallback_output(evidence_root, repo_id, run_id):
    validate_runtime_identifiers(repo_id, run_id, "0" * 64)
    base = validated_evidence_root(evidence_root)
    fleet_root = ensure_private_directory(base / "_fleet", create=True)
    name = run_id if repo_id == "_fleet" else f"{run_id}-{repo_id}"
    output = fleet_root / name
    try:
        output.relative_to(base)
    except ValueError as exc:
        raise Blocked("fallback_output_escapes_evidence_root") from exc
    if output.exists():
        ensure_private_directory(output)
    else:
        output.mkdir(mode=0o700)
        ensure_private_directory(output)
    return None, output


def write_result(repo_root, output, status):
    evidence = output / "sentinel-review-evidence.json"
    if status["state"] != "complete":
        untrusted = regular_digest(evidence)
        if untrusted is not None:
            status["untrusted_evidence_sha256"] = untrusted
    status["finished_at"] = utc_now()
    write_json(output / "runner-status.json", status)
    if repo_root is None:
        return
    latest = {
        "schema": "truenorth.federation-sentinel.local-latest.v1",
        "authority": "none",
        "repo_id": status["repo_id"],
        "run_id": status["run_id"],
        "bundle_id": status["bundle_id"],
        "path": str(output),
        "status": status["state"],
    }
    if status["state"] == "complete":
        latest["evidence_sha256"] = status["evidence_sha256"]
        latest["report_sha256"] = status["report_sha256"]
    write_json(repo_root / "latest.json", latest)


def communicate_engine(process):
    try:
        return process.communicate()
    except Exception:
        if process.poll() is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                process.communicate(timeout=TERMINATION_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                process.communicate()
        raise


def record_parent_failure(evidence_root, repo_id, run_id, bundle_id, reason, exit_code, output_text=""):
    status = status_template(repo_id, run_id, bundle_id)
    status.update({"state": "blocked", "reason": reason, "exit_code": exit_code})
    try:
        repo_root, output = repository_output(evidence_root, repo_id, run_id, allow_existing=True)
    except Exception:
        try:
            repo_root, output = fallback_output(evidence_root, repo_id, run_id)
        except Exception:
            return False
    if output_text:
        atomic_write(output / "worker.log", output_text.encode("utf-8", errors="replace"))
    try:
        write_result(repo_root, output, status)
    except Exception:
        return False
    return True


def run_repository_worker(registry_path, engine_path, state_root, evidence_root, manifest_path, bundle_id, run_id, repo_id):
    validate_runtime_identifiers(repo_id, run_id, bundle_id)
    started_at = utc_now()
    status = status_template(repo_id, run_id, bundle_id, started_at)
    repo_root = None
    output = None
    evidence = None
    try:
        manifest, registry = verify_bundle(
            manifest_path, bundle_id, registry_path, engine_path, state_root, evidence_root
        )
        matching = [entry for entry in registry["repositories"] if entry["id"] == repo_id]
        if len(matching) != 1:
            raise Blocked("repository_registry_identity_invalid")
        entry = matching[0]
        repo_root, output = repository_output(evidence_root, repo_id, run_id)
        evidence = output / "sentinel-review-evidence.json"
        report = output / "sentinel-report.md"
        log = output / "runner.log"
        environment = git_environment(Path(os.environ.get("HOME", "/")))
        resolved = Path(entry["path"]).resolve(strict=True)
        if str(resolved) != entry["path"] or not (resolved / ".git").exists():
            raise Blocked("repository_path_mismatch")
        git_identity_before = repository_git_identity(resolved, environment)
        canonical_remote = normalized_remote(entry["expected_remote"])
        if normalized_remote(raw_origin(resolved, environment)) != canonical_remote:
            raise Blocked("repository_origin_mismatch")
        repository_identity = canonical_remote.removeprefix("github.com/")
        live_policy = resolved / ".truenorth" / "sentinel.json"
        policy_snapshot = registry_path.parent / "policies" / f"{repo_id}.json"
        if live_policy.is_symlink() or not live_policy.is_file():
            raise Blocked("live_policy_invalid")
        try:
            live_policy.resolve(strict=True).relative_to(resolved)
        except (OSError, ValueError) as exc:
            raise Blocked("live_policy_escapes_repository") from exc
        if sha256_file(live_policy) != entry["policy_sha256"]:
            raise Blocked("policy_digest_mismatch")
        if sha256_file(policy_snapshot) != entry["policy_sha256"]:
            raise Blocked("policy_snapshot_mismatch")
        before = capture_repository(resolved, environment, entry["scope"])
        command = [
            sys.executable, "-I", "-X", "utf8", str(engine_path), "audit",
            "--repo", str(resolved), "--config", str(policy_snapshot),
            "--require-config", "--scope", entry["scope"], "--enforcement", "audit",
            "--repository-identity", repository_identity,
            "--evidence", str(evidence), "--report", str(report),
        ]
        process = subprocess.Popen(
            command,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=environment,
            start_new_session=False,
        )
        stdout, _ = communicate_engine(process)
        atomic_write(log, (stdout or "").encode("utf-8"))
        status["exit_code"] = process.returncode
        if process.returncode != 0:
            raise Failed(f"engine_exit_{process.returncode}")
        after = capture_repository(resolved, environment, entry["scope"])
        if before != after:
            raise Blocked("repository_changed_during_audit")
        if repository_git_identity(resolved, environment) != git_identity_before:
            raise Blocked("repository_git_identity_changed_during_audit")
        if normalized_remote(raw_origin(resolved, environment)) != canonical_remote:
            raise Blocked("repository_origin_changed_during_audit")
        if sha256_file(live_policy) != entry["policy_sha256"]:
            raise Blocked("policy_changed_during_audit")
        verify_bundle(manifest_path, bundle_id, registry_path, engine_path, state_root, evidence_root)
        receipt, report_sha = validate_evidence(
            evidence,
            report,
            manifest["identity"]["engine_sha256"],
            entry["scope"],
            before,
            repository_identity,
            policy_snapshot,
        )
        if repository_git_identity(resolved, environment) != git_identity_before:
            raise Blocked("repository_git_identity_changed_after_evidence")
        if normalized_remote(raw_origin(resolved, environment)) != canonical_remote:
            raise Blocked("repository_origin_changed_after_evidence")
        status.update({
            "state": "complete",
            "reason": None,
            "head": before["head"],
            "candidate_digest": before["candidate_digest"],
            "evidence_sha256": sha256_file(evidence),
            "report_sha256": report_sha,
            "review_status": receipt["review_status"],
        })
    except Blocked as exc:
        status.update({"state": "blocked", "reason": str(exc) or type(exc).__name__})
    except Failed as exc:
        status.update({"state": "failed", "reason": str(exc) or type(exc).__name__})
    except Exception as exc:
        status.update({"state": "blocked", "reason": f"{type(exc).__name__}:{exc}"})
    if output is None:
        try:
            repo_root, output = fallback_output(evidence_root, repo_id, run_id)
        except Exception:
            return 3
    try:
        write_result(repo_root, output, status)
    except Exception:
        return 3
    if status["state"] == "complete":
        return 0
    return 4 if status["state"] == "failed" else 3


def signal_parent(signum, _frame):
    global TERMINATION_SIGNAL
    TERMINATION_SIGNAL = signum
    process = ACTIVE_WORKER
    if process is not None and process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def stop_process_group(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        stdout, _ = process.communicate(timeout=TERMINATION_GRACE_SECONDS)
        return stdout or ""
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, _ = process.communicate()
        return stdout or ""


def kill_residual_process_group(process_group_id):
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    try:
        os.killpg(process_group_id, signal.SIGKILL)
    except ProcessLookupError:
        return False
    return True


def communicate_worker(process):
    deadline = time.monotonic() + REPOSITORY_TIMEOUT_SECONDS
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return stop_process_group(process), True
        try:
            stdout, _ = process.communicate(timeout=min(1.0, remaining))
            return stdout or "", False
        except subprocess.TimeoutExpired:
            if TERMINATION_SIGNAL is not None:
                return stop_process_group(process), False


def open_fleet_lock(state_root):
    lock = state_root / "run.lock"
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(lock, flags, 0o600)
    info = os.fstat(descriptor)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        os.close(descriptor)
        raise Blocked("fleet_lock_invalid")
    return os.fdopen(descriptor, "a+", encoding="utf-8")


def run_parent(registry_path, engine_path, state_root, evidence_root, manifest_path, bundle_id):
    global ACTIVE_WORKER
    if not isinstance(bundle_id, str) or not HEX64.fullmatch(bundle_id):
        return 3
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + f"-{uuid.uuid4().hex[:8]}"
    try:
        _, registry = verify_bundle(
            manifest_path, bundle_id, registry_path, engine_path, state_root, evidence_root
        )
        lock_handle = open_fleet_lock(state_root)
    except Exception as exc:
        record_parent_failure(
            evidence_root, "_fleet", run_id, bundle_id,
            str(exc) or type(exc).__name__, None,
        )
        return 3
    try:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        _, registry = verify_bundle(
            manifest_path, bundle_id, registry_path, engine_path, state_root, evidence_root
        )
        signal.signal(signal.SIGTERM, signal_parent)
        signal.signal(signal.SIGINT, signal_parent)
        environment = git_environment(Path(os.environ.get("HOME", "/")))
        aggregate = 0
        for entry in registry["repositories"]:
            if TERMINATION_SIGNAL is not None:
                return 128 + TERMINATION_SIGNAL
            repo_id = entry["id"]
            command = [
                sys.executable, "-I", "-X", "utf8", str(Path(__file__).resolve()),
                "--repository-worker", str(registry_path), str(engine_path), str(state_root),
                str(evidence_root), str(manifest_path), bundle_id, run_id, repo_id,
            ]
            try:
                ACTIVE_WORKER = subprocess.Popen(
                    command,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=environment,
                    start_new_session=True,
                )
                stdout, timed_out = communicate_worker(ACTIVE_WORKER)
                return_code = ACTIVE_WORKER.returncode
                residual_group_killed = kill_residual_process_group(ACTIVE_WORKER.pid)
            except Exception as exc:
                stdout = ""
                timed_out = False
                return_code = None
                residual_group_killed = False
                if ACTIVE_WORKER is not None:
                    try:
                        if ACTIVE_WORKER.poll() is None:
                            stdout = stop_process_group(ACTIVE_WORKER)
                        return_code = ACTIVE_WORKER.returncode
                        if kill_residual_process_group(ACTIVE_WORKER.pid):
                            stdout += "\nresidual_worker_process_group_killed\n"
                    except Exception as cleanup_exc:
                        stdout += f"\nworker_cleanup_failed:{type(cleanup_exc).__name__}:{cleanup_exc}\n"
                record_parent_failure(
                    evidence_root, repo_id, run_id, bundle_id,
                    f"worker_start_or_wait_failed:{type(exc).__name__}:{exc}", return_code,
                    stdout,
                )
                aggregate = 3
                ACTIVE_WORKER = None
                continue
            finally:
                if ACTIVE_WORKER is not None and ACTIVE_WORKER.poll() is not None:
                    ACTIVE_WORKER = None
            if TERMINATION_SIGNAL is not None:
                record_parent_failure(
                    evidence_root, repo_id, run_id, bundle_id,
                    f"runner_terminated_signal_{TERMINATION_SIGNAL}", return_code, stdout,
                )
                return 128 + TERMINATION_SIGNAL
            if residual_group_killed:
                record_parent_failure(
                    evidence_root, repo_id, run_id, bundle_id,
                    "residual_worker_process_group_killed", return_code, stdout,
                )
                aggregate = 3
                continue
            if timed_out:
                record_parent_failure(
                    evidence_root, repo_id, run_id, bundle_id,
                    "repository_timeout", return_code, stdout + "\nTIMEOUT\n",
                )
                aggregate = 3
            elif return_code == 0:
                try:
                    verify_bundle(
                        manifest_path, bundle_id, registry_path, engine_path,
                        state_root, evidence_root,
                    )
                    validate_complete_status(evidence_root, repo_id, run_id, bundle_id)
                except Exception as exc:
                    record_parent_failure(
                        evidence_root, repo_id, run_id, bundle_id,
                        f"complete_worker_receipt_invalid:{type(exc).__name__}:{exc}",
                        return_code, stdout,
                    )
                    aggregate = 3
            elif return_code != 0:
                expected_status = evidence_root / repo_id / run_id / "runner-status.json"
                if regular_digest(expected_status) is None:
                    record_parent_failure(
                        evidence_root, repo_id, run_id, bundle_id,
                        f"repository_worker_exit_{return_code}", return_code, stdout,
                    )
                aggregate = 3
        return aggregate
    except Exception as exc:
        record_parent_failure(
            evidence_root, "_fleet", run_id, bundle_id,
            f"fleet_runner_failed:{type(exc).__name__}:{exc}", None,
        )
        return 3
    finally:
        ACTIVE_WORKER = None
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        finally:
            lock_handle.close()


def main():
    os.umask(0o077)
    if len(sys.argv) == 10 and sys.argv[1] == "--repository-worker":
        registry_path, engine_path, state_root, evidence_root, manifest_path = map(Path, sys.argv[2:7])
        return run_repository_worker(
            registry_path, engine_path, state_root, evidence_root, manifest_path,
            sys.argv[7], sys.argv[8], sys.argv[9],
        )
    if len(sys.argv) != 7:
        return 3
    registry_path, engine_path, state_root, evidence_root, manifest_path = map(Path, sys.argv[1:6])
    return run_parent(registry_path, engine_path, state_root, evidence_root, manifest_path, sys.argv[6])


if __name__ == "__main__":
    raise SystemExit(main())
