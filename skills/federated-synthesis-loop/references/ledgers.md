# Ledgers

## Notion — recovery

Database `Chat Threads & Ideas`
`6ca15a00-908d-4ce4-9c37-5a2b36673c00`
Data source `collection://7024c1d7-031c-4d84-b761-7681a858879d`

Write one row per idea. Match on Source Chat URL, then issue id in the title, then overlapping Key Idea.

Properties that matter: Task name, Key Idea, Next Action, Why It Matters, Residual, Source Type, Source Chat, Impact, Recency, Priority, Status, Tags.

Source Type for other models is chatgpt, claude, gemini, perplexity, slack-export, or drive. Tag `external-ai`.

Deprecated stores: Idea & Thread Tracker, stub Chat Threads DB. Do not write them.

## Linear — commitment

Team Truenorthapplications. Founder OS project is the default for operating-system work.

Create an issue only when there is an owner, a next action, and David wants a commitment. Do not clone a recovery row.

Done and Canceled are receipts. They drive Notion close-sync.

## GitHub — promotion

Skills default to `dvdmrtnz15-afk/SkillAx`. Product and runtime work stays in the product repo (example: `dvdmrtnz15-afk/free-agents`).

A chat is not a source of truth after promotion. The file in Git is.

## Drop folder — other models

Drive folder `AI-Exports` or email subject containing `AI export`.

Header block:

```
# Idea title
Source: claude | chatgpt | gemini | perplexity | slack
Date: YYYY-MM-DD
Open question or next action: one concrete sentence
Why it might matter: one sentence
```

No header means notify only if Impact would be 8 or higher.
---
