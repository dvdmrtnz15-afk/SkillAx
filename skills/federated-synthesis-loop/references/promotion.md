# Promotion and push

The leak in this workflow is crystallization without a push. The chat holds the only copy. Other models cannot see it. Copilot cannot fix it.

## Crystallization gate

Promote only when all exist:

- One idea
- One next action
- One real stake
- Residual named or explicitly empty
- A file path or spec that can live in Git

If any field is missing, write Notion only.

## Push sequence

1. Write files in the target repo or skill directory.
2. Validate skills with `validate-skill.sh` when the artifact is a skill.
3. Commit on a branch. No secrets. No force-push.
4. Open a PR if another plane (Copilot, Actions, a second human) must review.
5. Link the PR or commit in Linear if a commitment exists. Put the real URL on the Notion Source Chat if the row is still open, then close or leave open based on leftover action.

## Automating the push

The operator automation is the push runbook in `references/push-runbook.md`. Run it in the same turn as the crystallization when David says push, ship, commit, promote, or automate the final push.

Do not fire a push on every assistant token. Do not add a scheduled ping for this.

Legal triggers:

- David says push, ship, commit, promote, or automate the push
- A Linear issue moves to a labeled ready-to-push state
- A skill or spec file was written in the sandbox and David confirms the repo

Fail closed if git status is dirty with unrelated work or if a secret-looking string is staged. Receipt is the PR URL. Do not merge unless David says merge.

## Repo agents after push

Copilot and Actions are allowed to patch tests, types, and lint. They are not allowed to change axioms, authority boundaries, or Why It Matters without a human merge.
---
