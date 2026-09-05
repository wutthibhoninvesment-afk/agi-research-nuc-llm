---
name: absence-retested-on-the-raw-input
description: Use when a tool reports something MISSING and you are about to act on it — "path resolves nowhere", "no such file", "names nothing", "0 results", "no tests collected". The verdict was computed against a DERIVED view (a sweep with a suffix or name filter, a tokenizer's output, an index, a cached map or roster) but worded as a fact about the world, so the repair it names is the wrong one. Symptoms: the report denies a subject you can see with one `ls`; an error whose fix is "create X" for an X that exists; a filter and an exemption ordered so the filter destroys the marker the exemption keys on; one message covering two causes whose repairs live in different files; an absence read out of a map with no row for the subject. The move is to re-test the negative DIRECTLY against the raw thing named, before wording it — then, if raw and derived disagree, report against the FILTER, not the subject. NOT errors-that-name-the-fix, NOT deleted-vs-never-written (who owns a real gap), NOT zero-rate-needs-a-distance.
---

# The absence you found is only as wide as the filter that found it

A checker that reports a *positive* is self-verifying: it holds the thing it
found. A checker that reports an *absence* holds nothing — it holds the
**failure of a predicate**, and predicates have edges. Between the subject
the user wrote and the set the checker searched there is always at least one
derivation: a suffix filter, a tokenizer, an index build, a normalisation, a
cached roster. The absence is a fact about *the far side of that
derivation*. The message is almost always written about the near side.

The cost is not a wrong verdict. It is a **wrong repair**: a reader who
obeys the message goes and edits a file that was never broken.

## Trigger conditions

Reach for this when any of these is true:

- A tool says a named thing does not exist and you can see it with one
  `ls`/`stat`/`grep`. (Two live examples, both from this repo's own corpus
  checkers, are worked through below.)
- A message says "nothing", "nowhere", "none", "never", "no such", "0 of",
  and the search behind it went through a filter you have not read.
- A finding's suggested repair is *create/write/add* something that is
  already there, or *fix a path* that was never a path.
- One error branch is reachable by two different causes whose repairs live
  in different files, and it prints one sentence for both.
- An exemption, allowlist, or "skip this, it's a template" rule sits
  **after** a split/normalise/strip step in the same pipeline.
- A coverage, blast-radius, ownership or dependency question is answered out
  of a recorded map, and you have not checked that the subject has a row in
  that map at all. Absence-in-the-map reads exactly like absence-in-the-world.

**Do not** use it for: a message that is true but unhelpful
(`errors-that-name-the-fix`); deciding who owns a gap that really is a gap
(`deleted-vs-never-written`); or a zero count being read as "cannot happen"
(`zero-rate-needs-a-distance`).

## Steps

1. **Write down the two representations.** For the finding in front of you,
   name (a) the RAW thing the subject wrote or the user named, and (b) the
   DERIVED view the checker actually searched. If you cannot state both in
   one line each, you have not found the derivation yet — keep reading the
   source. Checkable outcome: two lines, one naming a value in the input,
   one naming the collection the `in`/lookup/`not found` ran against.

2. **Re-test the negative directly against the raw thing.** One `os.path.
   exists`, one un-normalised `in`, one lookup with every filter off. This is
   cheap by construction: the raw form is right there in the finding.
   Checkable outcome: a two-line experiment whose result is `True` or
   `False`, run before you write a single word of message.

3. **If raw and derived disagree, the finding is about the FILTER — and that
   disagreement is the whole finding.** Do not repair the subject. Say which
   predicate excluded it and which file that predicate lives in, so the
   reader edits the checker instead of the corpus.

4. **Split the branch.** One sentence covering two causes is a sentence that
   is false for one of them. Emit one branch per repair, and let each name
   its own file. Checkable outcome: the two messages name different paths.

5. **Check the ORDER of every filter against every exemption.** A pipeline
   that *transforms then exempts* can destroy the marker the exemption keys
   on. Ask the exemption question of the **rawest form that still carries the
   marker**, then split. Checkable outcome: for each exemption rule, the
   representation it is asked about is the one the user typed, not a fragment.

6. **Before widening the predicate, measure what the widening admits.**
   Widening is the obvious repair and it over-shoots in one specific way:
   **the register is not a member of the set it registers.** A sweep for
   `*prediction*` files that now accepts `.json` will swallow the
   prediction *ledger*. Name such files out explicitly. Checkable outcome:
   the before/after counts of the widened sweep, and every new member
   accounted for by name.

7. **Pin both halves.** A test that the widened predicate SEES the new shape
   (a positive control — otherwise you have only tested the message), and a
   test that the genuinely-absent case still gets the genuinely-absent
   wording. Checkable outcome: two named test functions, each red if the
   other's fix is reverted.

## Worked instances

Both are real, both were live ERRORs in this repo at round 513, both had
been reported for two rounds, and both messages named the wrong repair.

**A. `carryforward_check.py` K003 — "the entry names nothing".** The ledger
entry for round 512 read `"bank": "state/whence/round-512/predictions.json"`.
The file existed. The sweep that builds the `banks` map filtered on
`name.endswith(".md")` — every one of the six banking conventions the module
documents is `.md` — so `banks` had no key for round 512 and the branch fired
with *"round 512: no bank on disk at all — the entry names nothing"*. The
module's own docstring already contains the lesson one attribute over: it
explains that the sweep was made repo-wide because *"an obligation nobody
registered cannot be enumerated from a list of the places you already know
about"*. It enumerated the directories honestly and went on enumerating the
**suffixes**.

The tempting repair — rename the bank to `.md` — was tested and **does not
work**: with the `.md` copy in place the same checker emits ``bank` is
…predictions.json, but the bank(s) on disk are …predictions.md`. Same cause,
different branch. The repair was step 6 (widen the suffix set, name the
ledger itself out of it) *plus* step 4 (split the branch on
`os.path.exists`), and the second half is the durable one: the next
convention nobody foresaw now gets a sentence that sends its reader to the
sweep.

**B. `claim_check.py` C001 — "path `/^` resolves nowhere".** A Verification
block contained

```bash
sed -n '/^=* FAILURES/,/^=* short test summary/p' <the retained log>
```

`path_tokens` split on `[\s=]+` — the `=` is there so `--flag=path` yields
the path — and that split cuts `'/^=*` into `'/^` and `*`. The `*` that the
placeholder exemption keys on ends up in the *other* fragment. The survivor,
`/^`, is a `sed` address; it is also absolute, and the guard that skips
tokens too unanchored to judge waves absolutes through by definition
("there is nothing else they could be relative to"). So the one token in the
corpus that is guaranteed not to be a path is also the one guaranteed to be
checked. Step 5 is the whole fix: ask the placeholder question of the
whitespace-delimited word first. Measured over 116 skills and 595 commands,
that rule drops **exactly one** token — the phantom — and no real path.

## Pitfalls

- **Widening the predicate and leaving the message alone.** The commonest
  half-fix. It closes today's instance and guarantees that the next
  unforeseen shape gets the same false sentence, with the added cost that
  everyone now believes the sweep is total.
- **Renaming the subject to fit the filter.** It moves the error to a
  different branch (measured above), and it corrupts the record: round 512
  banked in JSON on purpose.
- **Treating "absolute" as "anchored".** A guard that skips relative tokens
  it cannot resolve, and admits every absolute one, is not conservative —
  it is *selectively* aggressive, and regex addresses, URL fragments and
  `awk` patterns all start with a slash.
- **Reading absence out of a map that has no row for the subject.** The same
  error one level up, and it bites the tooling built to prevent it: this
  repo's diff→test-node mapper (`harness/readset.py blast`) is recommended
  in every round prompt, and at round 513 its recorded map contained **zero**
  nodes from the skills corpus suite — so for the four red nodes in that
  suite it answered "nothing reads this" by construction. Check the map's
  roster for the subject before you believe its silence.
- **The register is not a member.** Widening a name-shaped sweep to a new
  suffix will pick up the index, the ledger, the manifest, the lockfile —
  the file that *tracks* the population is not *in* it.
- **Stopping at the first disagreement.** Once raw and derived disagree,
  sweep the whole corpus for the other instances of the same mechanism
  before shipping: a predicate edge is rarely a singleton, and if it is,
  that is a number worth publishing.

## Verification

```bash
# 1. The direct re-test (step 2), against the two live instances.
python3 - <<'PY'
import os, sys, json
sys.path.insert(0, "skills/skill-authoring/scripts")
import carryforward_check as cf, claim_check as cc
led = json.load(open("state/prediction-bank-ledger.json"))["banks"]
named = led["512"]["bank"]
print("raw   :", named, "exists =", os.path.exists(named))
banks, _ = cf.find_banks(os.path.abspath("."))
print("derived:", 512 in banks, banks.get(512))
print("phantom:", cc.path_tokens(
    "sed -n '/^=* FAILURES/,/^=* short test summary/p' log"))
PY

# 2. Both checkers agree with the direct re-test, on the live corpus.
python3 skills/skill-authoring/scripts/carryforward_check.py | tail -1
python3 skills/skill-authoring/scripts/claim_check.py skills | tail -1

# 3. Both halves of step 7, and the register-is-not-a-member control.
python3 -m pytest -q skills/skill-authoring/scripts/test_carryforward_check.py \
                     skills/skill-authoring/scripts/test_claim_check.py

# 4. Does the map you are about to trust have a row for your subject?
python3 -c "import json; m=json.load(open('harness/readset-map.json')); \
print(sum(1 for k in m['nodes'] if 'skill-authoring' in k), 'skills node(s) in the map')" 
```

You have applied this correctly when, for the absence in front of you, you
can say: *the raw form, the derived form, which one the message was worded
about, and — if they disagree — the predicate and the file that produced the
disagreement.* If your repair changed the subject rather than the predicate
or the message, you have done step 3 backwards.

To see it fail on demand — the control that the widened sweep is not
vacuous:

```bash
cp state/whence/round-512/predictions.json /tmp/predictions-round-9999.json
cp /tmp/predictions-round-9999.json state/predictions-round-9999.json
python3 skills/skill-authoring/scripts/carryforward_check.py | grep 9999
rm state/predictions-round-9999.json
```

A `.json` bank for a round with no ledger entry must now be reported as
`K001` by name. Before round 513's fix that command printed nothing, which
is the failure this skill is about: the sweep was silent, and silence read
as "no obligation".
