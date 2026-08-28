# TrueNorth Federation Sentinel

Concept ID: `review.observer.federation-sentinel`

Federation Sentinel is a deterministic, read-only reviewer for GitHub and registered macOS checkouts. It turns Execution OS architecture policy into repeatable review evidence without creating another authority plane. The name distinguishes this fleet reviewer from LYZT's internal product-security Sentinel.

SkillAx is the provisional public distribution host for the candidate action because private repositories across the two current GitHub accounts need one immutable public action SHA. SkillAx does not own repository policy, findings, waivers, or promotion. Those contracts belong in the platform contract registry.

## Boundary

Federation Sentinel may inspect exact candidate Git objects, detect universal deterministic hazards, apply policy from the pull request's base commit, request evidence for sensitive paths, add an audit summary, and emit JSON/Markdown review evidence.

It never grants authority, approves a merge, executes repository-defined commands, promotes canon or memory, posts comments, patches, pushes, merges, deploys, retrieves secrets, or executes a product effect. A clean result is not proof of correctness.

Repository-native tests run in separate CI jobs. AI reviewers may synthesize Sentinel evidence as untrusted advice, but cannot convert it into authorization.

## GitHub caller

Each repository pins the public SkillAx action to an immutable 40-character commit and checks out the exact event head:

```yaml
name: Federation Sentinel
on:
  pull_request:
    types: [opened, reopened, synchronize, edited, ready_for_review]
  push:
    branches: [main]
  workflow_dispatch:
permissions:
  contents: read

jobs:
  review:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
        with:
          fetch-depth: 0
          persist-credentials: false
          ref: ${{ github.event.pull_request.head.sha || github.sha }}
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065
        with:
          python-version: "3.12"
          cache: ""
      - id: sentinel
        uses: dvdmrtnz15-afk/SkillAx/sentinel@<FULL_REVIEWED_SKILLAX_COMMIT_SHA>
        with:
          config: .truenorth/sentinel.json
          enforcement: audit
      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02
        if: always() && steps.sentinel.outputs.evidence-path != ''
        with:
          name: federation-sentinel-${{ github.sha }}
          path: |
            ${{ steps.sentinel.outputs.evidence-path }}
            ${{ steps.sentinel.outputs.report-path }}
          if-no-files-found: error
          retention-days: 30
```

Sentinel v1 has only `audit` mode. Promotion or merge enforcement, if later ratified, must remain a separate platform-owned admission mechanism; it must not be introduced by changing a repository policy value. Current private user-owned repositories may not support required checks under their present GitHub plan, so no required-check capability is claimed here.

## Policy trust

Store `.truenorth/sentinel.json` in each consuming repository. Profiles and sensitive paths are repository-owned; the engine does not invent architecture policy.

```json
{
  "schema": "truenorth.sentinel.policy.v1",
  "profile": "quillgenie.product-runtime.v1",
  "enforcement": "audit",
  "fail_on": ["critical"],
  "max_file_bytes": 5242880,
  "sensitive_globs": ["**/*auth*", "**/*publish*", "**/*payment*", "migrations/**"],
  "required_evidence": ["Product owner", "Effect impact", "Tests", "Rollback"]
}
```

For pull requests, Sentinel loads the base commit's policy. A candidate cannot weaken its own review. First-time policy addition uses the embedded hygiene policy and emits `BOOTSTRAP_REVIEW_REQUIRED`. Any later policy change is a critical independent-review finding.

Policy can add repository requirements but cannot disable hard-coded conflict-marker, secret, Unicode-control, destructive-shell, symlink-escape, or workflow-risk checks. Policy contains no shell commands.

## Review evidence

`truenorth.sentinel.review-evidence.v1` binds exact base/head commits, inspected and deleted paths, candidate digest, engine digest, base-policy digest, stable findings, and explicit nonclaims. It always carries:

```text
authority: none
effect_authorized: false
promotion_authorized: false
```

The sealed evidence digest excludes timestamp and local diagnostics. GitHub writes evidence beneath `RUNNER_TEMP`, never into the audited checkout.

## Local macOS

Create an explicit local repository registry from `sentinel/local-repos.example.json`, replacing its all-zero digest. Every entry must bind a stable ID, absolute checkout path, expected GitHub origin, and SHA-256 of its reviewed `.truenorth/sentinel.json`. Broad roots, recursive discovery, implicit nested repositories, and policy-digest drift are rejected.

From a reviewed SkillAx checkout:

```bash
./scripts/install-macos-launchagent.sh \
  --registry /absolute/path/to/repos.v1.json
```

This stages a versioned engine and candidate plist beneath:

```text
~/Library/Application Support/TrueNorth/FederationSentinel/
```

It does not activate the LaunchAgent. Review the normalized registry, engine digest, runner, candidate plist, and printed bundle ID. Then explicitly load that exact recomputed bundle:

Production activation remains blocked for this candidate until a durable PREPARED activation journal, next-run reconciliation, lifecycle/permissions/log tests, and macOS privacy/TCC validation pass on a linked GUI Mac. The installer deliberately rejects `--load` today. The command below documents the future explicit interface; it was not run or enabled by this rollout.

```bash
./scripts/install-macos-launchagent.sh \
  --registry /absolute/path/to/repos.v1.json \
  --load \
  --expected-bundle-id <REVIEWED_64_CHARACTER_BUNDLE_ID>
```

If any input changes between staging and loading, the bundle ID changes and activation stops. The installer also refuses to replace a running service; unload it separately, verify the exact Sentinel label is inactive, and use `--replace` only for a validated inactive plist.

After any activation attempt, inspect the newest receipt under `state/activation`, verify the exact `gui/<uid>/com.truenorthapplications.federation-sentinel` loaded state, and hash the active plist against the receipt. If the process was interrupted or the receipt says `rollback_failed`, do not retry automatically: boot out only that exact label if it is loaded, preserve the transaction directory, reconcile the inactive plist from its recorded `prior.plist` (or remove the candidate if no prior plist existed), and independently verify the final unloaded state. SIGKILL or power loss is not claimed to be transactionally recoverable.

The asynchronous worker uses a private lock, a 300-second whole-repository timeout target, minimized environment, separate per-run evidence directories, and atomic latest pointers. An OS process stuck in an uninterruptible state can exceed that target, but it cannot produce a false-complete receipt. The worker's `full` scope covers tracked files plus untracked files that Git does not ignore; ignored files are outside scope. It binds each receipt to the raw, include-free canonical GitHub origin, records dirty-state plus content digests, and never fetches or executes repository code. A completed local status binds both evidence and Markdown report hashes. Review evidence lives under Application Support; process logs live under `~/Library/Logs` and need an independently configured retention or rotation policy.

Run one checkout manually, writing evidence outside it:

```bash
python3 sentinel/sentinel.py audit \
  --repo /absolute/path/to/repo \
  --config /absolute/path/to/repo/.truenorth/sentinel.json \
  --evidence /tmp/sentinel-review-evidence.json \
  --report /tmp/sentinel-report.md
```

## Promotion sequence

1. Ratify the Concept Registry entry and platform-owned contract locations.
2. Resolve SkillAx's existing red default-branch validation independently of Sentinel.
3. Obtain independent review of this engine; it cannot certify itself.
4. Merge and pin the reviewed engine by exact commit.
5. Roll out audit-only callers and repository-owned policies in cohorts.
6. Triage findings and create separate draft patch PRs; Sentinel never patches what it scores.
7. Validate the same engine digest, LaunchAgent lifecycle, permissions, and macOS privacy prompts on a linked Mac before activation.
8. If enforcement is ever needed, design it as a separate platform-owned admission control after baseline triage, bypass testing, and GitHub plan/ruleset verification.
9. Keep human/repository ownership and Canon Review upstream of promotion.
