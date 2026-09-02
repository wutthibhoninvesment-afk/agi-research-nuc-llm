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

8. **Report the silent fields — and count LOOKUPS, not findings.** Most
   prose makes no checkable claim, and "0 errors" over 26 artefacts must not
   read as "26 artefacts verified". Publish `coverage <checked>/<total>`.

   **The trap, and it is the easy implementation.** `checked = total -
   silent`, with `silent` meaning "produced no finding", is the FINDING COUNT
   wearing coverage's name. A claim that was looked up and found CORRECT
   produces no finding and is published as uncovered, so the token can only
   rise when the corpus gets WORSE and reads `0/N` exactly when everything is
   clean. This repo shipped that for twelve rounds and its own next-steps
   file read `coverage 1/26` as "one of 26 fields yields a checkable claim",
   which is what it was meant to mean and not what it measured. Count a field
   as covered when at least one rule RAN a lookup in it. Count a rule's
   deliberate declines (partitive, past tense, wrong container) as neither —
   counting refusals as coverage is the same defect upside down. Checkable
   outcome: a test asserts the two numbers DIFFER on your corpus.

9. **Re-run the executable claims by hand, once, and record the result.**
   A `must report 0 X` line is the highest-value sentence in any artefact and
   the least likely to have been re-run. In the instance it was FALSE — the
   command reports 5 — and had been false for nine rounds, with a recorded
   measurement of `5` sitting in a sibling file the whole time.

10. **Match field names by SHAPE, not by a list of names.** An exact-name
    tuple (`_`, `_comment`, `_note`, …) misses the generated idiom every
    append-only registry uses: `_round_446_note`, `_round_349_addendum`,
    `_2024_11_migration_note`. A round appends its reasoning under a NEW key
    rather than editing the one below it, so the names cannot be enumerated
    and the newest one — the only one describing the file as it stands — is
    always the one your tuple has not been taught yet. Checkable outcome: the
    sweep's field count is derived by a regex over key names, and a test
    asserts a lower bound rather than a number.

11. **A nested field's subject is its PARENT, not the file.** When you widen
    the sweep to depth, carry the containing node with each field and give
    each rule its right denominator. A `why` inside one entry describes that
    entry; counting "the five reasons" in it against the file's 26-entry map
    invents a finding on every nested field you reach. Split the rules by
    scope — SUBJECT (counts, absence, element deltas), TREE (paths, readers,
    commands: a path is the same claim at any depth), ARTEFACT (nothing reads
    this file; nothing regenerates it — de-duplicate these, one per file
    however many fields repeat them). Done this way, a nested element with no
    sub-collections has no nouns and the subject rules go quiet *by
    construction*, with no exclusion list to maintain.

12. **Choose the depth population by MEASURING what a wider rule pulls in.**
    Accepting every prose-shaped key at any depth reached 1415 fields here;
    dropping just `description` and `summary` removed 803 of them — the key
    names in captured API payloads and in mirrors of other files' metadata,
    text the repo RECORDED rather than ASSERTED. Do not instead gate on "the
    artefact has a top-level self-description": that predicate is convenient,
    has nothing to do with whose prose it is, and would have silently dropped
    359 of this repo's own run records.

13. **Date a claim by its KEY, and keep the newest key on the hook.** A
    round-stamped note is a claim about the artefact AT THAT ROUND, and
    today's file cannot falsify it — these registries are not append-only in
    practice, entries leave when their debt is paid. So an OLDER stamp is a
    record (INFO). The NEWEST stamp is not: nothing in the artefact says
    anything happened after it, so it is the file's most recent description
    of itself and must be checked as an assertion about now. Dating *every*
    stamped field is the tempting simplification and it suppresses the only
    finding worth having — in this repo, a count that had been wrong for ten
    rounds and was being priced in dollars. Derive "newest" from the artefact,
    never from a configured list. Its cost, which belongs in the code: it is
    a proxy for "nothing changed the collection since", and a round that edits
    without stamping makes the newest older note wear the blame. That is the
    right direction — the false report is repaired by adding a note.

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
- **An empty collection is not a collection.** `if isinstance(v, (list, dict))
  and v` reads as harmless tidying and deletes exactly the case drift travels
  toward: a list DRAINED to zero leaves the sentence that counted it standing,
  with no noun left for the count rule to compare against. In this repo the
  instance was the checker's OWN acknowledgement registry — "only the one
  entry … is here" over `"acknowledged": []`, for ten rounds.
- **A number word that is also a negation.** `no` and `zero` belong in your
  number table, because "no pins" is a real count of a CONTAINER. Before an
  ATTRIBUTE name they are English negation — "no edit text, no witness" means
  the change touched neither — and reading them as 0 made both live hits of a
  new rule false. Exclude them for the attribute rule only, and pin the recall
  you lose as a test.
- **A sentence splitter is not a claim's scope.** When rule A hands a sentence
  to rule B ("this one names a sibling, it is the delta rule's"), ask what
  each half is a property of. WHICH file this one derives from is a property
  of the DOCUMENT; a delta VERB is a property of the sentence. Scoping both to
  the sentence mis-fired here on a header that named its sibling 200
  characters and one split before the count it governed.
- **A count in the docstring of the count checker.** The first draft of this
  round's fix wrote "the 17 `_round_NNN_note` fields" into a module docstring
  and a test docstring — a hand-maintained count of a collection that grows
  one entry per round, i.e. the exact claim the tool exists to catch. Say
  "every", and assert lower bounds in tests.

## Verification

```bash
# 1. The seam. Name the constant that excludes the artefacts.
grep -rn "SCANNED_EXTS\|SCANNED_EXT\|include=" --include=*.py . | head

# 2. The corpus and its denominator, plus every finding.
python3 skills/skill-authoring/scripts/selfdesc_check.py --repo-root . \
    --show-acknowledged
# -> "  fields: 612 of 663 nested below the artefact root; 136 claim(s)
#     checked in 72 field(s), 6 field(s) yielded a finding"
# -> "selfdesc-check: 46 artefact(s) of 622 json file(s), 663 prose field(s),
#     0 error(s), 0 warning(s), 7 info, 0 acknowledged;
#     coverage 72/663 prose-fields, 2/2 must-claims"
# TWO numbers, and they must be different ones. 72 fields had a lookup RUN in
# them; 6 produced a finding. Publishing the second under the first's name is
# step 8's trap, and this line read "coverage 0/28" for twelve rounds because
# the corpus was CLEAN.

# 3. Both halves of the discrimination, from one sentence, and the near-miss
#    that must stay quiet.
python3 -m pytest -q skills/skill-authoring/scripts/test_selfdesc_check.py
# -> 47 passed

# 4. The scope split: a nested field is checked against its own parent.
python3 -c "import sys; sys.path.insert(0,'skills/skill-authoring/scripts'); \
import selfdesc_check as S; a,_n,_u,_s = S.scan_tree('.'); \
print(sum(1 for x in a for f in x.fields if f.depth), 'nested,', \
sum(1 for x in a for f in x.fields if f.round is not None), 'round-stamped')"
# -> "612 nested, 23 round-stamped"
# Both were zero before the sweep matched field names by SHAPE and carried a
# subject with each field.

# 5. The executable claim, actually executed (the step nobody does).
python3 languages/whence/polarity.py audit \
    state/whence/round-422/host-pins-plus-repointed.json 2>&1 | grep -i mispointed
# -> "audit: examples/self_host.lang - 22 directional pin(s), 0 MISPOINTED,
#     0 unlocatable, 1 precondition-broken, 4 undecided, 0 strict-violation"
# Re-derived round 447. This block said "5 MISPOINTED" for seven rounds after
# round 440 REPLACED the criterion; the number was true when written and is
# the reason step 9 says run it, not quote it.
```

- [ ] The file-type seam is named as a constant in a real file
- [ ] The artefact corpus has a published count, and it is derived by a sweep
- [ ] Every claim shape came from reading the corpus, not from imagination
- [ ] Every rule has a near-miss test that must stay silent
- [ ] Dated claims are INFO and can never be an error
- [ ] Findings were FIXED where the owner is you; acknowledged only otherwise,
      and pinned to the prose's hash
- [ ] The summary line carries `coverage <checked>/<total>`, and `<checked>`
      counts lookups that RAN, not findings — a test asserts they differ
- [ ] Field names are matched by SHAPE, so the generated round-stamped idiom
      is swept and a new one needs no edit
- [ ] Every nested field carries the SUBJECT it describes, and the rules are
      split into subject-scoped / tree-scoped / artefact-scoped
- [ ] The newest round-stamped note is checked as an assertion; older ones are
      records
- [ ] Empty collections are still collections
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

Three were one-sentence fixes by the round that found them. The fourth was
content-pinned in `state/known-selfdesc-drift.json` because another track owned
the record; round 437 fixed that prose too, and the registry has been empty
since. Separately, the corpus's single executable self-claim —
"`polarity.py audit` over this file must report 0 MISPOINTED" — reports **5**
at HEAD and has since at least round 426, whose own saved artefact records the
same 5 four directories away.

## What round 447 added, and why each half was a different gap

Round 447 (skills B) came back to it for two next-steps items round 435 had
written about its own checker, both twelve rounds old. Both were real and
neither sentence was quite right, which is the useful part.

**"It sweeps TOP-LEVEL prose fields only."** It swept six literal field NAMES.
Every `_round_NNN_note` in the registry that item cited is top-level and was
skipped anyway. Reading a name gap as a depth gap points at the wrong fix, and
both turned out to exist with different repairs (steps 10 and 11). 28 prose
fields became **663** — 51 top-level, 612 nested — across 27 → **46**
artefacts.

**"`coverage 1/26` is the honest headline: one of 26 self-descriptions yields
a checkable claim today."** The token was `prose_fields - silent_fields` and
`silent` meant "produced no finding", so it was the error count under another
name. On a clean corpus it read `0/28`. Step 8 now carries the trap.

**The yield.** Reading a `_round_NNN_note` for the first time found a count
that four consecutive rounds had been re-quoting into a status file and
pricing in dollars: an unprobed-skills batch carried as `SIXTEEN` against a
map holding **26**. The undercount decomposed exactly — one note counted the
fourteen entries its own round registered and dropped the nine already there,
and a later entry was never counted at all. Priced from the batch's own 91
trigger cases at the rate a previous whole-batch payment measured, the real
figure is **$26.57** against the **$16.35** the carried number implies.

**The rule that made that finding survivable** is step 13. Dating every
round-stamped field would have demoted it to INFO along with five genuine
historical records; keeping only the NEWEST stamp on the hook separates them,
and the separation is derived from the artefact rather than configured.

**And the new rule's first two live hits were both false**, in two independent
ways now in the pitfalls: a number word that is also a negation, and an
exclusion scoped to a sentence when the thing it looked for was a property of
the document.
