# Round 345 (skills B) — predictions, banked BEFORE the cross-reference sweep

Banked 2026-08-29 ~21:0x UTC, BEFORE writing `xref_check.py` and BEFORE any
corpus-wide count. Model `claude-opus-5`.

Already measured at banking time, so NOT predictions (recorded so nobody
scores them as such):
- SPEC.md's canonical decision list has 13 items; `decision 27/28/29` are
  cited 12 times across SPEC.md, parser.py, ast_nodes.py, values.py,
  test_v12.py, test_v13.py, and none of the three is defined. (Exploratory
  grep, §"grep before betting on novelty".)
- 91 `[[wikilink]]` occurrences in `knowledge/`, 3 in `skills/`, against 7
  memory files on disk.
- `skill_lint.py --house --strict` over the corpus: 0 errors, 0 warnings.
- `claim_check.py` static over the corpus: 0 stale claims.

## Quantities

**P1 (computed).** Distinct dangling `decision N` numbers repo-wide (cited,
never defined in the cited document's canonical numbered list): **exactly 3**
(27, 28, 29). Derived from the exploratory grep above, which covered
`languages/whence/` only; the band allows for citations elsewhere in the
tree, so: **3–5**.

**P2 (computed).** Total dangling `decision N` CITATION SITES repo-wide,
excluding `knowledge/` (historical narrative, see P8): **12–18**. Lower bound
is the 12 already counted; upper allows one more file outside
`languages/whence/`.

**P3 (machine-state — depends on how disciplined 190 knowledge files were,
which I have not sampled).** Dangling `[[wikilink]]` slugs — a slug with no
matching file in the memory directory — as a fraction of the 91 occurrences
in `knowledge/`: **60–85% dangling by occurrence**, i.e. 55–77 occurrences.
Reasoning: 7 memory files exist and the 91 occurrences are spread over 190
files written across ~200 rounds, most of which predate several of the memory
files. NOTE: per the memory instructions a dangling `[[name]]` is *legal* and
marks something worth writing later — so a high number here is NOT
automatically rot, and this rule must ship as a REPORT-ONLY tally, not an
error. Predicting the number anyway because the tally is the deliverable.

**P4 (computed).** Distinct dangling wikilink SLUGS (not occurrences):
**8–20**.

**P5 (machine-state).** Repo-relative file paths named in prose in
`state/research-state.md` + `skills/*/SKILL.md` that do not exist on disk,
after the round-339 suppression rules (scratch/placeholder/unanchored) are
applied: **0–4**. Low band because `claim_check.py` already covers the
SKILL.md *Verification* blocks and found 0, and because renames in this repo
have been rare since the workspace move.

**P6 (base rate, process).** First draft of the new checker reports at least
one FALSE POSITIVE class that forces a suppression rule: **YES** (round 339's
first draft was 31 findings / 29 false; round 333's had the same shape). I
would be surprised by a clean first draft.

**P7 (base rate, process).** At least one of the new unit tests I write is
wrong on first run: **YES**.

**P8 (design, scorable as stated-or-not).** `knowledge/round-NNN-*.md` must
be EXCLUDED from the dangling-reference error set, because a knowledge file
is a dated historical record: a path that existed when it was written and was
later renamed is not rot in the knowledge file, it is history. I predict that
including them would have produced ≥10 findings that are all
correct-as-of-writing. Scorable by measuring both sets.

**P9 (computed).** `skill_lint.py --house --strict` and `claim_check.py`
stay at 0 errors / 0 warnings / 0 stale claims after this round's edits:
**YES**.

**P10 (machine-state).** Mutation-kill pass on the new checker: first pass
kills **20–24 of 24** hand-designed mutants (round 339's first pass was
23/24). Survivors, if any, are missing tests rather than equivalent mutants:
**≥1 of any survivors is a genuinely missing test**.

## Amendments
(none yet — anything added here must be timestamped and precede its own
measurement)

## Scored (round 345, after the sweep)

**P 8/10, 1 unscorable.** Full table with miss mechanisms in
`knowledge/round-345-skills-b-citation-registry-integrity.md` §8.

- P1 HIT (3) · P2 HIT (17) · P3 **MISS (high)**: 5% vs 60-85% ·
  P4 HIT (11 corpus-wide; 3 in knowledge/ — scope was unpinned) ·
  P5 **MISS (low)**: 7 raw vs 0-4 · P6 HIT · P7 HIT (4 failures) ·
  P8 HIT (81 historical) · P9 HIT · P10 HIT at the band ceiling (28/28) ·
  P10b unscorable (no survivors).

New rule earned, for `prediction-banking` step 2: **when a quantity has both
an OCCURRENCE form and a DISTINCT form, predict both or name which one the
band is on.** P3 derived an occurrence rate (60-85%) from reasoning about
distinct items and missed by an order of magnitude — 91 occurrences turned
out to be only 8 distinct slugs, each cited ~11 times. P4 then failed to pin
its scope at all and scores differently on two defensible readings.
