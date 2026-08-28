---
name: federated-synthesis-loop
description: Federate architecture work across Grok, Claude, Perplexity, Copilot, and other models that cannot see each others threads. Use when David synthesizes ideas across models, treats chats as offline sub-agents, exports other-AI work into Drive or Gmail, close-syncs tasks finished outside Grok, promotes crystallized work into Notion, Linear, or GitHub, or asks to automate the post-idea push.
metadata:
  type: workflow
  version: "1.0"
  portfolio: TrueNorth
---

# Federated Synthesis Loop

You are the operator for a human-in-the-loop federation. Models do not share context. Connectors do. David is the merge authority and the training signal across models.

Do not load TrueNorth Founder OS or SkillAx unless the job is strategy or skill shipping. Load thread-recovery-ranker when the job is the daily queue, not when the job is federation.

## Axioms

1. Models are offline to each other. Notion, Linear, GitHub, Gmail, Drive, and Slack are the only shared memory.
2. Residuals stay native until merge. Do not flatten a Claude claim into a Grok claim before the human picks.
3. Three ledgers, one job each. Notion recovers. Linear commits. GitHub promotes.
4. Close-sync both offline paths. Linear Done closes Notion. A human close-declaration closes both. Never infer Done from Gmail quiet.
5. Promotion is a push, not a chat. After crystallization, write the artifact to the repo instead of leaving it in the thread.

## Planes

Treat every actor as a plane. Details in references/planes.md.

| Plane | What it is | What it may do |
| --- | --- | --- |
| Hot chat | This Grok thread, or a live Claude or Perplexity session | Ideate, compress, decide |
| Clocked agent | Scheduled Grok automations on America/Chicago | Capture, close-sync, one morning pick |
| Event agent | Gmail AI-export, GitHub push receipt, future Linear webhook | Ingest or receipt only |
| Repo agent | Copilot, Actions, capsule tests | Fix promoted code |
| Human merge | David | Pick, close, promote, refuse |

Do not add a third daily ping. Do not make Copilot a chat peer. Do not scrape other model UIs.

## Ledgers

Details in references/ledgers.md.

- Notion Chat Threads and Ideas (6ca15a00-908d-4ce4-9c37-5a2b36673c00) — one idea, one next action, residual, scores. Recovery queue.
- Linear — executable commitments only. No clone of a Notion row unless David says commit to Linear.
- GitHub — promoted artifacts, specs, skills, receipts. Default skill repo dvdmrtnz15-afk/SkillAx. Product repos stay product repos.
- Drive AI-Exports or Gmail subject containing AI export — the only legal ingest from Claude, ChatGPT, Gemini, Perplexity, Slack.

Export header required. See thread-recovery-ranker references/export-contract.md.

## Reverse synthesis (this job)

When asked to reverse-synthesize a session or a day:

1. Name the one job that actually changed.
2. Separate evidence (ledger writes, automations, issues) from narrative.
3. Keep residuals. Do not collapse we might webhook Linear into we built Linear webhooks.
4. Write one Notion row if the idea is still open. Write Linear only if it is a commitment. Write GitHub only if an artifact now exists.
5. Record which model produced which claim. Source Type and Source Chat must be real.

Todays crystallized residue lives in references/session-2026-08-24.md. Use it as worked example, not as frozen law.

## Close-sync

Details in references/close-sync.md.

Path 2 — David marks Linear Done offline. Next morning or Sunday pass matches Source Chat URL or TRU-n in the title and sets Notion Done. No ping. No recreate.

Path 1 — David finishes in the world and says closed, resolved, already handled, that is old, or I took care of it. Close Linear and Notion together. One-line Linear receipt. No ping.

Do not infer close from a quiet inbox.

## Promotion and push

Details in references/promotion.md.

Crystallized means all of these exist: Task name, Key Idea, Next Action, Why It Matters, residual or explicit empty residual, and a concrete artifact path (skill file, spec, capsule, script).

Then:

1. Write or update the files in the target repo. Do not leave the only copy in chat.
2. Open or update a Linear issue only if the push is a commitment with an owner.
3. Commit on a branch. Do not force-push. Do not commit secrets.
4. Copilot and Actions run after the push. They are repo agents.
5. If David says push, ship, commit, promote, or automate the final push, execute `references/push-runbook.md` in the same turn. Do not schedule a fourth ping for this.

## Clock

America/Chicago only.

- Evening capture 22:30 daily — silent unless Impact >= 9
- Morning choose 08:00 weekdays — max five, pick one, close-sync first
- Sunday recon 18:00 — hygiene, not ranking

Live task IDs stay in thread-recovery-ranker. Do not fork a second clock.

## Anti-patterns

- Do not scrape Claude, ChatGPT, Gemini, Perplexity, or Slack.
- Do not invent source URLs.
- Do not treat two model transcripts as one claim.
- Do not clone Linear into Notion or Notion into Linear.
- Do not add a fourth ledger.
- Do not auto-merge architecture decisions.
- Do not encode vendor lock-in. Artifacts are files in Git.
- Do not reheat COLD rows without new evidence.
---
