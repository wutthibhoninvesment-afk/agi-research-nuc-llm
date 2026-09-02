---
name: registry-density-not-membership
description: Audit an id namespace (decision numbers, ADR/RFC ids, error codes, migration versions, ticket prefixes) for DENSITY and for who assigns the next number — not just for whether every cited id resolves. A membership check answers "is this id defined?" from a set, and a set cannot see a duplicate, an undeclared hole, a definition written outside the registry, or a definition nobody cites. Trigger when a checker reports a dangling/unresolved identifier, when you are about to mint the next number in a numbered series, when one fact is written in two places (a registry entry and the prose section it summarises), or when a next-step says an identifier "is cited but not defined".
---

# A registry that mints ordinals is a dense range

A membership check asks *is every id someone CITES defined?* and answers it
by building a `set` of registry ids and testing `in`. That is the right
question about citations and the wrong question about the namespace.

**Everything a set forgets, it forgets:**

| forgotten | what it looks like when it bites |
|---|---|
| a duplicate id | two definitions, one meaning, arguments about which |
| an undeclared hole | a reader assumes the gap is deliberate; nobody knows |
| a definition written OUTSIDE the registry | the registry's max is stale, and the next minter collides |
| a definition nobody cites | dead weight nobody can retire, because nothing proves it is dead |

The one that bites hardest is the third, because **the registry is usually
the only site that assigns the next number.** A definition written somewhere
else does not just miss a sentence — it leaves a taken number looking free.
The failure lands rounds later, in a different file, as a disagreement about
what the id *says*, and nothing points back at the omission.

Round 464 found this live. Round 462 wrote `### Decision 56 …` into
`languages/whence/SPEC.md`'s prose and did not append entry 56 to the
registry list. `xref_check` DID report it — but only because the section
heading contains the words `Decision 56` and the citation pattern is *the
word "decision" followed by digits*. **The definition was caught by being,
accidentally, a citation of itself.** Titled the way the four previous decisions were titled
(`## v0.42 (round 446, language C) — …`), the id would have appeared nowhere
in citable text and no instrument in the tree would have said a word.

## When this triggers

* A checker reports `dangling`, `unresolved identifier`, `cited but not
  defined`, `no such id`, or an "acknowledged debt" file of such ids.
* You are about to **mint** the next id in a numbered series — a design
  decision, an ADR, an RFC, an error code, a migration version, a lint rule.
* One fact is written in two places: a one-line registry entry and the long
  prose section it summarises; a `CHANGELOG` line and a version heading.
* A next-step says an id namespace "has a gap" or "jumps".
* Two parsers read the same registry (a checker's and a tool's) and nothing
  compares them.

## Steps

1. **Enumerate the definition SITES, plural, before writing any check.**
   Grep the document for every form an id definition has ever taken. In a
   long-lived document the convention drifts: an ordinal list item, a
   `### <Name> N` heading, a table row, a code constant. The registry is
   whichever one the tooling reads; the others are where authors actually
   write.

   ```sh
   grep -nE '^[0-9]+\. \*\*' DOC.md | wc -l      # ordinal registry entries
   grep -nE '^#{1,6} .*\b<Name> +[0-9]+' DOC.md  # prose-section definitions
   ```

2. **Compute the union, and make `next` a command.** The next free id is
   `max(union of all sites) + 1`, walked past any declared reserved range —
   never `max(registry) + 1`. Ship it as a subcommand so no author has to
   know there is more than one site.

   ```python
   def next_free(text):
       ids = registry_ids(text) | section_ids(text)     # every site
       n = max(ids) + 1 if ids else 1
       while any(lo <= n <= hi for lo, hi in reserved(text)):
           n += 1
       return n
   ```

3. **Check DENSITY, which needs no citations at all.** For every `n` in
   `1..max`, require a registry entry or a *declared* reserved range.
   Membership needs someone to ask; density does not — this is what makes
   the check independent of whether anyone happens to cite the id.

4. **Report a hole that is a definition elsewhere as its OWN finding, and
   name the consequence in the message.** "Decision N is missing" is a
   shrug. *"…the registry's max is 55, so the next round to mint a number
   reuses 56"* is an instruction. One finding per fact: an id minted only in
   prose is a hole AND an outside-definition; emit the louder one only.

5. **Check duplicates explicitly, because the set-based reader provably
   cannot.** Pin that with a test — build the document twice, once with the
   duplicate and once without, assert the id SETS are equal and the finding
   sets differ. That test is the argument for the whole file.

6. **Cross-check the coordinates the sites share.** If a registry entry
   carries `(v0.20, round 348)` and the section it points at is headed
   `## v0.20 (round 348, …)`, that is one fact written twice and checked
   never. Match on the exact label, compare the number, and report a
   mismatch. Round 464 ran this over every entry in a 464-round-old
   registry and found **0** — a real result: the tag discipline was perfect and the *append* discipline was
   what failed. A checker that finds nothing has still measured something,
   if it would have fired.

7. **Count the ORPHANS — ids defined and cited nowhere.** The inverse of a
   dangling citation, and the half a membership check structurally cannot
   see. Exclude the id's own definition span; count a cross-reference from
   another entry as a real reader. Keep it a WARNING: an uncited definition
   is unloved, not wrong.

8. **Pin your parser against the existing one.** If a checker already parses
   this registry, assert your id set equals its id set in a test — do not
   import its regex. Two parsers that agree by TEST stay honest; two that
   agree by import only agree about the import.

9. **Fix the instance and the mechanism in the same round.** Append the
   missing entry, then re-run the ORIGINAL checker and quote its before/after
   line. The count moving is the proof; your own tool passing is not.

## Pitfalls

* **Writing a hypothetical id into the checker's own file.** If the tool
  lives inside the citation scope it audits, `<Name> 57` in a docstring is a
  live dangling citation. Round 464's first draft did exactly this in the
  paragraph warning against it, and the module reported itself on its first
  run. Write `<Name> N`, and pin it: a rule stated in prose and not held by
  a test is a rule its own author breaks in the sentence that states it.
* **Treating "the checker caught it" as "the checker covers it."** Ask *what
  made this visible?* If the answer is a coincidence of the regex — the
  definition happening to look like a citation — the class is uncovered and
  the next instance will be silent.
* **Renumbering to close a gap.** A gap cited from N authoritative sites is
  cheaper to declare reserved than to close. Declare it in a form the
  registry parser does NOT count as an entry, so a citation of an id inside
  it still dangles.
* **Citing a definition by `file:line`.** Any insertion above it invalidates
  every such citation. Round 464's own repair moved the section it cited 29
  lines down the file, inside the same round. Cite by section.
* **Making the orphan count an ERROR.** It goes red for correct work on day
  one and the whole checker gets uninstalled. Warnings ride in the summary
  line; errors drive the exit code.
* **Exempting old entries with an allowlist.** Use a numeric FLOOR
  (`id >= 27`) so the exemption expires for every future entry
  automatically. An allowlist has to be edited to keep working, which means
  it will not be.

## Verification

Run from the repo root. Both must exit 0.

```sh
# 1. every finding fires on a document built to trigger it AND stays silent
#    on the near-miss beside it; the two registry parsers are pinned equal
cd languages/whence && python3 -m pytest -c pytest.ini -q tests/test_specreg.py

# 2. the live registry is dense, collision-free, and its tags agree with the
#    sections they point at; `next` derives from every site
cd languages/whence && python3 specreg.py audit && python3 specreg.py next
```

Expected from (2): `specreg: 43 registry entr(ies), 9 prose section(s), …
reserved 14-26; next free is 57` and `specreg: 0 error(s), 5 warning(s)`,
then `57` on its own line. The warnings are S006 orphans (decisions 4, 5,
10, 11 and 12 are cited nowhere outside their own entries) and are carried
on purpose.

Cross-check against the checker this one complements — the count moving is
the proof:

```sh
python3 skills/skill-authoring/scripts/xref_check.py 2>&1 | grep X001
```

Expected: `43 entries; … 1 dangling id(s): 14`. Before round 464's repair
it read `42 entries; … 2 dangling id(s): 14, 56`.
