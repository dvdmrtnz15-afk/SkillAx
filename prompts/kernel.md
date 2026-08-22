# Prompt — kernel vs app

Classify each item I list as KERNEL (always on), APP (load on trigger), or DELETE.

Tests:
- Strong model already knows this? → DELETE
- Capital allocation / who pays / what not to build? → KERNEL (TrueNorth only)
- How skills are extracted, named, validated, shipped? → KERNEL (SkillAx only)
- Domain job a third party can run without me? → APP
- Two items share the same job? → merge, keep one name

Constraints:
- At most 2 kernels.
- App descriptions must not steal pre-load attention from the kernels.
- No item may be named OS unless it governs the others.

Return a table: item, class, one-line job, merge/rename if needed.

Example input:
true-north-founder-os, skillax, productized-knowledge-to-asset-system,
sovereign-control-plane, consultative-service-operations-os,
how to write a for-loop, jungian thesis notes

Example output:
| item | class | change |
| true-north-founder-os | KERNEL | keep |
| skillax | KERNEL | keep |
| productized-knowledge-to-asset-system | DELETE | merge into skillax |
| sovereign-control-plane | APP | keep |
| consultative-service-operations-os | APP | rename consultative-service-ops |
| how to write a for-loop | DELETE | base model |
| jungian thesis notes | DELETE | off-stack |
