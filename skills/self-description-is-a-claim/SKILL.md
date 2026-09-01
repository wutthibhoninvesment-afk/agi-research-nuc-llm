---
name: self-description-is-a-claim
description: Use when a machine-readable artefact carries prose ABOUT ITSELF — a `_comment` atop a registry, a header block in a config or fixture, a `description` in a schema or manifest — and that prose is the only description anyone reads. Symptoms: a header saying "N entries" beside a list of a different length; "derived from X, regenerate, do not hand-edit" on a file with no generator; a "read by" line naming a module that no longer reads it; a caption listing what is deliberately ABSENT while one of the named things is right there in the file; a correction that landed in an assertion while the sentence above it kept the old number; a "must report 0 X" criterion nobody has run. Covers deriving the checkable claim shapes from the corpus's own prose instead of inventing a grammar, using the artefact's contents as the oracle, the date qualifier that separates a record from an assertion, and publishing the silent-field denominator. NOT for link resolution, code comments, or a rolling status document (carried-claim-rot).
---

# The prose inside the data

Checkers in a mature pipeline divide the tree by FILE TYPE. One reads the
markdown, one reads the code, one reads a registry's structure. That division
leaves a seam, and the seam is where a project keeps its most authoritative
sentences:

```
docs           checked (links, paths, numbers, citations)
code           checked (tests, types, lint)
data STRUCTURE checked (schema, required fields, referential integrity)
data PROSE     nothing
```

A `_comment` at the top of a registry is not a comment. It is the file's
specification, its provenance, its usage note and its acceptance criterion,
written in the present tense, over an author's name, and read by every human
who opens the file. Nothing re-derives it, so it drifts — and it drifts
*silently*, because the artefact under it keeps working.

**The tell that this is a real class and not a tidiness worry:** the
correction usually already exists somewhere in the same repository. In the
instance that produced this skill, a registry header said nineteen guardian
labels had been re-pointed; a test in the same tree had asserted `moved == 20`
for **thirteen rounds**, with a comment explaining that nineteen was the wrong
number. The assertion was right, was watched, went green every run — and the
sentence people actually read stayed wrong, in two more places, one of them
590 lines above the assertion in the same file.

## When to use (triggers)

- You are about to trust a data file's header for a count, a provenance, a
  reader, or a rule — or to copy one into a report or a ticket.
- A registry, fixture, manifest or generated table opens with a paragraph.
- Someone fixed a number "in the test" and the review stopped there.
- A file says `derived — regenerate, do not hand-edit` and you are about to
  hand-edit it, or to look for the generator.
- An artefact's caption tells you what is NOT in it ("A/B/C have no X",
  "empty", "no baseline", "controls: []").
- A schema `description`, an OpenAPI summary, a Terraform variable
  description, a `package.json` `description`, a fixture's `note` field.

**When NOT to use:** a rolling status document that each cycle rewrites by
copying (that is `carried-claim-rot`); link/citation resolution alone; a code
comment describing adjacent code; a claim whose subject is MEANING ("the
direction is fail-closed") rather than a lookup.

## Steps

1. **Find the seam before writing anything.** Print the file-type scope of
   every checker you already run. The gap is usually one tuple:
   `SCANNED_EXTS = (".md", ".py", ".lang", ".sh")` — no `.json`. Checkable
   outcome: you can name the constant, in a file, that excludes the artefacts.

2. **Enumerate the corpus of self-describing artefacts, and publish the
   count.** Sweep for a top-level string field of more than one clause
   (`_`, `_comment`, `note`, `description`, `summary`). This is the
   denominator for everything after it, and it is nearly always smaller than
   feared — 26 files in a 607-file tree, in the instance below.

3. **DERIVE the claim shapes from that prose. Do not invent a grammar.**
   Read all of it once and write down the sentence forms that actually
   recur. The instance yielded six, and each reduces to a lookup, not to
   parsing English: a reader claim (`read by X`), a path claim, a count
   claim, an absence claim, a derivation/regeneration instruction, a delta
   claim against a named sibling. A seventh — an executable acceptance
   criterion (`must report 0 MISPOINTED`) — is located and never run, for the
   same reason a Verification-block runner is opt-in.

4. **Make the artefact its own oracle.** Every check compares the prose
   against the file it sits in, or against a sibling the prose NAMES. Never
   against a list you maintain: derive the id set, the collection lengths and
   the element field names from the artefact, so a registry that starts
   keying its entries differently is covered the day it does
   (`derived-subject-set`).

5. **Give every rule a discriminator, and pick the discriminator from a real
   near-miss.** A count-checker that reads "Two kinds so far" over a
   three-entry map and reports a finding is a broken checker. The noun
   decides: a count is checkable only when its noun names one of the
   artefact's own collections. Write the near-miss down as a test *before*
   you like the rule.

6. **Treat the DATE as the discriminator between a record and an assertion.**
   "EMPTY **as of round 357**" is true forever; "EMPTY" is a claim about now.
   A dated claim gets its own INFO code and can never be an error. This one
   rule is what keeps the checker from declaring war on every historical
   note in the tree, and it also tells authors what to write.

7. **Prefer FIXING the prose to acknowledging it.** Three of the four
   findings in the instance were one-sentence edits made by the round that
   found them. Acknowledge only what another owner's frozen record holds, and
   pin the acknowledgement to the sha of the prose so editing the sentence
   expires it (`content-pinned-acknowledgement`).

8. **Report the silent fields.** Most prose makes no checkable claim, and
   "0 errors" over 26 artefacts must not read as "26 artefacts verified".
   Publish `coverage <checked>/<total> prose-fields` so the shapes you cannot
   reach stay a number instead of an impression.

9. **Re-run the executable claims by hand, once, and record the result.**
   A `must report 0 X` line is the highest-value sentence in any artefact and
   the least likely to have been re-run. In the instance it was FALSE — the
   command reports 5 — and had been false for nine rounds, with a recorded
   measurement of `5` sitting in a sibling file the whole time.

## Pitfalls

- **The fix that quotes the rot.** Your correction says "this used to say
  `A/B/C have no mirror`" — and the checker fires on your quotation, because
  the quotation is a fresh absence clause. Rewrite the correction so it
  *describes* the old sentence instead of reproducing it. (The corpus
  checkers in this repo carry a standing exemption for exactly this and it is
  still worth avoiding.)
- **Two nouns spelled the same.** "It has no baseline" is true of a
  mutation-campaign baseline and false of the `baseline` key in the same
  file. Before reporting, ask whether the prose's noun and the artefact's key
  are the same thing. This is the single most common false positive.
- **A subset counted as a whole.** "Five banks had been dropped" and "20 of
  the 23 pins" are counts of a *part*; only "the three pins below" is a claim
  about the collection. Partitive `of` and past tense are the two cheap
  discriminators, and both cost recall — pin the recall loss as a test
  ("a true count phrased in the past IS dropped") rather than discovering it.
- **A different container sharing a noun.** "27 skills in the corpus" is not
  a claim about this file's `skills` map. A prepositional phrase right after
  the noun re-points it.
- **Reporting the same defect twice under two codes.** A declared reader that
  does not exist is both a bad reader claim and a bad path. Report it once,
  under the code that says more.
- **Crying wolf about an unwatched claim that IS watched.** Before flagging
  "nothing runs this", check whether a test names the artefact. In the
  instance, the one live executable claim was already held open by a test —
  and flagging it would have punished the one place the discipline worked.
- **Fixing the number only where it is asserted.** The correction belongs in
  every sentence that carries it. Grep the number, not the file.
- **A checker whose own registry is invisible to it.** The acknowledgement
  file you add has a `_comment` too. Let the sweep include it; the instrument
  appearing in its own record is the cheap half of `recorder-in-the-record`.

## Verification

```bash
# 1. The seam. Name the constant that excludes the artefacts.
grep -rn "SCANNED_EXTS\|SCANNED_EXT\|include=" --include=*.py . | head

# 2. The corpus and its denominator, plus every finding.
python3 skills/skill-authoring/scripts/selfdesc_check.py --repo-root . \
    --show-acknowledged
# -> "selfdesc-check: 26 artefact(s) of 607 json file(s), 26 prose field(s),
#     0 error(s), ... coverage 1/26 prose-fields, 1/1 must-claims"
# The coverage token is the honest half: 1 of 26 fields yielded a checkable
# claim today, and "0 errors" means nothing without it.

# 3. Both halves of the discrimination, from one sentence, and the near-miss
#    that must stay quiet.
python3 -m pytest -q skills/skill-authoring/scripts/test_selfdesc_check.py
# -> 30 passed

# 4. The executable claim, actually executed (the step nobody does).
python3 languages/whence/polarity.py audit \
    state/whence/round-422/host-pins-plus-repointed.json 2>&1 | grep -i mispointed
# -> "22 directional pin(s), 5 MISPOINTED" against a header that says 0
```

- [ ] The file-type seam is named as a constant in a real file
- [ ] The artefact corpus has a published count, and it is derived by a sweep
- [ ] Every claim shape came from reading the corpus, not from imagination
- [ ] Every rule has a near-miss test that must stay silent
- [ ] Dated claims are INFO and can never be an error
- [ ] Findings were FIXED where the owner is you; acknowledged only otherwise,
      and pinned to the prose's hash
- [ ] The summary line carries `coverage <checked>/<total>`
- [ ] Every executable claim was run by hand once and its result recorded

## The instance this came from

Round 435 (skills B). `xref_check.py` had checked 6504 prose path tokens
across every `.md`, `.py`, `.lang` and `.sh` in the tree for ninety rounds,
and `SCANNED_EXTS` has no `.json`, so the ~26 000 characters of present-tense
assertion inside the tree's registries had never been read by anything. The
first sweep found four defects in 26 artefacts:

| finding | the claim | the fact |
| --- | --- | --- |
| J010 | "`host-pins-plus.json` with **nineteen** guardian labels repointed" | 20, asserted by a test since round 423, with two more `nineteen`s in prose — one of them 590 lines above that assertion |
| J006 | "CP01/CP02/**CP05** are lateral … and have no mirror" | `CP05p` is a pin eleven entries below the sentence, and its own `why` field is the argument for why CP05 is not lateral |
| J008 | "Derived from …check-pins.json; **regenerate, do not hand-edit**" | nothing has ever regenerated it, and nothing can: the `dir` column is a per-pin judgement that is in no derivation |
| J005 | "it has **no baseline**, no score and no denominator" | the artefact has a top-level `baseline` key — two nouns spelled the same, and the only one of the four that was acknowledged rather than fixed |

Three were one-sentence fixes by the round that found them. The fourth is
content-pinned in `state/known-selfdesc-drift.json` because another track owns
the record. Separately, the corpus's single executable self-claim —
"`polarity.py audit` over this file must report 0 MISPOINTED" — reports **5**
at HEAD and has since at least round 426, whose own saved artefact records the
same 5 four directories away.
