# SkillAx

**Chillax. Load the skill. Ship the work.**

SkillAx is an axiom-boiled agent-skill standard and reference pack.

Most public skills are prompt dumps. They inflate tokens, leak risk, and collapse when someone other than the author uses them. SkillAx treats a skill as a **transferable asset**: few canonical axioms, tight triggers, progressive disclosure, and a safety floor.

```
Skill  +  Ax  =  SkillAx
          ^
     axiom, not vibes
```

## Why this exists

GitHub is flooded with agent skills. Quality is not. SkillAx is the calm layer:

- Encode only **asymmetric procedural knowledge** the base model does not already have
- Boil every skill to **canonical axioms** (3-5 non-negotiables)
- Name for the **job**, not the origin story
- Design for **homeogenic** outcomes — stable results across similar users, industries, and constraints
- Keep **cognitive load** inside working-memory limits (progressive disclosure)
- Lint structure and obvious security foot-guns before install

## Quick start

```bash
git clone https://github.com/dvdmrtnz15-afk/SkillAx.git
cp -R SkillAx/skills/sovereign-control-plane ~/.your-agent/skills/
python3 SkillAx/scripts/validate.py --all
```

Works with Claude Code, Codex, Cursor, Grok, Hermes, and any SKILL.md harness.

## Reference pack (v0.2)

| Skill | Job |
|-------|-----|
| [sovereign-control-plane](skills/sovereign-control-plane/SKILL.md) | Controllable, auditable multi-agent systems |
| [cinematic-narrative-engine](skills/cinematic-narrative-engine/SKILL.md) | Repeatable short-form cinematic systems |
| [consultative-service-operations-os](skills/consultative-service-operations-os/SKILL.md) | High-touch appointment + mentorship operations |
| [constraint-based-planning-engine](skills/constraint-based-planning-engine/SKILL.md) | Plans that respect hard constraints |
| [structured-document-compliance-agent](skills/structured-document-compliance-agent/SKILL.md) | High-stakes documents under constraints |
| [persistent-character-world-system](skills/persistent-character-world-system/SKILL.md) | Long-running coherent narrative universes |

Stack: [STACK.md](STACK.md). Spec: [spec/SKILLAX.md](spec/SKILLAX.md). Prompts: [prompts/](prompts/). Launch: [LAUNCH.md](LAUNCH.md). Agents: [llms.txt](llms.txt).

`productized-knowledge-to-asset-system` is merged into SkillAx. Historical file only.

## Canonical axioms

1. Only asymmetric procedural knowledge is allowed.
2. A third party must be able to use the skill without the original expert.
3. Homeogenic first, specialty second.
4. Ownership and recurring revenue are design constraints.
5. Name for the job, not the story.
6. Stop at 7-9 skills per corpus. More is usually generic knowledge.

## Topics

`ai-agents` · `agent-skills` · `agent-harness` · `mcp` · `skillax` · `claude-code` · `llm`

## License

MIT. See [LICENSE](LICENSE).
