# SkillAx Spec v0.3

A SkillAx skill is a loadable instruction package that specializes an agent for a job the base model does not already do well.

Level 1 = a `SKILL.md`.
Level 2 = typed axioms + recipes + a fixture the skill must pass.

`SKILL.md` remains the runtime export. Axioms and recipes are the source.

## File contract

```
skill-name/
  SKILL.md          required export
  axioms.json       optional L2 source
  references/
  scripts/
  assets/

recipes/
  recipe-name.json  composition of existing skills — not a new skill

fixtures/
  skill-name/
    in.md           corpus or ticket
    out.md          required refusals + shape
```

## SKILL.md frontmatter (unchanged L1)

```yaml
---
name: kebab-case-name
description: What it does and when to use it. Trigger words live here. Plain YAML scalar.
---
```

Description rules: single line, no quoting, no colon-space, no `<>`, max 1024 characters, capability + triggers.

Body: Core Mandate (≤4 interacting constraints), Operating Principles, Analysis Sequence, Response shape. Under 500 lines.

## Typed axioms

An axiom is a constraint with a type, not a slogan.

Types:
- `job` — what the operator does
- `refuse` — what must not be encoded
- `load` — when this skill may wake
- `bind` — what it may call (other skills, recipes, never a new OS)
- `safety` — floor that fails closed

Count: 3–5 total. At most one `job`. At least one `refuse`.

See `spec/axiom.schema.json`.

## Recipes

A recipe names an arrangement of existing skills. It is not a seventh skill.

- Ingredients = skills that already exist
- Slots = order and what each skill is allowed to emit
- Product-owned if content-bound
- Promote a *generic* extract only after two consumers

See `spec/recipe.schema.json` and `recipes/extract-audit-kernel.json`.

## Fixtures

A skill is not done when it parses. It is done when `fixtures/<name>/in.md` produces the refusals and shape in `out.md`.

Minimum fixture: one job cluster + one pile that must be refused.

## Extraction

1. Cluster procedures
2. Drop base-model knowledge
3. Rank by reuse, buyer, moat
4. Homeogenic generalize
5. Type the axioms
6. Name the job
7. Formalize SKILL.md
8. Add fixture
9. Validate structure + fixture

## Safety floor

Reject: credentials in prompts, unrestricted SSRF/DNS-rebinding/sandbox escape, targeting minors, criminal methods.

## Compatibility

Runtime is still any SKILL.md harness. L2 files are SkillAx-native; other harnesses may ignore them.
