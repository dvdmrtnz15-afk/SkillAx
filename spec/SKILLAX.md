# SkillAx Spec v0.1

A SkillAx skill is a loadable instruction package that specializes an agent for a job the base model does not already do well.

## File contract

```
skill-name/
  SKILL.md          required
  references/       optional, loaded on demand
  scripts/          optional, deterministic helpers
  assets/           optional, templates not loaded into context
```

`skill-name` is kebab-case, 2–64 characters, starts and ends with a letter or digit, no consecutive hyphens. It must match the `name` field.

## SKILL.md frontmatter

```yaml
---
name: kebab-case-name
description: What it does and when to use it. Trigger words live here. Plain YAML scalar.
---
```

Hard rules for `description`:

- Single line
- No quoting
- No `: ` (colon-space)
- No `<` or `>`
- Max 1024 characters
- Include both capability and trigger scenarios

The description is the only thing visible before load. Make it earn that slot.

## Body rules

Write in imperative form. Challenge every paragraph: does this justify its token cost?

Required sections for a SkillAx reference skill:

1. **Core Mandate** — 3–5 ranked properties
2. **Operating Principles** — non-obvious constraints
3. **Required Analysis Sequence** — what to determine before answering
4. **Response Requirements** — the deliverable shape

Keep SKILL.md under 500 lines. Move depth to `references/`.

## Cognitive load

Treat working memory as ~4 chunks.

- Metadata always visible
- Body loaded on trigger
- References loaded only when needed
- Never dump a corpus into the body

## Naming

- Lead with the capability
- Prefer the job-to-be-done over project mythology
- Test: would a stranger searching for this job use these words?

## Extraction (how a SkillAx skill is born)

1. Cluster a corpus by repeated procedural patterns
2. Drop anything a strong base model already does well
3. Rank survivors by reuse, defensibility, and buyer
4. Generalize to homeogenic form without deleting the specialty core
5. Boil to canonical axioms
6. Optimize the name
7. Formalize and validate

## Safety floor

Reject or flag skills that:

- Request credentials, tokens, or private keys in prompts
- Instruct unrestricted SSRF, DNS rebinding, or sandbox escape
- Target minors
- Encode criminal methods

This is a floor, not a full security product.

## Compatibility

SkillAx SKILL.md files are intended to work with any harness that loads a YAML-frontmatter markdown skill (Claude Code skills, Cursor skills, Grok skills, Hermes plugins, and similar).
