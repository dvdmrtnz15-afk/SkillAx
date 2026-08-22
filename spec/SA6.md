# SA6

SkillAx Address + six proofs.

Python: one obvious way to write a job.
Turing: a skill is a small machine with a tape, a state, and a halt test.
Satoshi: published axioms are content-addressed. Edits mint a new hash. No priest.
Dewey: every job has a call number so it can be filed, not searched by vibe.
Mythos-6: a job is not real until it survives six layers, not one slogan.

`SKILL.md` is still the export the harness reads. SA6 is the law that file must satisfy.

## The machine

```
tape     = corpus | ticket | screen
head     = description + call number   (only this is visible at idle)
state    = idle | loaded | refused | halted
write    = output + refusal list
halt     = fixture hash matches
```

Idle cost must stay tiny. If the head is a novel, the machine is already broken.

There is one way to add knowledge: cluster → refuse → type axioms → name → address → fixture → hash.
There is not a second way called “make an OS.”

## Call numbers (Dewey for jobs)

Class is the *kind of job*, not the project myth.

| Class | Kind of job |
|------:|-------------|
| 000 | Meta. Extract, validate, address. SkillAx lives here. |
| 100 | Control. Audit, recover, govern agents. |
| 200 | Narrative. Short-form cinematic systems. |
| 300 | Service ops. Consult, roster, multi-site. |
| 400 | Constraint planning. Hard limits first. |
| 500 | High-stakes documents. |
| 600 | Persistent worlds and characters. |
| 700 | Reserved. Empty on purpose. |
| 800 | Recipes (arrangements of 000–600). Not skills. |
| 900 | Private kernels (TrueNorth). Not published. |

Notation: `class.subclass.item` plus kebab name.

```
000.10.01  skillax
100.00.01  sovereign-control-plane
200.00.01  cinematic-narrative-engine
300.00.01  consultative-service-ops
400.00.01  constraint-based-planning-engine
500.00.01  structured-document-compliance-agent
600.00.01  persistent-character-world-system
800.00.01  extract-audit-kernel
```

A stranger files by class, then name. If they need the origin story to find it, the name failed.

## Mythos-6 proofs (all required)

Aristotle put *mythos* (plot) first among six parts of a work. SA6 requires six proofs before a job is real.

| # | Proof | Question | Fail |
|---|--------|----------|------|
| 1 | Literal | What is the single job? | Theme, memoir, thesis |
| 2 | Relational | Can a third party run it? | Only works if you are in the thread |
| 3 | Political | Who pays, or explicit none? | Fake buyer |
| 4 | Load | ≤4 interacting constraints? | Kitchen-sink mandate |
| 5 | Symbolic | Call number + job-name a stranger would search? | LuckyKatOps |
| 6 | Law | Typed axioms + fixture that checks refusals? | Parses but never refuses |

A skill that passes 1 and 5 only is a labeled prompt dump.

## Axiom types (still 3–5)

`job` | `refuse` | `load` | `bind` | `safety`

At most one `job`. At least one `refuse`. Safety fails closed.

## Address (Satoshi move)

Published pack identity is the hash of:

- call number
- kebab name
- axioms.json
- fixture out.md

Change an axiom → new address. Do not silently edit a live pack and keep the old name as if nothing happened.

The network does not trust a README. It trusts the hash and the halt test.

## Recipes live in 800

`extract-audit-kernel` is 800.00.01. It arranges 000. It is not 000.10.02.
Same rule as UI: dishes do not go in the pantry.

## What this is not

Not a blockchain product.
Not a religion.
Not Dewey for books.
Not six new skills.

It is a filing system + a halt test + a ban on priests.

## Halt

The machine stops when `fixtures/<name>/out.md` is satisfied.
If it cannot refuse winters and physics, it has not halted. It has only talked.
