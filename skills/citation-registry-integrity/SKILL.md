---
name: citation-registry-integrity
description: Use when a codebase or docs corpus cites bare identifiers that promise a lookup — "SPEC decision 29", "house rule D-013", "rule B002", "ADR-014" — and nobody has checked those identifiers are actually DEFINED anywhere. Symptoms: an ID namespace with gaps or jumps; a numbered decision list nobody appends to while prose keeps minting new numbers; a "canonical" section present but empty; a rename that broke prose references nothing reports; each unit of work cites the registry but appending to it is separate and skippable; or you are turning on a docs checker over a corpus you do not fully own, know it will be red on day one, and need it to survive instead of being deleted. Covers declaring a registry per ID family instead of sniffing definitions, authoritative / historical / frozen scopes, and a keyed baseline that ships a red-on-day-one check green while the debt stays visible and owned. NOT for checking that markdown links or #fragments resolve, and NOT for verifying a documented claim is still TRUE.
---

# Citation-registry integrity

A citation like `SPEC decision 29` makes a promise: *there is a registry, and
29 is in it.* Nothing enforces that promise. A dangling identifier renders as
ordinary prose — no broken link, no 404, no red build — so it is invisible
until a reader goes looking and finds nothing.

The failure has a specific shape, and it is a property of how work gets
divided rather than of any one repo. Minting an ID is free and happens in the
sentence you are already writing; appending to the registry is a separate
edit to a different file, and it is the step that gets dropped when the unit
of work ends early. In a long-running or autonomous program the units end
early a lot. So the citation set grows monotonically and the registry does
not, and the gap sits in exactly the documents that read most authoritative.

The live example this skill was written from: a research workspace's language
spec had a numbered "design decisions" list with **13** entries. Its own
prose, its parser, its AST module, its value module and two test files cited
decisions **27, 28 and 29**, seventeen times. Decisions **14 through 26 were
never minted at all** — the namespace jumped. Separately, a "house rule
D-013" was cited 22 times, and the curriculum file said the house rules lived
in a `## Ground rules` section that existed and was **empty**.

That second case has a sequel worth knowing before you copy this skill's
reasoning. The empty section was written up as unrecoverable — "the body
predates this repo's git history" — and filed as the operator's decision.
It was wrong: the body was present at the initial commit and destroyed by a
later bulk commit, and the identifier was defined under a DIFFERENT heading
in the same file, so a search correctly scoped to the declared registry
found nothing. Restoring it was transcription. **Before classifying a
dangling family as "needs authorship", run the provenance check** —
`xref_check.py --provenance`, and see [[deleted-vs-never-written]]
(`skills/deleted-vs-never-written/SKILL.md`) for the general technique.

## Trigger conditions

Reach for this when any of these is true:

- Prose, comments or commit messages cite bare IDs — `decision N`, `D-013`,
  `ADR-7`, `FR-22`, `I3`, `R006` — that a reader is expected to look up.
- A numbered list in a spec or design doc is the *de facto* registry and you
  cannot tell at a glance whether it is still being appended to.
- An ID namespace has a visible gap or jump, or two documents both look like
  they might be the registry.
- Work is produced by many short-lived units (autonomous rounds, rotating
  authors, contractors) that each cite the registry but rarely extend it.
- A rename or a directory move just landed and you want to know what it
  broke in prose rather than in code.
- You are adopting any of this on a corpus that is already dirty and need
  the check to be usable on day one.

**Do not** reach for this to check markdown links or `#fragment` anchors —
those resolve mechanically and a normal link linter is the right tool. Do
not reach for it to check whether a *claim* is still true (`# expected: 45
passed`); that needs re-execution, not lookup.

## Steps

1. **Enumerate the ID families before writing any code.** One line each:
   how a citation is spelled (a regex with the bare id as group 1), which
   files may legitimately contain one, and — the load-bearing part — *which
   document and section is its registry*. Three families is typical; a
   family with no candidate registry is already a finding.
   Checkable outcome: a table with a registry named for every family.

2. **Declare the registry. Never sniff for definitions.** This is the whole
   design. A definition is an entry in the declared registry and nothing
   else; every other occurrence is a citation. The tempting alternative —
   "a line that *looks* definitional (a heading, a bold lead-in, `ID:`)
   counts as a definition" — fails in the direction that hides the bug. In
   the live corpus, a heading `## D-013 prediction ledger` in an unrelated
   report would have been read as D-013's definition and the whole family
   reported clean. **A false negative in an unwatched checker is strictly
   worse than a false positive**: a false positive gets argued with, a false
   negative gets believed.
   Checkable outcome: no function in the tool decides whether a line is a
   definition.

3. **Report the registry's STATUS, not just its contents.** Distinguish at
   minimum `no-doc` / `no-section` / `empty` / `ok`. "The registry file is
   missing", "the section was renamed" and "the section is there and has
   nothing in it" are three different bugs with three different owners, and
   collapsing them to "0 entries" throws away the diagnosis. `empty` is what
   makes a finding exact instead of heuristic: the registry was found, it
   was read, it contains nothing, therefore every citation dangles.
   Checkable outcome: the summary line prints a status word per family.

4. **Pick the registry's entry syntax narrowly.** If the registry is a
   markdown ordinal list, require the entries' actual convention
   (`N. **Bold lead-in.** …`), not bare `N.`. Documents are full of numbered
   procedure lists; counting `1. do this` invents entries and silently
   validates every citation below that number.
   Checkable outcome: a test that a plain numbered list yields zero entries.

5. **Split the corpus into three scopes, because a citation's meaning
   depends on when it was written.**
   - *authoritative* — what a reader acts on today. Findings are errors.
   - *historical* — dated records: changelogs, decision logs, per-unit
     reports, banked predictions. A reference that was correct when written
     and broke later is **history, not rot**. Count and report; never error.
   - *frozen* — vendored trees and test fixtures that contain whole snapshot
     copies of the project. Exclude from scanning entirely; a snapshot's
     references are about the snapshot.
   Checkable outcome: a live-corpus test asserting the historical count is
   non-zero, so the tier is provably reachable.

6. **Exempt the instrument from itself, and say so in the output.** The
   checker's own docstring will quote the dangling IDs it detects, and its
   test fixtures will name paths whose whole job is to be missing. Both must
   be exempt or the tool reports its own evidence as the defect. Print the
   exemption as a named blind spot with a count — an unstated exemption is
   indistinguishable from a coverage hole.
   Checkable outcome: the summary names the blind spot and its size.

7. **If you also check path references, make truncation the first rule.**
   Path-in-prose checking has one dominant false positive and it is not the
   one people expect: **a token truncated by its own delimiter**. Hard-wrapped
   markdown splits a path across a line break; a glob character outside your
   character class stops the match early so the placeholder rule never sees
   the glob it exists to suppress. Both produce a prefix that of course does
   not exist. Rule: a match is checkable only if the character *immediately
   after it* genuinely ends a path — and a newline is not one of those. Then
   add recovery rules (an abbreviated `dir/prefix` that a glob resolves) and
   impossibility rules (you cannot descend into a regular file; `logs/state`
   with both components top-level directories is prose meaning "logs and
   state"). Report skipped-vs-checked so the recall cost is visible.
   Checkable outcome: `N checked, M missing, K skipped` in the summary, with
   K explained.

8. **Adopt on a dirty corpus with a keyed baseline, not with a fix-first
   rule.** Some findings will not be yours to fix — another team owns the
   spec, the governance file is the operator's. Record them in a baseline
   file keyed `CODE:identifier`, each entry naming a reason and an **owner**,
   and exit non-zero only on citations the baseline does not cover.
   Key on the identifier, **never on file:line** — line numbers churn on
   every rewrap, so a file:line baseline goes stale within days and gets
   regenerated on autopilot, which turns a record of accepted debt into a
   rubber stamp.
   Checkable outcome: a test that a new identifier still turns the check
   red while an acknowledged one does not.

9. **Test that the baseline can expire.** Assert `baseline_keys - live_keys
   == {}`: every acknowledged entry still corresponds to a real finding. An
   entry that outlives its finding pre-accepts the *next* instance of the
   same defect, which is how accepted debt becomes invisible debt.
   Checkable outcome: that assertion exists and currently passes.

10. **Fail toward noise on every degraded path.** A missing or malformed
    baseline yields *no* acknowledgements (check stays red). A malformed
    allowlist yields *no* suppressions. An unreadable registry document
    yields `no-doc`, not "everything is fine". Every ambiguous case should
    make the tool louder, never quieter.
    Checkable outcome: a test per degraded path asserting the noisy result.

11. **Do not populate someone else's registry to make your check green.**
    Transcribing a definition that already exists verbatim elsewhere is
    repair. Writing the missing definition from its citations is authorship,
    and for a governance or spec document it is authorship of rules that
    will bind future work. Record the gap, name the owner, baseline it.

## Exact commands

```bash
# 1. Size the problem before building anything: cited vs defined.
grep -rohE '\bdecision [0-9]+\b' --include=*.md --include=*.py . \
  | sort | uniq -c | sort -rn          # every citation, by frequency
grep -nE '^[0-9]+\. \*\*' SPEC.md      # the registry's real entries

# 2. Find the gap in the namespace — a jump is the loudest possible symptom.
grep -rohE '\bdecision 1[4-9]\b|\bdecision 2[0-6]\b' . | sort -u   # empty = never minted

# 3. Confirm the registry section exists and is empty, rather than absent.
sed -n '/^## Ground rules/,$p' CLAUDE.md | head

# 4. Sweep, then adopt with a baseline.
python3 xref_check.py                      # exit 1 on NEW dangling citations
python3 xref_check.py --list               # every citation with its verdict
python3 xref_check.py --show-acknowledged  # what the baseline is covering
python3 xref_check.py --historical         # dated records, reported not errored
```

## Pitfalls

- **Definition-sniffing hides the bug it was written to find.** Any
  heuristic for "this line defines the ID" will match a heading that merely
  *mentions* it, and then reports the family clean. Declare the registry.
- **A checker that can never go green gets muted.** If adoption requires
  fixing debt you do not own, the tool is uninstalled within a week and the
  next real regression lands unseen. That is the same failure this skill
  exists to prevent, one level up. Ship the baseline in the same commit as
  the checker.
- **A file:line baseline is a rubber stamp.** It goes stale on the first
  reflow, someone regenerates it wholesale, and real new findings get
  absorbed. Key on the identifier.
- **The historical scope is not a way to be quiet.** It exists because a
  dated record correctly describes a past state. If you find yourself
  widening it to reduce noise, you are relabelling rot as history — check
  that the file really is append-only and dated.
- **The truncated token, twice.** A hard line wrap and an out-of-class glob
  character produce the same artifact by different routes, and a placeholder
  suppression list catches neither, because the placeholder is in the part
  of the token the regex never reached.
- **`lstrip("./")` is a character class, not a prefix strip.** It turns
  `.venv/x` into `venv/x`, which then fails to match a frozen-directory name
  and quietly pulls a vendored tree into the sweep. Strip `"./"` by slicing.
  (Found by comparing the scanned-file count between two runs, not by a
  test — watch that number.)
- **Excluding a snapshot directory by substring excludes real directories
  too.** A rule that freezes `state/swe` wherever the string appears also
  freezes an unrelated `state/swe` nested under some other top-level
  directory. Anchor snapshot exclusions at the repo root; match only true
  basenames (`__pycache__`, `.git`) anywhere. (This very pitfall's first
  draft named the example path literally, and the checker flagged it inside
  the hour — prose about a path that does not exist is still prose about a
  path that does not exist.)
- **A hypothetical ID written in prose is a real citation.** Documentation
  about the checker is the likeliest place to mint one: "…and still flags the
  first citation of a decision 30" put a fourth dangling identifier into the
  corpus headline within minutes of the tool going green. Same defect as the
  illustrative path, one family over. Describe the case without naming a
  number, or the docs about the rot become rot.
- **Registry mismatch between citation and entry type.** If citations are
  strings (`D-013`) and the registry reader returns ordinals (`13`), nothing
  can ever match and populating the registry will not clear the finding —
  the tool becomes unsatisfiable. Test the fix, not just the finding: write
  a case that populates the registry and asserts the family goes silent.

## Verification

```bash
cd skills/skill-authoring/scripts
python3 -m unittest test_xref_check      # expected: Ran >= 112 tests, OK (round 459)
cd ../../.. && python3 skills/skill-authoring/scripts/xref_check.py
# expected: "0 NEW", exit 0; X001 registry ok 13 entries, X002 registry empty
python3 -c "import json;d=json.load(open('state/known-dangling-citations.json'));print(len(d['citations']))"
# expected: 4
```
- [ ] Every ID family names a registry document+section, and the summary
      prints that registry's status word
- [ ] No function in the tool decides whether a line "looks like" a definition
- [ ] The summary prints checked / missing / skipped for path references, and
      names the self-exemption blind spot with a count
- [ ] The baseline is keyed `CODE:identifier`, every entry names an owner, and
      a test asserts no entry outlives its finding
