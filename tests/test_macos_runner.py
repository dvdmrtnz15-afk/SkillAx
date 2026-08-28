from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "sentinel" / "macos_runner.py"
SPEC = importlib.util.spec_from_file_location("sentinel_macos_runner", RUNNER_PATH)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


def write_mode(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(mode)


class MacRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_raw_origin_ignores_instead_of_rewrite(self) -> None:
        repo = self.root / "repo"
        repo.mkdir()
        subprocess.run(["/usr/bin/git", "init", "-q", str(repo)], check=True)
        subprocess.run(
            ["/usr/bin/git", "-C", str(repo), "remote", "add", "origin", "https://evil.invalid/project.git"],
            check=True,
        )
        subprocess.run(
            [
                "/usr/bin/git", "-C", str(repo), "config", "--local",
                "url.https://github.com/expected/.insteadOf", "https://evil.invalid/",
            ],
            check=True,
        )
        environment = RUNNER.git_environment(self.root)
        rewritten = subprocess.run(
            ["/usr/bin/git", "-C", str(repo), "remote", "get-url", "origin"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        self.assertEqual(rewritten, "https://github.com/expected/project.git")
        self.assertEqual(RUNNER.raw_origin(repo, environment), "https://evil.invalid/project.git")

    def test_git_identity_rejects_cross_worktree_gitfile(self) -> None:
        source = self.root / "source"
        alias = self.root / "alias"
        source.mkdir()
        alias.mkdir()
        subprocess.run(["/usr/bin/git", "init", "-q", str(source)], check=True)
        subprocess.run(
            ["/usr/bin/git", "-C", str(source), "config", "core.worktree", str(source)],
            check=True,
        )
        (alias / ".git").write_text(f"gitdir: {source / '.git'}\n", encoding="utf-8")
        with self.assertRaisesRegex(RUNNER.Blocked, "repository_worktree_root_mismatch"):
            RUNNER.repository_git_identity(alias.resolve(), RUNNER.git_environment(self.root))

    def test_async_scope_is_full_only(self) -> None:
        with self.assertRaisesRegex(RUNNER.Blocked, "unsupported_scope"):
            RUNNER.selected_paths(self.root, {}, "changes")

    def test_effective_policy_matches_engine_normalization(self) -> None:
        policy_path = self.root / "policy.json"
        policy_path.write_text(
            json.dumps({
                "schema": RUNNER.POLICY_SCHEMA,
                "profile": "repo.v1",
                "enforcement": "audit",
                "fail_on": ["critical"],
                "sensitive_globs": ["z/**", "a/**"],
            }),
            encoding="utf-8",
        )
        self.assertEqual(
            RUNNER.effective_policy(policy_path),
            {
                "schema": RUNNER.POLICY_SCHEMA,
                "profile": "repo.v1",
                "max_file_bytes": 5 * 1024 * 1024,
                "sensitive_globs": ["a/**", "z/**"],
                "required_evidence": [],
            },
        )

    def make_evidence(self) -> tuple[Path, Path, dict, Path, str]:
        policy_path = self.root / "policy.json"
        policy_path.write_text(
            json.dumps({"schema": RUNNER.POLICY_SCHEMA, "profile": "repo.v1"}),
            encoding="utf-8",
        )
        policy = RUNNER.effective_policy(policy_path)
        head = "1" * 40
        snapshot = {
            "head": head,
            "evidence_paths": ["gone.txt", "safe.txt"],
            "deleted_paths": ["gone.txt"],
            "candidate_digest": "2" * 64,
            "status_digest": "3" * 64,
            "working_tree_dirty": True,
        }
        evidence = {
            "schema": RUNNER.EVIDENCE_SCHEMA,
            "generated_at": RUNNER.utc_now(),
            "authority": "none",
            "effect_authorized": False,
            "promotion_authorized": False,
            "completion_status": "complete",
            "review_status": "REVIEW_REQUIRED",
            "subject": {
                "repository": "repo",
                "base": None,
                "head": head,
                "event": "local",
                "pull_request_number": None,
                "pull_request_body_digest": None,
                "profile": "repo.v1",
                "inspected_paths": ["gone.txt", "safe.txt"],
                "deleted_paths": ["gone.txt"],
                "scope_mode": "full-working-tree",
                "source_mode": "working-tree",
                "path_encoding": "percent-encoded-bytes-v1",
                "snapshot_stable": True,
                "candidate_digest": "2" * 64,
            },
            "engine": {
                "name": "truenorth-federation-sentinel",
                "version": "test",
                "source_digest": "4" * 64,
                "policy_digest": RUNNER.digest_value(policy),
            },
            "summary": {
                "finding_count": 1,
                "by_severity": {"critical": 0, "high": 0, "medium": 1, "low": 0},
            },
            "findings": [{"code": "SNT020", "severity": "medium", "message": "review", "path": "safe.txt"}],
            "nonclaims": RUNNER.EXPECTED_NONCLAIMS,
            "diagnostics": {
                "policy_source": f"working-tree:{policy_path}",
                "working_tree_dirty": True,
                "working_tree_status_digest": "3" * 64,
                "working_tree_end_status_digest": "3" * 64,
                "checkout_head_at_end": head,
                "snapshot_stable": True,
            },
        }
        evidence["evidence_digest"] = RUNNER.digest_value({
            key: value
            for key, value in evidence.items()
            if key not in {"generated_at", "diagnostics", "evidence_digest"}
        })
        evidence_path = self.root / "evidence.json"
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        report_path = self.root / "report.md"
        report_path.write_text(
            "\n".join([
                "# TrueNorth Federation Sentinel review",
                "- Authority: `none`",
                "- Profile: `repo.v1`",
                f"- Head: `{head}`",
                f"- Evidence digest: `{evidence['evidence_digest']}`",
            ]),
            encoding="utf-8",
        )
        return evidence_path, report_path, snapshot, policy_path, evidence["engine"]["source_digest"]

    def test_evidence_validation_binds_policy_deletions_and_report(self) -> None:
        evidence_path, report_path, snapshot, policy_path, engine_sha = self.make_evidence()
        _, report_sha = RUNNER.validate_evidence(
            evidence_path, report_path, engine_sha, "full", snapshot, "repo", policy_path
        )
        self.assertEqual(report_sha, hashlib.sha256(report_path.read_bytes()).hexdigest())

        changed = json.loads(evidence_path.read_text(encoding="utf-8"))
        changed["subject"]["deleted_paths"] = []
        changed["evidence_digest"] = RUNNER.digest_value({
            key: value
            for key, value in changed.items()
            if key not in {"generated_at", "diagnostics", "evidence_digest"}
        })
        evidence_path.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaisesRegex(RUNNER.Failed, "evidence_deleted_paths_invalid"):
            RUNNER.validate_evidence(
                evidence_path, report_path, engine_sha, "full", snapshot, "repo", policy_path
            )

    def test_report_must_bind_the_receipt(self) -> None:
        evidence_path, report_path, snapshot, policy_path, engine_sha = self.make_evidence()
        report_path.write_text("unrelated report\n", encoding="utf-8")
        with self.assertRaisesRegex(RUNNER.Failed, "report_evidence_binding_invalid"):
            RUNNER.validate_evidence(
                evidence_path, report_path, engine_sha, "full", snapshot, "repo", policy_path
            )

    def test_invalid_repository_output_falls_back_to_fleet_receipt(self) -> None:
        evidence_root = self.root / "evidence"
        evidence_root.mkdir(mode=0o700)
        target = self.root / "redirect"
        target.mkdir(mode=0o700)
        (evidence_root / "repo").symlink_to(target, target_is_directory=True)
        result = RUNNER.record_parent_failure(
            evidence_root,
            "repo",
            "20260828T010203.000000Z-deadbeef",
            "a" * 64,
            "output_root_invalid",
            None,
        )
        self.assertTrue(result)
        receipt = evidence_root / "_fleet" / "20260828T010203.000000Z-deadbeef-repo" / "runner-status.json"
        value = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(value["repo_id"], "repo")
        self.assertEqual(value["state"], "blocked")
        self.assertFalse(value["effect_authorized"])

    def test_internal_worker_identifiers_cannot_escape_evidence_root(self) -> None:
        evidence_root = self.root / "evidence"
        evidence_root.mkdir(mode=0o700)
        with self.assertRaisesRegex(RUNNER.Blocked, "runtime_run_id_invalid"):
            RUNNER.repository_output(evidence_root, "repo", "../escape")
        self.assertFalse((self.root / "escape").exists())

    def test_parent_requires_complete_digest_bound_worker_status(self) -> None:
        evidence_root = self.root / "evidence"
        evidence_root.mkdir(mode=0o700)
        run_id = "20260828T010203.000000Z-deadbeef"
        bundle_id = "a" * 64
        _, output = RUNNER.repository_output(evidence_root, "repo", run_id)
        evidence = output / "sentinel-review-evidence.json"
        report = output / "sentinel-report.md"
        write_mode(evidence, b"{}\n", 0o600)
        write_mode(report, b"report\n", 0o600)
        status = RUNNER.status_template("repo", run_id, bundle_id)
        status.update({
            "state": "complete",
            "reason": None,
            "exit_code": 0,
            "finished_at": RUNNER.utc_now(),
            "head": "1" * 40,
            "candidate_digest": "2" * 64,
            "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
            "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
            "review_status": "NO_FINDINGS",
        })
        RUNNER.write_json(output / "runner-status.json", status)
        value = RUNNER.validate_complete_status(evidence_root, "repo", run_id, bundle_id)
        self.assertEqual(value["state"], "complete")
        report.write_text("tampered\n", encoding="utf-8")
        report.chmod(0o600)
        with self.assertRaisesRegex(RUNNER.Blocked, "artifact_digest_mismatch"):
            RUNNER.validate_complete_status(evidence_root, "repo", run_id, bundle_id)

    def make_bundle(self, repo_id: str = "repo") -> tuple[Path, str, Path, Path, Path, Path]:
        install_root = self.root / "install"
        releases = install_root / "releases"
        state_root = install_root / "state"
        evidence_root = install_root / "evidence"
        log_root = self.root / "logs"
        for path in (releases, state_root, evidence_root, log_root):
            path.mkdir(parents=True, mode=0o700)
            path.chmod(0o700)
        engine = b"engine\n"
        runner = b"runner\n"
        policy = b"{}\n"
        registry_value = {
            "schema": RUNNER.REGISTRY_SCHEMA,
            "repositories": [{
                "id": repo_id,
                "path": "/tmp/repo",
                "expected_remote": "https://github.com/example/repo.git",
                "policy_sha256": hashlib.sha256(policy).hexdigest(),
                "scope": "full",
            }],
        }
        registry = (json.dumps(registry_value, indent=2, sort_keys=True) + "\n").encode()
        schemas = {
            "local-repos.v1.schema.json": b"local repos\n",
            "local-run.v1.schema.json": b"local run\n",
            "sentinel-review-evidence.v1.schema.json": b"evidence\n",
        }
        identity = {
            "schema": RUNNER.BUNDLE_SCHEMA,
            "engine_sha256": hashlib.sha256(engine).hexdigest(),
            "runner_sha256": hashlib.sha256(runner).hexdigest(),
            "registry_normalized_sha256": hashlib.sha256(registry).hexdigest(),
            "schema_sources_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in schemas.items()},
            "interval_seconds": 3600,
            "python_executable": str(Path(sys.executable).resolve()),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "python_mode": ["-I", "-X", "utf8"],
            "installation_root": str(install_root),
            "state_dir": str(state_root),
            "evidence_dir": str(evidence_root),
            "log_dir": str(log_root),
        }
        bundle_id = RUNNER.digest_value(identity)
        bundle = releases / bundle_id
        bundle.mkdir(mode=0o700)
        registry_path = bundle / "config" / "repos.v1.json"
        engine_path = bundle / "sentinel.py"
        manifest_path = bundle / "bundle-manifest.json"
        write_mode(engine_path, engine, 0o500)
        write_mode(bundle / "run-all.py", runner, 0o500)
        write_mode(registry_path, registry, 0o400)
        write_mode(bundle / "config" / "policies" / f"{repo_id}.json", policy, 0o400)
        for name, data in schemas.items():
            write_mode(bundle / "schemas" / name, data, 0o400)
        arguments = [
            str(Path(sys.executable).resolve()), "-I", "-X", "utf8",
            str(bundle / "run-all.py"), str(registry_path), str(engine_path),
            str(state_root), str(evidence_root), str(manifest_path), bundle_id,
        ]
        plist = {
            "Label": RUNNER.LABEL,
            "ProgramArguments": arguments,
            "RunAtLoad": True,
            "StartInterval": 3600,
            "ProcessType": "Background",
            "StandardOutPath": str(log_root / "launchagent.out.log"),
            "StandardErrorPath": str(log_root / "launchagent.err.log"),
        }
        write_mode(bundle / f"{RUNNER.LABEL}.plist", plistlib.dumps(plist, sort_keys=True), 0o400)
        for path in (bundle / "config" / "policies", bundle / "config", bundle / "schemas"):
            path.chmod(0o500)
        files, directories, _ = RUNNER.inspect_tree(bundle)
        manifest = {
            "schema": RUNNER.BUNDLE_SCHEMA,
            "bundle_id": bundle_id,
            "identity": identity,
            "files": files,
            "directories": directories,
        }
        write_mode(manifest_path, (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(), 0o400)
        bundle.chmod(0o500)
        return manifest_path, bundle_id, registry_path, engine_path, state_root, evidence_root

    def test_bundle_verification_rejects_extra_file(self) -> None:
        manifest, bundle_id, registry, engine, state, evidence = self.make_bundle()
        verified, entries = RUNNER.verify_bundle(
            manifest, bundle_id, registry, engine, state, evidence
        )
        self.assertEqual(verified["bundle_id"], bundle_id)
        self.assertEqual(entries["repositories"][0]["id"], "repo")
        bundle = manifest.parent
        bundle.chmod(0o700)
        write_mode(bundle / "unexpected", b"x", 0o400)
        bundle.chmod(0o500)
        with self.assertRaisesRegex(RUNNER.Blocked, "inventory_mismatch"):
            RUNNER.verify_bundle(manifest, bundle_id, registry, engine, state, evidence)

    def test_bundle_verification_rejects_reserved_registry_id(self) -> None:
        manifest, bundle_id, registry, engine, state, evidence = self.make_bundle("_fleet")
        with self.assertRaisesRegex(RUNNER.Blocked, "registry_repo_id_invalid"):
            RUNNER.verify_bundle(manifest, bundle_id, registry, engine, state, evidence)

    def test_whole_worker_timeout_kills_and_reaps_process_group(self) -> None:
        prior_timeout = RUNNER.REPOSITORY_TIMEOUT_SECONDS
        prior_grace = RUNNER.TERMINATION_GRACE_SECONDS
        RUNNER.REPOSITORY_TIMEOUT_SECONDS = 0.1
        RUNNER.TERMINATION_GRACE_SECONDS = 0.1
        heartbeat = self.root / "heartbeat"
        child_code = (
            "import os,signal,sys,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "p=sys.argv[1]; "
            "exec('while True:\\n open(p, \\\"a\\\").write(\\\"x\\\")\\n time.sleep(0.02)')"
        )
        parent_code = (
            "import signal,subprocess,sys; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "p=subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]]); "
            "print(p.pid, flush=True); p.wait()"
        )
        process = subprocess.Popen(
            [sys.executable, "-c", parent_code, child_code, str(heartbeat)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            _, timed_out = RUNNER.communicate_worker(process)
            self.assertTrue(timed_out)
            self.assertIsNotNone(process.returncode)
            size_after_kill = heartbeat.stat().st_size
            time.sleep(0.1)
            self.assertEqual(heartbeat.stat().st_size, size_after_kill)
        finally:
            RUNNER.REPOSITORY_TIMEOUT_SECONDS = prior_timeout
            RUNNER.TERMINATION_GRACE_SECONDS = prior_grace
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()

    def test_engine_communicate_exception_forces_kill_and_reap(self) -> None:
        process = mock.Mock()
        process.poll.return_value = None
        process.communicate.side_effect = [
            RuntimeError("pipe failed"),
            subprocess.TimeoutExpired(["engine"], 1),
            ("", None),
        ]
        with self.assertRaisesRegex(RuntimeError, "pipe failed"):
            RUNNER.communicate_engine(process)
        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()
        self.assertEqual(process.communicate.call_count, 3)


if __name__ == "__main__":
    unittest.main()
