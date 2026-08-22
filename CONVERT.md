# Level 3 conversion (automated)

Job: turn one founder operating loop into a SkillAx pack a stranger can load.

Not a skill. Not a new OS. Arrangement only: extract → audit → kernel class (`recipes/extract-audit-kernel.json`).

Level 3 is done when the buyer runs the pack without you in the thread.

## Halt rules

- Missing `job` + `corpus` + `must_refuse` → HOLD. Do not extract.
- Origin story, weather, thesis, brand-as-name → refuse or generalize.
- Base-model CRM / “be helpful” → drop.
- Kitchen-sink second job → refuse.
- Safety floor trip → FAIL closed.
- Folklore that will not homeogenize → send back.

## DM (send as-is)

I turn one operating loop into a SkillAx pack a stranger can install. First three founders this week.

Send **one** thing: SOP, ticket pile, or recorded loop. I name the job (not your company), write 3–5 axioms, and ship files you run without me.

I skip brand story, weather, theses, and generic CRM. If it only works as your folklore, I send it back.

## Intake (machine fields)

Copy [prompts/convert-intake.txt](prompts/convert-intake.txt). Parse as key: value.

## Pack contract

Buyer gets:

- `SKILL.md`
- `axioms.json` (3–5 typed: one `job`, ≥1 `refuse`)
- `fixtures/<name>/in.md` + `out.md`
- `python3 scripts/validate.py` on the pack

Stays private (off-repo):

- raw corpus
- staff names, client prices, keys
- this fee and owner notes
- failed drafts

## Price shape

Economic buyer = the founder or ops owner who is the SOP today.

One pack, one job cluster. Fixed conversion fee, paid before draft. One revision if the refuse pile was incomplete. No retainer. First three founders this week are the only discounted slots.

Do not publish dollar amounts in the public post.

## Automation steps

1. Parse intake. HOLD if required fields missing.
2. Extract one kebab job. Drop base-model + origin story.
3. Type axioms. Mandate ≤4 interacting constraints.
4. Write fixture: one job cluster + one refuse pile.
5. Run `python3 scripts/validate.py`. PASS → send pack. FAIL → one revision. Else stop.

Do not add a catalog skill for this loop. Do not wire SCAN measure because of a conversion.
