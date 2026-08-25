# Push runbook

Execute this when David says push, ship, commit, promote, or automate the final push, and the crystallization gate has passed.

## Fail closed

Stop if any of these are true:

- No concrete file path
- Skill failed `validate-skill.sh`
- File text looks like a credential (`ghp_`, `sk-`, `lin_wh_`, PEM private key)
- Target repo is unknown
- Unrelated dirty work would be mixed into the same commit

## Default target

Skills go to `dvdmrtnz15-afk/SkillAx` at `skills/<name>/`.
Product runtime goes to the product repo. Do not dump OS skills into `free-agents`.

## Steps

1. Secret-scan every file.
2. Create branch `promote/<name>` from `main`. Never push straight to main. Never force-push.
3. `github___push_files` the skill tree in one commit.
4. Open a PR into `main`. Title `Promote <name>`. Body names the plane that produced it (Grok hot chat, Claude export, etc.).
5. Let `.github/workflows/validate.yml` run. That is the repo agent.
6. Receipt David with the PR URL. Do not merge unless he says merge.
7. Put the PR URL on the Notion row Source Chat if a row exists. Leave Status open until leftover action is gone.

## What this automation is not

It is not a daily ping.
It is not push-on-every-token.
It is not Copilot inventing axioms.
---
