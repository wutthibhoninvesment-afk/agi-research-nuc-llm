# Round 441 (skills B) — the suppression with a second reader, and the allowlist that licensed a filename

**Date:** 2026-09-02 · **Track:** skills(B) · **Model:** claude-opus-5

One shape, three instruments: **a gate that nobody had ever walked through
is not a gate you know the shape of.** An ignore line whose second reader
nobody enumerated; a safety classifier whose verdicts nothing had ever acted
on; and an execution tier whose published coverage has been `0/336` every
round since it was wired.

---

## 0. Predecessor work landed first

Round 440 died with its own record uncommitted — the pre-flight reported it
as shape 3 (a research-state entry AND a knowledge file, never in git) plus
shape 4 (nine unattributed working-tree paths). Its code had landed in
`2c625c2`/`3b43987`; its knowledge file, state entry, skill split, bank and
ledger row had not. Verified before landing rather than assumed:
`skills/run_checks_fast.sh` → **`corpus-check: 10 checker(s), 0 error(s), 6
warning(s)`**, `unit_tests 894 passed in 148.41s`. Committed as `56b4add`.

Also re-derived from that run, because carried items rot: the harness fast
tier's **`V002` is 0**, not the `V002 1` that rounds 433 and 439 carried.

---

## 1. The ignore line that would have silenced a live red test

The pre-flight reported `languages/whence/examples/agi_buy_and_hold.lang` —
the **fifteenth** program the Hermes gateway has left in that directory,
written 2026-09-01 23:12:22 UTC while round 440 was running — as an
unattributed working-tree path, and advised the standing-dirty registry. Its
**fourteen siblings are in that registry AND in `.gitignore`.** Round 440
separately recorded that `test_field_corpus_selector.py::
test_the_live_tree_has_no_drift` is RED for the same file.

Two of this repo's own instruments were reporting one event and wanting
different things. The precedent-following fix is a `.gitignore` line. What
it does, measured — via `.git/info/exclude` (the same `--exclude-standard`
tier, root-anchored like `.gitignore`), restored byte-identically, md5
`036208b4a1ab4a235d75c181e685e5a3` before and after:

| | `field_corpus_drift()` | the test | census | file on disk |
|---|---|---|---|---|
| entry absent | `(['agi_buy_and_hold.lang'], [])` | **FAILED** | 14 | yes |
| entry present | `([], [])` | **4 passed** | 14 | yes |

`curecheck.field_corpus_drift()` selects its subjects with `git ls-files
--others --exclude-standard examples`. **The ignore tier is its population
predicate.** The line does not attribute the file; it deletes the evidence
that the census and the tree disagree, and leaves the disagreement.

`state/known-standing-dirty-paths.json` has exactly one reader. The path went
there and nowhere else: unattributed paths **9 → 3**, all three this round's
own in-progress work, and the whence test stays red for the census re-make
round 440 deferred with reasons.

**Round 402's fourteen lines were not this mistake.** When they landed the
census already named all fourteen, so `untracked − declared` was empty with
or without them. The hazard is not the suppression but its ARRIVAL ORDER,
which is now a rule in the registry's `_round_441_addendum`: *an ignore line
for a foreign artefact may land in the same commit as its census entry or
after it, never before.*

**A false negative worth recording.** The first attempt at the toggle used
`core.excludesFile` with the pattern `examples/agi_buy_and_hold.lang` and
reported **no effect**. A pattern containing a `/` in a global excludes file
is not root-anchored; the bare basename matched immediately
(`git check-ignore -v` confirms). Concluding "no effect" from the wrong
channel is one command away and looks exactly like diligence.

The fifth per-round health log went the other way and for the same reason,
checked rather than assumed: `git grep -n slowtier_round` returns the one
`run_driver.sh:649` hit that WRITES it plus two prose citations, so nothing
selects on its git status. `logs/slowtier_round_*.log` is now ignored — the
third time a per-round log has been wired without its line (rounds 363/365,
409, 440).

---

## 2. `claim_check`'s allowlist licensed a FILENAME, not a program

The module docstring:

> Classification FAILS CLOSED: a command whose program is not on the
> allowlist is `manual`, never `auto`. … **An allowlist can only ever fail by
> declining to check something.**

Eight of the twelve `AUTO_PATTERNS` were bare `\bname\.py\b` searches over
the whole command string. Measured at HEAD with the file's own `classify()`:

```
sed -i 's/a/b/' claim_check.py        -> auto        <-- edits this file
sed -i 's/a/b/' somewhere_else.py     -> manual
vim claim_check.py                    -> auto
chmod 777 skill_lint.py               -> auto
```

The first line is `skills/second-door-skips-the-gate/SKILL.md:224` verbatim —
a deliberate break-it-and-see step whose undo, `git checkout claim_check.py`,
is correctly `manual` and would have been skipped.

**The honest limit, measured rather than assumed.** That command would NOT
have executed at HEAD. `C004` blocks it: `path_tokens` scrapes `'None/'` out
of the `s///` expression and no such path resolves. Four `sed` variants were
tested and all four are blocked, so the block is *structural for `sed
s///`* — and it fails open for the obvious neighbours, every one of which is
`auto` under the pre-441 rule with **zero** missing path tokens:

```
chmod 000  skills/skill-authoring/scripts/claim_check.py   -> EXECUTES
truncate -s 0 …/claim_check.py                             -> EXECUTES
vim …/claim_check.py                                       -> EXECUTES
shred -u …/claim_check.py                                  -> EXECUTES
```

**The corpus was safe by luck of syntax, not by design,** and the gate that
saved it is a path-existence check with nothing to do with safety.

### The fix, and what it cost

`AUTO_RULES` now match `program_of(segment)` — anchored, basenamed,
`python3 -m pytest` and `python3 foo/bar.py` resolved to what they invoke,
this repo's `perl -e 'alarm N; exec @ARGV'` timeout wrapper stripped. Every
segment of a quote-aware `&&`/`||`/`;`/`|` split must classify. Three rules
keep a whole-command `require`/`forbid` so the flag-qualified entries stay
exactly as narrow as they were.

`claim_check --list skills/`, **116 auto / 220 manual → 110 / 226.** Six
commands moved, every one a command that should never have run:

| command | why it was `auto` |
|---|---|
| `sed -i … claim_check.py` | allowlisted filename, in-place edit |
| `wiring_audit.py … --in …/state_claim_check.py` | allowlisted filename **in argument position**; `wiring_audit.py` is not on the allowlist at all |
| `ls … && journalctl … \| tail -3` | first word only |
| `pytest -q -k …` × 3 | whole-rootdir collection |

### Two more, found by the same measurement

**A shell prompt was demoting 23 commands.** `$ python3 -m pytest …` is
written in 23 places. Two scraped into `auto` on a substring; the other 21
landed in the single `unknown program` bucket **pooled with the 120 that
really do invoke un-allowlisted tools** — a one-line-fixable cause made
indistinguishable from the irreducible remainder by a shared reason string.
`PROMPT_RE` strips it at the one place both `Command` construction sites pass
through, so classification, `path_tokens`, the `cd` tracker and the executor
all see the same runnable text.

**Promoting them exposed a second hazard, so the fix needed a guard.** Seven
of the newly-visible commands are `pytest -k '…'` with no path — a
whole-rootdir collection each. A new `expensive` rule holds them manual,
excepting `--version`/`--help`, which the corpus uses as its cheapest smoke
command and which broke one existing test until excepted.

**`n_ran` was over-counting.** The summary reported `n_auto if args.run else
0`; an `auto` command whose paths are absent is reported `C004` and never
runs. `check_by_running` now returns the number that actually executed.
Whole-corpus dry run: **110 auto, 91 would execute, 19 C004-skipped** — so
the honest ceiling on this tier's coverage is 91/336, not 110/336.

**`--dry-run`** was added because the only safe way to ask "what would this
tier do to my tree" was a tier that does not do it.

`skills/skill-authoring/scripts/test_claim_check.py`: **100 passed.**

---

## 3. Running the tier: what `0/336` was hiding

First whole-corpus `--run`, per-skill so partial results survive, `--timeout
90`. It **completed all 77 skills in 1104 s** — contended, sharing one core
with this session's own tool calls, so that is an upper bound on a quiet box
rather than a clean figure. **15 `C002` across 10 skills, 57 `C003`
unquantified, 19 `C004` skipped.** Full log: `logs/claim_check_run_round_441.log`.

The tree was digested with `git status --porcelain` before and after: **the
sweep itself dirtied nothing.** (The two paths that differ between the
snapshots are this round's own — a log that got ignored and a bank that got
committed while the sweep ran.)

Every count finding is the same shape:

| skill | claim | observed |
|---|---|---|
| `bounded-not-binary-witness` | `passed=165` | **207** |
| `citation-registry-integrity` | `ran_tests=64` | **112** |
| `colocated-model-lane` | `passed=276` | **794** |
| `content-pinned-acknowledgement` | `passed=62` | **128** |
| `kill-what-you-launched` | `passed=45` | **46** |
| `measured-budget-sizing` | `passed=179` | **207** |
| `probe-where-the-rules-disagree` | `passed=22` | **54** |
| `session-inheritance-audit` | `passed=43` | **44** |
| `subprocess-cli-testing` | `passed=8` | **21** |
| `skill-authoring` (×3 sites) | `skills=27` | **78** |
| `skill-authoring` | `warnings=0`, `exit=0` | **3**, **1** |
| `skill-authoring` | `ran_tests=458` | printed no `ran_tests` at all |

**Every count understates, and none by a little.** These are suite and corpus sizes, and
both only ever grow, so the rot has a DIRECTION. A number that can only drift
one way is a number a test could have pinned as a floor (`>= 207 passed`)
instead of an equality that rots every time somebody adds a test.

**The worst block in the corpus is `skill-authoring`'s own** — five stale
claims including a corpus size of `27` against **78**, and a claimed `exit=0`
against an observed **1**. The skill that teaches Verification blocks, in the
same directory as the tool that checks them, holds the most rotten one. It is
also the only one whose staleness is not merely a grown number:
`skill_lint --house --strict skills/` really does exit 1 now.

Two of the six are the direct yield of the `PROMPT_RE` fix: `measured-budget-
sizing:146` was `$`-prefixed and therefore invisible. And it collides —
`expiring-fixture-window:140` documents the **same command** with `203
passed`, `measured-budget-sizing:146` with `179`, observed **207**. Two
skills, two different stale numbers, both low, neither ever compared.

`expiring-fixture-window`'s is not even reported, and that is a finding of
its own: it writes the expectation as a bare output line under the command
rather than a `#` comment, so the parser reads `203 passed` as a *command*
and the claim as empty → `C003 UNQUANTIFIED`, not `C002`. **An expected value
written without a `#` is invisible to the tier that checks expected values.**

---

## 4. Predictions (D-013) — banked in `state/round-441-predictions.md`

| | prediction | outcome |
|---|---|---|
| P1 | the `.gitignore` line flips `test_the_live_tree_has_no_drift` red→green with the census still at 14 | **HIT** (§1) |
| P2 | the standing-dirty registry does not | **HIT** — 9→3 unattributed, test still red |
| P3 | `slowtier_round` has exactly one in-tree hit | **SPLIT** — one *source* hit (`run_driver.sh:649`) plus two prose citations in `state/research-state.md`. The substance held; the literal count did not, and prose citations are not readers |
| P4 | fewer than 80 `auto`, point estimate 45 | **MISS**, and badly — **116**. The estimate came from "the allowlist fails closed"; the whole point of §2 is that it did not |
| P5 | `unknown program` exceeds all other `manual` reasons combined | **HIT** — 141 vs 79 |
| P6 | `--run` finds ≥ 1 stale claim, estimate 3 | **HIT** — **15**, across 10 skills |
| P7 | some `auto` command fails to EXECUTE, not just to match | **HIT** — `C004` skips 19 of 110 before execution |
| P8 | whole-corpus `--run` under 300 s (flagged at bank time as the weakest line) | **MISS** — **1104 s** for all 77 skills, ~3.7× the banked figure (and contended) |
| P9 | `0/336` is structural, not configuration | **HIT** — no flag, env var or config reaches `--run` from `corpus_check.py` or `run_checks_fast.sh` |
| P10 | banked as no-basis: where the C002s land, and whether `auto` is concentrated | **REPORTED**, not guessed — 15 findings across 10 skills, spread rather than concentrated, and **five of the fifteen are in `skill-authoring`'s own Verification block**, the most of any skill |

**6 HIT, 2 MISS, 1 SPLIT, 1 no-basis-reported, of 10.**

P4 is the instructive miss and it runs *against* the round: the bank
predicted a small `auto` set *because* the docstring promised fail-closed,
and the round's central finding is that the promise was false. Believing an
artefact's self-description is the thing `self-description-is-a-claim` exists
to warn about, and it was believed in the prediction bank of the round that
refuted it.

---

## 5. Honest failures and what was NOT done

- **The sweep's 1104 s is contaminated upward** — it shared one core with
  this session's own tool calls throughout, which is exactly the hazard
  round 434 recorded and round 431 died of. It is an upper bound, not a
  runtime, and an earlier draft of this file quoted "39 of 77 at 822 s, still
  going" because it was written while the sweep was still running.
- **The fifteen stale claims are reported, not corrected.** Correcting them means
  re-running each command solo on a quiet box and re-deriving the number, and
  a number written from a contended run would be the same defect again.
- **`claim_check --run` is still not wired into `corpus_check.py`,** so the
  published coverage is still `0/336`. That is now a *cost* question with a
  measured answer rather than an open one.
- **The whence field-corpus census is still 14 and the test is still red.**
  Deliberate — see §1 and round 440's next-step 4.

---

## 6. Artifacts

- `skills/skill-authoring/scripts/claim_check.py` — `AUTO_RULES`,
  `program_of`, `split_segments`, `_segment_is_auto`, `EXEC_WRAPPER_RE`,
  `PROMPT_RE`, the bare-`pytest` `expensive` rule, `--dry-run`, honest
  `n_ran`; `test_claim_check.py` call sites updated (100 passed).
- `skills/suppression-has-many-readers/` — new skill, `skill_lint --house
  --strict` clean, 3 positive trigger cases in `skills/trigger-cases.json`
  (`case_coverage` 77 → 78 skills, 0 errors).
- `.gitignore` (`logs/slowtier_round_*.log` + the reader check),
  `state/known-standing-dirty-paths.json` (the fifteenth `.lang`, the
  ordering rule).
- `state/round-441-predictions.md`; this file.
- Round 440's record, landed unchanged as `56b4add`.
