# Round 445 (harness A) — predictions, written BEFORE any measurement (D-013)

**Subject.** The driver's round-439 slow-tier slice made its first non-trivial
catch. Its post-round-444 run logged

```
[2026-09-02 03:35:30] round 444: slowtier-slice OK (slow tier: 31 files / 32 units,
  1 conclusive against checkout 3a96aefb5ed69c5a (3% recall), 1 failing)
```

and appended `test_swe_equivalence.py failed, 3 failed / 8 passed in 58.16s` to
`state/slow-tier-ledger.jsonl` — the file's FIRST appearance in that ledger's 41
entries. Reproduced at HEAD before writing this: `_concat_mutant()` asserts
`no arith mutant on a "concat" line with x + y — re-anchor`.

Already established by reading, NOT predicted here: round 368's `f568a79` (v0.27)
deliberately deleted the inline `return Prov("+", "concat", line, (l, r), _LAZY, x + y)`
that the anchor names; round 437's `ce7a89d` fixed the IDENTICAL anchor in
`harness/tests/test_swe_killers.py` and its 15-file diff does not mention
`equivalence`; `test_swe_equivalence.py`'s helper docstring says *"Same anchor
swe.killers' own test uses"*, a claim round 437 made false.

| # | prediction | band |
|---|---|---|
| P1 | All THREE failures have one root cause: the `_concat_mutant()` helper. Repairing that helper alone turns all three green with no edit to any test body. | 3/3 green from one helper edit; any test needing its own edit is a MISS |
| P2 | Round 437's EXACT fix — deleting the `and "x + y" in ...` clause — is **not sufficient** here. Killers ITERATES `candidates` and equivalence takes `candidates[0]`, and killers' own comment records that "a concat site can be unreachable for two string literals". So the naive port leaves at least one of the three red. | ≥1 still red = HIT; all 3 green on the naive port = MISS |
| P3 | Dropping the clause yields **3** candidates (the three live `"concat"` lines at `interp.py` 2014/2059/2066; 2291 is prose in a comment and carries no arith op). | 3 exact; 2 or 4 a weak hit; ≥5 or ≤1 a MISS |
| P4 | Exactly **2** files in `harness/tests/` carry this `'"concat"' in src.splitlines()` anchor — killers and equivalence. There is no third copy. | 2 exact |
| P5 | `test_swe_killers.py` (`stale_checkout`, 67.5 h old) is GREEN when re-run at HEAD: round 437's fix holds and this is a staleness verdict, not a hidden second red. | green = HIT |
| P6 | The repaired `test_swe_equivalence.py` runs LONGER than the 58.16 s failing run, because three tests that currently abort in the fixture will now execute real Whence programs. | > 58.16 s = HIT; band 90-220 s |
| P7 | Nothing in this repo checks a claim of the form "this fixture is the same as that other file's fixture". The docstring is a cross-file reference with no reader. `claim_check`/`state_claim_check`/`xref_check` all operate on markdown, not on Python docstrings. | no checker found = HIT |
| P8 | After the fix `slowtier status` reports `test_swe_equivalence.py fresh_pass` and `0 failing`. | exact |

**Design position, stated before measuring so it can be refuted.** I predict the
defect is not "a stale anchor" — round 437 already named and fixed that class, and
rule 7 exists for it. I predict the defect is that **a fix was applied to one of two
copies, and the copy that stayed broken was the one whose own docstring asserts the
two are the same.** If P2 holds, the second copy is additionally *weaker* than the
first (first-candidate vs. iterate), which means porting round 437's diff verbatim
would produce a test that passes today and re-breaks on the next `interp.py` edit
that reorders the concat sites. The right repair is therefore to remove the
duplication, not to re-apply the fix twice.
