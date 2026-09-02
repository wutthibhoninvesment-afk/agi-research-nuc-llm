---
name: suppression-has-many-readers
description: Use when adding a path, pattern or id to a SHARED suppression list -- .gitignore, a lint baseline, an alert inhibition rule, a "known issues" allowlist -- to quiet ONE report, while some OTHER tool derives its subject set from the same list. Symptoms: a red test goes green when you fix an unrelated warning; a file "everyone ignores" turns out to be how a checker selects its population; a suppression added for tidiness makes a drift detector or a coverage number stop counting; two records disagree and the fix that reconciles the report deletes the evidence. Covers enumerating the READERS before writing, measuring each by toggling the entry, preferring a single-reader channel, and the ordering rule -- a suppression may land WITH or AFTER the record that makes it honest, never before. NOT for many suppressions in ONE checker (exemption-census), designing one (measured-exemption), one guard with several causes (skip-reason-is-a-claim), or doors that skip a gate (second-door-skips-the-gate).
---

# A suppression list is an interface, and you rarely know all its clients

Adding a line to `.gitignore` feels like housekeeping. It is an edit to a
predicate that an unknown number of tools consult. Each of those tools took
the same dependency for its own reason, and each will silently change its
answer.

`second-door-skips-the-gate` is the dual of this skill: there, one gate has
several **doors** into it, and a door that skips the gate produces a false
verdict. Here, one gate has several **readers**, and a change to the gate
silently changes every verdict downstream of it. The first is a missing
call; the second is an unwanted one.

## The measured instance (round 441)

A separate autonomous system left a fifteenth `.lang` program in a directory
this repo watches. Two of this repo's own instruments reported it:

| instrument | what it said | what it wanted |
|---|---|---|
| `check_round_recorded.py` | `1 uncommitted, unattributed change` | attribute it |
| `test_the_live_tree_has_no_drift` | RED, `(['agi_buy_and_hold.lang'], [])` | re-make the census |

The obvious fix — the one the first instrument's own message suggests, and
the one the file's **fourteen siblings already have** — is a `.gitignore`
line. Measured, by putting the line in `.git/info/exclude` (the same
`--exclude-standard` tier, restorable byte-for-byte) and re-running both:

```
drift before      (['agi_buy_and_hold.lang'], [])       test: FAILED
drift with line   ([], [])                              test: 4 passed
census            still declares 14 -- unchanged
the file          still on disk     -- unchanged
```

The second reader was `curecheck.field_corpus_drift()`, which selects "the
programs a separate system wrote" with `git ls-files --others
--exclude-standard examples`. Ignoring the file does not attribute it; it
deletes the evidence that the two records disagree, and leaves the
disagreement.

The other registry — `state/known-standing-dirty-paths.json` — has exactly
one reader. Writing the path there suppressed the record-gap report and left
the drift test red, which is the honest state.

**And the fourteen siblings were not this mistake.** When their ignore lines
landed, the census already named all fourteen, so `untracked - declared` was
empty with or without them. The hazard is not the suppression; it is the
suppression arriving *before* the record that makes it true.

## When to use

- You are adding an entry to any file whose whole job is "do not look at
  this": ignore files, lint baselines, suppression/inhibition rules,
  allowlists, `# noqa` families, alert silences, exclusion globs.
- A test, dashboard or audit went green and you did not fix its subject.
- Two records of the same fact disagree and one candidate fix reconciles the
  *report* rather than the *fact*.
- A checker selects its population negatively — "everything not X", "the
  untracked ones", "the files no rule covers". Any such checker is a reader
  of X.
- A reviewer says "just add it to the ignore list" about a file that some
  other tool is known to enumerate.

### NOT this skill

- **`exemption-census`** — many suppressions *inside one checker*, and what
  each costs. Here it is one suppression across many checkers.
- **`measured-exemption`** — designing a single exemption and proving it
  load-bearing.
- **`skip-reason-is-a-claim`** — one guard whose condition has several
  causes.
- **`second-door-skips-the-gate`** — several doors that must all call one
  gate. The dual; see above.
- **`filter-shares-the-defect`** — the filter reads the field the defect
  corrupts. Related, but there the coupling is accidental; here it is a
  deliberate shared dependency.

## Steps

1. **Name the report you are trying to quiet, in one sentence, before you
   touch anything.** "`git status` lists a file no round wrote." If you
   cannot say which report, you are tidying, and tidying is how a suppression
   with side effects gets in.

2. **Enumerate the readers of the suppression mechanism — by grep, not by
   memory.** For an ignore file, the readers are every caller of the flag
   that honours it, not just the file's name:

   ```bash
   git grep -n -- '--exclude-standard'          # git's ignore tier
   git grep -n 'gitignore\|check-ignore'
   git grep -n '<registry-filename>'            # for a bespoke registry
   ```

   Count them. **One reader is a different situation from two.** Write the
   number down; it goes in the commit message.

3. **For each reader, ask what it does with the answer.** A reader that
   merely *displays* is harmless. A reader that *selects a population* —
   "the untracked ones", "the files not matched by any rule" — will change
   its verdict, and that is the dangerous class. Negative selection is the
   tell.

4. **Toggle the entry and re-run each reader. Measure, do not argue.** Use a
   channel you can restore exactly — for git, `.git/info/exclude` is
   root-anchored like `.gitignore`, untracked, and md5-checkable:

   ```bash
   cp .git/info/exclude /tmp/bk && md5sum .git/info/exclude
   printf '%s\n' "<the path>" >> .git/info/exclude
   <run every reader from step 2, record each verdict>
   cp /tmp/bk .git/info/exclude && md5sum .git/info/exclude   # same hash
   ```

   Beware the anchoring rule you are testing under: a pattern containing a
   `/` in `core.excludesFile` is NOT anchored at the repo root and will
   silently fail to match, so a test through that channel can report "no
   effect" when the real `.gitignore` line would have had one. That false
   negative is one command away and was hit once while writing this.

5. **Prefer the narrowest channel that quiets the report.** If a registry
   exists whose only reader is the complaining tool, use it. A shared
   mechanism is a last resort, not a default, however many precedents it has.

6. **Apply the ordering rule.** A suppression that asserts "this is known and
   accounted for" may land in the SAME commit as the record that accounts for
   it, or after it — **never before**. Landing first converts an open
   question into a silent one. Where the record is deferred, say so in the
   suppression's own text and name the commit that should add it.

7. **Write the readers, and the measurement, into the artefact itself.** The
   next person to add a sibling entry reads the file, not your commit
   message. A one-line "checked: the only in-tree reader of this pattern is
   the line that writes it" is what stops the cargo-cult copy.

8. **Re-run the report you named in step 1 and confirm it is quiet, and
   re-run the OTHER readers and confirm they still say what they said.** Both
   halves. A suppression is correct when exactly one verdict moved.

## Pitfalls

- **"Its fourteen siblings are already there."** Precedent is not evidence.
  The siblings may have landed when the second reader agreed — that is
  exactly what happened in the measured instance. Check the *state at the
  time each precedent landed*, not just that it exists.
- **Taking the complaining tool's own advice literally.** A checker that
  says "a file a separate system leaves behind belongs in the standing-dirty
  registry" is describing its own suppression channel, and knows nothing
  about anyone else's. Its message is scoped to itself.
- **Testing the toggle through a differently-anchored channel.** See step 4.
  A global `core.excludesFile` and a repo-root `.gitignore` do not match the
  same patterns; concluding "no effect" from the wrong one is a false
  negative that looks like diligence.
- **Ignoring a file to stop a future `git add -A` from tracking it.** A real
  hazard with a real history — but it is a *write* concern, and it buys
  protection by paying with every *read* of the ignore tier. If some reader
  selects negatively, that trade is a bad one; say so and take the risk you
  can see.
- **Assuming a per-round log is like the last per-round log.** It usually is,
  and checking costs one `git grep`. The point of the check is that the
  cheap answer and the expensive answer look identical until you run it.

## Verification

You have done this when all of these hold:

1. The report being quieted is named in one sentence in the commit message.
2. The readers of the mechanism were enumerated by a command, and the count
   appears in the commit message or in the artefact.
3. Each reader's verdict was recorded with the entry both present and absent,
   by toggling through a restorable channel whose restoration was checked by
   hash.
4. Exactly one verdict moved. If more than one did, the suppression is the
   wrong channel, or the ordering rule (step 6) has been broken.
5. If a narrower single-reader channel existed and was not used, the
   artefact says why.
6. The suppression's own text names the record that makes it honest, and
   that record either exists or is cited as deferred with its owner.

```bash
# 1. the readers of git's ignore tier, in this tree
git grep -n -- '--exclude-standard'
# expected: every hit is a population selector you must re-run in step 3

# 2. the readers of a bespoke registry
git grep -n 'known-standing-dirty-paths'
# expected: exactly one reader (check_round_recorded.py) plus its own tests

# 3. the toggle, and the proof it was restored
md5sum .git/info/exclude
# expected: identical before and after the experiment

# 4. the second reader's verdict with the entry ABSENT
cd languages/whence && python3 -c "import curecheck as C; print(C.field_corpus_drift())"
# expected: (['agi_buy_and_hold.lang'], []) — still red, still saying the
#           census and the tree disagree

# 5. the report that WAS quieted
python3 skills/session-inheritance-audit/scripts/check_round_recorded.py
# expected: the path no longer appears among the unattributed changes
```
