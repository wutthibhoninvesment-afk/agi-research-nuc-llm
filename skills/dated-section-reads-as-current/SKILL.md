---
name: dated-section-reads-as-current
description: Use when a long-lived document is organised into sections named for a version or date — a SPEC with `## v0.12` … `## v0.41`, a CHANGELOG whose entries describe mechanism, an ADR log — and prose inside one is READ as how the system works today. Symptoms - somebody reasons from a sentence in an old section and is wrong; a bullet in `## vN` says "X desugars to Y" in the present tense while `## vM` (M > N) removed that desugaring; a section carries one dated correction note about ONE bullet and nothing swept the rest; a code comment says "vA-vB did it the old way" and no document sentence agrees. The move is to use the version RANGES written elsewhere as an index instead of detecting tense: a range claims a behaviour held from A to B and no longer, and a dated section in that window sharing the claiming sentence's identifiers must carry a staleness marker. Covers scoping the marker to the SENTENCE not the section, and replaying against the pre-correction document to prove recall.
---

# A section named for a version is a date stamp nobody reads as one

Long-lived design documents grow by appending a section per release. Inside
`## v0.12`, a sentence written in 2024 is *correct*: it describes v0.12. Read
in 2026 it is a description of the system, because nothing about the prose
says otherwise — the heading is a date stamp and headings are furniture.

This is worse than an ordinary stale comment, because the sentence is not
wrong where it sits. Nobody can fix it by "reading more carefully": the
reader has no signal. In the program this skill comes from, one such bullet
cost a round four of its nine predictions — the round banked on a document
instead of on the parser, and the document was right about a version four
releases old.

## Trigger conditions

- A document has ≥10 sections whose headings name a version, release, sprint
  or date, and its sections describe MECHANISM ("desugars to", "is erased at
  parse time", "compiles only call-free subtrees") rather than only listing
  changes.
- Somebody has just been wrong about current behaviour and the sentence they
  read is in a dated section. This is the trigger that actually fires — the
  cost is paid before anybody looks.
- A section carries a dated correction note ("Stale-note correction (round
  240)", "Updated 2025-06") attached to ONE bullet. That note is evidence
  that the section has been found wrong once and evidence that nothing swept
  the rest of it.
- A source comment states a WINDOW — `# v0.12-v0.18 instead PREPENDED …`,
  `// removed in 3.4` — and you cannot say whether the document agrees.

## Steps

1. **Find the index, and do not build a tense detector.** English present
   tense is not a closed class; a grammar-guessing checker is a worse
   instrument with a more confident voice. The usable signal is a version
   RANGE written anywhere in the repo. Count them first — if there are none,
   this technique does not apply and you should say so rather than proceed.

   ```bash
   grep -rnoE "v[0-9]+\.[0-9]+(\.[0-9]+)?\s*[-–—]+\s*v?[0-9]+\.[0-9]+" \
        --include=*.md --include=*.py . | wc -l
   ```

   Checkable outcome: a number. In the source corpus it was 23, small enough
   that every finding could be hand-read — which is what made the precision
   number below honest rather than asserted.

2. **Take each range statement's subjects from the CLAIMING SENTENCE, not
   its paragraph.** A range sits inside a fourteen-line comment about five
   other things. Taking the paragraph took five extra identifiers, each of
   which matches thirty unrelated sections. Split on sentence boundaries
   AFTER stripping each line's comment/bullet furniture — a `#` between a
   full stop and the next word stops every splitter — and remember that in
   this kind of prose a sentence very often OPENS with the version
   (`… for a -> Type. v0.12-v0.18 erased …`), so a splitter that requires a
   capital letter never fires on the one shape you care about.
   Checkable outcome: for one range you have read by hand, the extracted
   subject set contains the identifier the claim is about and none of the
   identifiers from the neighbouring sentences.

3. **Scope the STALENESS MARKER to the block, not the section.** This is the
   step that decides whether the instrument works at all. A marker is a
   property of a sentence. A 132-line section that carries one dated
   correction about one bullet will, under section-scoped marking, be exempt
   forever — and the exemption is invisible, because the tool still prints
   dozens of findings elsewhere and looks healthy.
   Checkable outcome: a section with two bullets, one marked and one not,
   yields exactly one finding.

4. **REPLAY against the document as it was before a correction you already
   know about.** This is the falsifier, and without it you cannot tell a
   working instrument from a confident one.

   ```bash
   git show <commit-before-the-fix>:path/to/SPEC.md > /tmp/spec-old.md
   python3 specstale.py --spec /tmp/spec-old.md --top 0 | grep ":<known-line>:"
   ```

   Checkable outcome: the instrument names the block that a previous
   commit's message says was stale. Steps 2 and 3 were both found this way
   — each shipped a clean, plausible answer that omitted exactly that block.

5. **Narrow the WINDOW before you narrow anything else, and measure every
   narrowing against step 4.** A behaviour is SPECIFIED at the range's low
   end; the sections above it merely lived with it, and they share the whole
   vocabulary, so they are where every false positive comes from. Measured
   on the source corpus: window `all` → 67 findings, recall 1/1; window
   `low` → 14, recall 1/1. Two other narrowings were tried and REJECTED for
   killing recall — a minimum-overlap of 2 (67 → 6, recall 0/1) and
   rarity-weighted ranking alone (the true positive ranked 46 of 67).
   Checkable outcome: a table with one row per narrowing, carrying BOTH the
   finding count and whether the known-true finding survived. A narrowing
   with only the first column is a quiet checker, not a better one.

6. **Hand-read every survivor, and publish the precision.** The population
   is small by construction. Reading all of it is the difference between a
   measurement and a headline. On the source corpus: 11 blocks read, 4 true
   positives, 7 false — **36% precision**, and the 4 named three functions
   that existed nowhere in the tree.
   Checkable outcome: each finding is recorded as TRUE or FALSE with the
   command or file that decided it.

7. **Fix the true positives in the document, in its own correction style.**
   Past-tense the verb and add the marker the document already uses. Do NOT
   silence them in the baseline; a suppressed true positive is the original
   defect with a registry entry attached.
   Checkable outcome: re-running the instrument marks them.

8. **Expect the fix to widen the search, and say so.** Every correction you
   write is itself a new range statement, so the index grows as you use it.
   In the source corpus this took 14 statements to 17 and surfaced a FOURTH
   true positive that only appeared after the first three were fixed. Run to
   a fixed point, and report the loop rather than hiding it.

9. **Content-pin the false positives, never line-pin them.** A document line
   number is not durable — the corrections in step 7 moved every line below
   the first one. Key each acknowledgement on the version plus a digest of
   the block's first line, and make the tool report an acknowledgement that
   matches nothing (see [`content-pinned-acknowledgement`](../content-pinned-acknowledgement/SKILL.md)).
   Checkable outcome: an entry with a deliberately wrong digest is reported
   as expired. Assert that with a HAND-BUILT one; an expiry control whose
   only evidence is an empty result cannot be told from one that never
   fires.

10. **Give every acknowledgement the reason, not the verdict.** "Not stale"
    is a verdict. "The only tie to the window is the phrase *the same
    classification `typed` uses*, and v0.19 removed the desugaring, not the
    builtin — verified against `b_typed` at HEAD" is a reason a later reader
    can check. Enforce a minimum length in the test if you have to.

## Pitfalls

- **Building the tense detector.** It is the obvious move and it is the
  wrong one. The section-is-in-a-window test does the work; the tense is
  what a human then confirms.
- **Marking a section instead of a bullet.** See step 3. This failure is
  silent and it grows: the more a section has been corrected, the more
  permanently exempt it becomes.
- **Tuning until the output is quiet.** Three of the four narrowings tried
  on the source corpus reduced the count and deleted the founding case. A
  count is not a quality metric without a recall column beside it.
- **Treating "0 findings" as clean without a positive control.** The first
  draft's 34 findings looked like a working instrument. It was not.
- **Assuming the strongest overlap is the strongest evidence.** The single
  highest-scoring false positive shared the rarest possible term — the exact
  identifier the range claim is about — and was still false, because it
  described the REPLACEMENT mechanism one section early. Sharing the subject
  is not sharing the claim.
- **Silently capping the report.** If you print a top-N, print how many you
  cut and how to see them.
- **Naming your checker's private rule codes in the skill.** A SKILL is a
  portable technique, and another repo's reader cannot resolve a bare
  three-letter-and-digits code. This file cited one of its own, a citation
  checker was right to call it dangling — and the first draft of THIS bullet
  cited it again while warning against it. Describe the finding, not its
  code.
- **Believing the blind spot is empty.** A range whose low end has no
  section at all is unreachable by this rule. Print those (the source
  corpus had 8) rather than letting a green run imply full coverage.

## Verification

Against `languages/whence/` in this repo:

```bash
# 1. the index exists and is small enough to hand-read
cd languages/whence && grep -rnoE \
  "v[0-9]+\.[0-9]+(\.[0-9]+)?\s*[-–—]+\s*v?[0-9]+\.[0-9]+" SPEC.md | wc -l

# 2. the instrument is green, and its summary prints the blind spot
python3 specstale.py --strict

# 3. what a fresh auditor sees — the baseline is a claim, not furniture
python3 specstale.py --no-ack --top 0

# 4. THE test: the narrowing that keeps recall vs the one that does not
python3 specstale.py --window all  --no-ack | tail -1
python3 specstale.py --window low  --no-ack | tail -1

# 5. the expiry control fires on a hand-built wrong key, and the two
#    scope errors stay fixed
python3 -m pytest -q tests/test_specstale.py
```

The instrument is working when step 2 exits 0 while still printing its
blind-spot lines, step 4's two summaries differ in BOTH directions
(more findings, same recall), and step 5 passes
`test_an_acknowledgement_matching_nothing_expires_loudly` and
`test_the_sibling_bullets_marker_does_not_cover_it`.
