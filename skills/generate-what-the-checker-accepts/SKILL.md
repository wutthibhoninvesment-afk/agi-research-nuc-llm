---
name: generate-what-the-checker-accepts
description: Use when a checker keeps going red for the same class of missing record and the repair is a HAND-WRITTEN entry -- a registry line, a ledger entry, an allowlist row -- that only one team or one rotation slot ever writes. Symptoms: the same lint reopens after every closure; its error count grows monotonically between closures; the fix is always "somebody adds the entry"; a --suggest or scaffold mode proposes half-filled records nobody can commit; the diagnosis has been written in prose three times and no tool came out of it. Covers proving the arrival rate outruns the repair rate first, reading the checker's own ERROR predicates as a spec of a valid record and running them FORWARDS to derive one, making REFUSAL a first-class output so a generator cannot launder a debt, and pinning that refusal against the known-bad case in the live corpus. NOT for a checker nothing invokes (unrun-checker-latency) or a red nobody routes to an actor (finding-must-reach-an-actor).
---

# A checker already knows what a valid record looks like — make it write one

A checker that ERRORS on a missing or malformed record is a specification
with the arrows pointing the wrong way. It can say *this entry is invalid and
here is which clause it fails*; the same clauses, run forwards over the
material the entry would describe, say *here is a valid entry*. Almost
nobody turns them around, and the cost is paid in a permanently red check.

The reason it stays unturned is that the red looks like a discipline problem.
It is an arithmetic problem:

    defects ARRIVE at   R  per unit of work
    records are WRITTEN at r  per unit of work, by the one owner who runs the check
    if R > r, the check is red forever and its count grows monotonically

In the episode behind this skill, a prediction bank arrived roughly once per
round; ledger entries were written once per six-round rotation, by the one
track that runs the corpus check. Six closures, six reopenings, the error
count growing by one per round in between. Four rounds wrote that diagnosis
down in prose. None built anything from it, because writing one entry by hand
is a four-clause job — the quote must be present in the cited file, present
exactly once, matched by no other scope, and be a scoring rather than a
promise of one — and nobody does a four-clause job for bookkeeping.

## When this triggers

- A lint, audit or CI check reopens after every closure, and every closure
  was somebody hand-writing entries for work other people did.
- The check's error count grows by a predictable amount per unit of work
  (per PR, per round, per service onboarded) between closures.
- A `--suggest` / `--scaffold` / `--init` mode exists and its output has
  `"?"`, `null` or `TODO` in the fields that matter, so using it costs as
  much as not using it.
- The obligation is discharged in two phases and only the first leaves an
  artifact — the record of the second is what keeps going missing.
- The same recurring diagnosis appears in three or more comments, registry
  `why` fields or post-mortems, each rewritten by a different author.
- A checker's error message says nobody can tell whether X was done, and you
  can tell, in ten seconds, by opening one file.

**Not this skill** when the checker simply never runs (`unrun-checker-latency`),
when it runs and is read by nobody who can act (`finding-must-reach-an-actor`),
or when there is no ledger of the obligation at all yet (`obligation-ledger`).

## Steps

1. **Prove the arithmetic before you build.** Count how many instances of
   this finding arrived per unit of work, and how many were repaired per
   unit, over enough history to see both. A generator for a one-off is waste;
   a generator for `R > r` is the only thing that ends the recurrence.
   Checkable outcome: two rates, with the commands that produced them, and a
   statement of which is larger.

   ```bash
   # arrivals: how many entries did each closure have to write?
   git log --format='%h %s' -- <registry> | head -20
   git log -S'"NNN": {' --oneline -- <registry> | tail -1   # per instance
   ```

2. **Read the checker's ERROR codes as a record specification.** List every
   code that can fire on the record class, and write next to each the
   property a valid record must have. Do not paraphrase from the docstring —
   read the branch that raises. The list IS your accept-predicate.

   In the worked example: present in the cited file, present exactly once,
   matched by no scope the entry does not name, carrying its own outcome
   rather than a pointer to one, not crediting a different owner, and long
   enough to locate.

3. **Run the predicates forwards over the material.** For each candidate
   piece of material — each line, each row, each config block — apply every
   predicate. What survives is, by construction, a record the checker
   accepts. Rank the survivors by whatever the codes are a proxy for
   (usually: information content) and take the top one.

4. **Make REFUSAL a first-class output, and design it before the happy
   path.** When no candidate survives, the generator must emit a record that
   says the obligation is still OPEN, name what it searched, and name what it
   failed to find. This is the whole safety property: a generator that always
   produces a satisfying record is a mute button with a CLI. Checkable
   outcome: the refusal path has its own return value, its own test, and its
   own prose in the emitted record.

5. **Refuse to invent the fields that are judgements.** Ownership,
   attribution, severity and deadlines are decisions, not derivations. Emit
   them empty and make the WRITE path refuse an empty one with a message
   naming the flag that supplies it. A generator that guesses an owner
   produces records that are wrong in the one field anybody will act on.

6. **Pin the refusal against the known-bad case in the LIVE corpus.** Every
   such checker has one instance everybody already knows is genuinely
   outstanding. Write a test that runs the generator against that real
   instance and asserts it refuses. A fixture proves the code path exists;
   the live case proves the predicate is strong enough for the material it
   will actually meet.

7. **Round-trip the output through the checker.** Generate, write, re-run
   `findings()`, assert zero errors for that record. A generator whose output
   the checker rejects is worse than no generator: it manufactures a red the
   next owner inherits and cannot attribute.

8. **Match the target file's own serialisation, byte for byte.** Before
   writing, prove that re-serialising the untouched file reproduces it
   exactly, and pin that in a test. Adding three entries with the wrong
   `indent` or `ensure_ascii` rewrites every line and buries the change.

   ```bash
   python3 - <<'EOF'
   import json; p = "<registry>"
   raw = open(p, encoding="utf-8").read()
   for kw in (dict(indent=1), dict(indent=2), dict(indent=2, ensure_ascii=False)):
       print(kw, json.dumps(json.loads(raw), **kw) + "\n" == raw)
   EOF
   ```

9. **Put the prompt where the author still is.** The generator removes the
   cost; something still has to ask. The check that found the gap runs after
   the author has gone, so route a cheap tier of it into the author's own
   loop — a pre-commit warning, a PR template check, an editor task. Fire on
   the artifact that means *the work is finished*, not on the one that means
   *the work has started*, or you will warn at the one person doing it right.
   This step is `finding-must-reach-an-actor` applied, not new; the fail-open,
   never-block rule is that skill's and it holds here.

10. **Say in the generated record that a generator wrote it, and which
    command.** The next reader must be able to re-derive the entry and to
    disagree with the predicate that produced it. An auto-written record that
    reads like a hand-written one removes the reader's ability to audit the
    rule.

## Pitfalls

- **Mistaking the suggester you already have for this.** A `--suggest` built
  on a prose classifier proposes what *looks* like a discharge; an
  accept-predicate generator derives what the checker will *accept*. They can
  disagree on the same input, and in the worked example they did: the prose
  scanner offered a `scored` entry for a bank whose file promises a section
  that was never written, which would have closed the finding while the debt
  stayed open. Keep both, and never make the classifier the writer.

- **Generating for the class the predicates cannot verify.** Derive only the
  sub-class the checker fully specifies. In the example that is the
  self-scoring case — the record's subject and its evidence belong to the same
  owner — which was 146 of 173 existing entries. Cross-owner attribution is a
  judgement about somebody else's work and stays manual, with the classifier
  beside it as a hint.

- **A generator with no refusal path.** If every invocation yields a
  satisfying record, you have automated the laundering of the debt rather
  than its repair, and the check will go green while nothing improved. Test
  the refusal before the acceptance.

- **Ranking by the wrong proxy.** The codes' shared purpose is usually "can a
  reader relocate this?", for which longest-and-unique is a decent proxy. Do
  not switch to "most canonical-looking" without checking availability: in
  the worked example, two of the three target records had no summary line at
  all, so a generator that preferred summaries would have failed on two
  thirds of the population it was built for.

- **Gating the commit.** The prompt in step 9 must warn and exit zero. A gate
  can refuse the commit of an author with no time left to satisfy it, and
  losing the work is strictly worse than one more cycle of a red line.

- **Leaving the recurrence undiagnosed in the artifact.** Write the rate
  arithmetic into the generator's own comment. The next author to see the
  check red needs to know it is arithmetic, not discipline, or they will
  close it by hand again.

## Verification

```bash
# 1. the predicates, forwards: derive an entry, refuse where nothing survives,
#    refuse to invent an owner, and byte-stable writes
python3 -m pytest -q skills/skill-authoring/scripts/test_carryforward_check.py \
  -k "Enter or WriteEntry or StagedCheck"

# 2. the live known-bad case must still be refused
python3 skills/skill-authoring/scripts/carryforward_check.py --enter 492

# 3. the generated record survives the checker that specified it
python3 skills/skill-authoring/scripts/carryforward_check.py

# 4. the prompt reaches the author, costs ~0.1 s, and never blocks
time python3 skills/skill-authoring/scripts/carryforward_check.py \
  --staged-check --quiet
grep -A2 'staged-check' .git/hooks/pre-commit
```

Expected: (1) green; (2) `verdict unscored/no-anchor` with `"status":
"unscored"` — round 492's knowledge file promises a scoring section it never
wrote, and a generator that proposes `scored` there has become the classifier
it replaced; (3) `0 error(s)`; (4) well under a second, and the hook line ends
`|| true` with `exit 0` as the file's last line.

Worked example, both rates, and the four prose-only diagnoses that preceded
the tool: `knowledge/round-501-the-repair-nobody-could-afford.md`.
