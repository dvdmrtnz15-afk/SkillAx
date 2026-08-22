# SCAN

SA6 + UPC + content address + deterministic measurement.

Not a coin. Not a quantum computer. A scannable job that always collapses the same way.

## UPC (the thing you can point a camera at)

A published job has a **Skill Code** — 12 digits, UPC-A shape, so it files like a product.

```
CCC SSS IIII K
 |   |    |   check digit (mod-10, UPC-A weights 3-1-3-1…)
 |   |    item 0001–9999 inside the subclass
 |   subclass 000–999
 class 000–999  (SA6 hundreds: 000 meta … 900 private)
```

Worked:

```
skillax                        000 010 0001  → 0000100001 + check
sovereign-control-plane        100 000 0001
cinematic-narrative-engine     200 000 0001
consultative-service-ops       300 000 0001
constraint-based-planning      400 000 0001
structured-document-compliance 500 000 0001
persistent-character-world     600 000 0001
extract-audit-kernel (recipe)  800 000 0001
TrueNorth (do not publish)     900 000 0001
```

Human form stays Dewey: `000.10.01 skillax`.
Machine form is the 12-digit code + payload.

Payload (QR / Code128, not printed as mysticism):

```
SA6/<call>/<name>/<sha256>
```

Example:

```
SA6/000.10.01/skillax/<64-hex>
```

If the code and the hash disagree, the scan is counterfeit. Trust the hash, not the sticker.

## Crypto (address, not currency)

Canonical bytes, UTF-8, LF, JSON keys sorted:

```
call number
name
axioms.json
fixtures/<name>/out.md
```

`id = sha256(canonical)`.

Rules:
- Same bytes → same id. Always. That is the deterministic half.
- Change one refuse axiom → new id. Old packs keep the old id.
- No admin rewrite of history.
- Signatures optional (owner key). Verification never requires a signature; the hash is enough to detect tamper.

Merkle of axioms (optional, for diffs):
leaf = sha256(axiom.id + type + text), root published next to id.

## Quantum-deterministic measure

Use the physics as a *contract*, not a simulator.

| Physics | Here |
|---------|------|
| Superposition | Unpublished draft. Many axiom sets possible. Do not scan it. |
| Unitary / pure evolution | Extract pipeline is a function. No hidden RNG. Temperature 0 for validate. |
| Entanglement | A recipe halts iff every slot’s fixture would halt. You cannot pass extract and fail refuse. |
| Measurement | Run fixture. Collapse to PASS or FAIL. |
| No-cloning | Copy the markdown, change an axiom, keep the old Skill Code → invalid. |
| Interference | Two skills that claim the same call number + different hash → conflict, do not merge vibes. |

Deterministic means: `measure(tape, machine) → {PASS, FAIL, id}` is a pure function.
Quantum means: until measure, the draft is not in the catalog. Observation is the product.

There is no oracle that “feels” the skill is good.

## Halt procedure

1. Assign call number + item (Dewey).
2. Compute check digit → Skill Code.
3. Write axioms + fixture out.
4. `id = sha256(canonical)`.
5. Measure fixture (deterministic agent or human checklist — same out.md either way).
6. If FAIL, do not publish the code. Superposition remains private.
7. If PASS, publish `SA6/<call>/<name>/<id>`.

## Forbidden

- Tokens, coins, gas, chain for its own sake.
- Publishing class 900.
- Reusing a Skill Code after axiom change.
- Measuring with a creative model temperature as the authority.
- Class 700 placeholders presented as products.

## One sentence

A job is a barcode on a hash that only exists after a deterministic collapse.
