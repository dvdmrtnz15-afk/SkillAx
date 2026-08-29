---
name: semantic-ir-compressor
description: Compress a thread, export, or receipt into one SemanticIR fragment for agent federation. Use when David says compress, SemanticIR, one idea plus next action, export for Notion, recover a thread, or when Claude ChatGPT Perplexity Gemini or Grok must hand work to another plane without dumping the transcript.
license: MIT
metadata:
  type: workflow
  version: "1.3"
  portfolio: TrueNorth
---

# SemanticIR Compressor

Turn a source into one fragment another plane can run. Not a summary. Not a transcript.

## Core Mandate

1. Compress one source into one fragment another plane can execute.
2. Never amplify the source claim.
3. Keep residual first-class.
4. Refuse incomplete or out-of-lease work from the working set.

## Operating Principles

- Hard constraints beat similarity.
- Notion is recovery. Linear is a later human commit.
- Real URLs only. No scrape. No inferred Done.
- Circadian receipts with no world delta are not fragments.

## Organism fit

This skill is Skill X on the Cognition Plane. It is the experience and intent frontend of the one IR.

- Signal: Gmail `AI export` or Drive `AI-Exports` is the Event.
- Governance: `gate_fragment` is a reflex. Admit or reject.
- Execution: local stdio MCP is dumb muscle. Writes none.
- State: an admitted Notion row is recovery memory, not Job Active.
- Atlas: organism spec chapter 15. Explorer is not runtime.

Kernel freeze stays `Intent → Job → Process → Capability → Action → Receipt → State`.

## Axioms

1. One source, one fragment. Split if two jobs exist.
2. Non-amplification. Never invent a stronger claim, buyer, deadline, or next action than the source earned.
3. Residual is first-class. Unresolved meaning, intent, authority, evidence, or time stays named.
4. No next action means incomplete. Incomplete rows do not enter the working set unless Impact is 8 or higher.
5. Hard constraints beat similarity. Decorative Why It Matters is rejection, not a soft miss.

## Communications layer (local MCP)

This skill is pointed at by a local stdio MCP. Clients (Claude, Codex, VS Code) attach `mcp.json`. FounderLab Agent Hub stays the vault/handoff gateway. This MCP only admits fragments.

- Server: `scripts/mcp_server.py`
- Tools: `gate_fragment`, `format_export`, `skill_pointer`
- Writes: none
- Export contract: consume `packet` only when `format_export.status` is `ADMITTED`; rejected results never contain a packet.
- Pointer: https://github.com/dvdmrtnz15-afk/SkillAx/tree/main/skills/semantic-ir-compressor

See `references/local-mcp.md`.

## Fragment

Required fields

- title — Job name at Idea or Candidate
- idea — 2 to 4 sentences, source-strength only
- next_action — one concrete verb, next valid step
- why_it_matters — one real stake on the Intent Graph
- residual — unresolved evidence, or empty if cleanly complete
- source_type — grok | claude | chatgpt | gemini | perplexity | linear | github | gmail | drive | slack-export | teams | calendar
- source_url — real URL only. Omit rather than invent.
- plane — the disposable Process that compressed this

Optional ranking fields (do not invent precision)

- impact 1-10
- recency 1-10
- last_activity — ISO date of last human activity

Priority = Impact + Recency when both exist.

## Procedure

1. Read the source. Separate evidence from narrative.
2. Name the one job that actually changed or remains open.
3. Write idea at source strength. If the source said might, keep might.
4. Write next_action as a start move, not a restatement of the idea.
5. Write why_it_matters with a stake. If none exists, mark incomplete. Do not decorate.
6. Write residual. Prefer one dimension. Empty only when nothing is unresolved.
7. Attach source_type and a real source_url when you have one.
8. Run the gate in `scripts/gate.py` or MCP tool `gate_fragment` before a ledger write.
9. Admit only if the gate returns `ok`. `format_export` must return `status: ADMITTED` before a caller consumes `packet`; `status: REJECTED` has no packet. Otherwise return the rejection and stop.

Do not write Linear from a fragment. Notion is recovery. Linear is a later human commit.

## Output

Return exactly one JSON object, then a four-line human block.

```
AI export
Source: <plane>
Date: YYYY-MM-DD
Title: <title>
Key idea: <idea>
Next action: <next_action>
Why it matters: <why_it_matters>
Residual: <residual or empty>
Source URL: <url or omit>
Do not promote to Linear unless David says commit.
```

## Refusals

- Do not merge two models into one claim.
- Do not infer Done from silence.
- Do not infer a pick from a re-issued prompt.
- Do not compress Circadian receipts that have no world delta. Reject as no-evidence pass.
- Do not put family or legal work into a cortex fragment. Mark out_of_lease.
- Do not scrape other-model UIs. Ingest only an export packet, Drive file, or Gmail subject containing AI export.
- Do not treat organism explorer as runtime.

## Load next

Organism binding: `src/lib/organism/semantic-ir.ts` (atlas chapter 15).
Local MCP in `references/local-mcp.md`.
Gate in `scripts/gate.py`.
