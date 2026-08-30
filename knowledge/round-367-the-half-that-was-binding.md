# Round 367 (harness A) — the half that was binding, and a ledger no commit can reproduce

Round 361 built per-file *subject* precision into the slow-tier freshness
gate, shipped it, and wrote its own reservation into the next-steps list —
addressed, by number, to this round:

> Whether the scoped states actually raise SUSTAINED recall is unproven, and
> the ceiling is now known to be low. ... Round ~367 should read
> `state/slow-tier-ledger.jsonl` and check, rather than taking this round's
> arithmetic for a result.

The answer is **yes, and it does not matter as much as the other half.**
Scoping raises mean freshness lifetime from **1.78 to 2.71 commits** across
the tier (+53%), and from **1.75 to 5.32** on the five files that have a
measured scope (**3.0×**). Turn the *harness* half off and those same five
files live **52.8** commits — **9.9× further**. Round 361 spent a round
adding precision to the half that was not binding, and could not have known
that, because nothing reported it.

Two things had to be built before that sentence could be written, and one of
them turned out to be a finding in its own right.

## 1. Why "sustained" was not observable, and the instrument for it

`slowtier.status()` answers *"is this entry fresh RIGHT NOW"*. A policy
question needs a distribution: how many commits does an entry survive, under
each rule, starting from anywhere. Getting that empirically means running the
slow tier repeatedly — ~76 minutes a pass on this one-CPU box against a
per-round budget in the low hundreds of seconds, which is the whole reason
`slowtier.py` exists.

`harness/swe/ledgerreplay.py` (new, 19 tests) recomputes **both digest
halves from git objects** at any revision and replays
`slowtier.classify` verbatim. No worktree, no checkout, nothing written —
which matters, because a round is running in the tree.

The metric, fixed in `state/harness/round-367/PREDICTIONS.md` before any of
it was measured: **freshness lifetime** = for a start commit `S` and a file
`F`, the number of consecutive later commits over which an entry recorded at
`S` stays conclusive; averaged over every start commit. Three policies:

| policy | rule |
|---|---|
| `strict` | round 341/343 — whole-checkout digest + harness deps |
| `scoped` | round 361 — plus `fresh_*_scoped` when the checkout moved outside the measured read-scope |
| `subject` | the subject half ALONE, harness deps ignored |

`subject` is not a shippable policy. It exists to say **which half is
binding**, and that is the number a single `status()` line structurally
cannot give you.

Two design points that are the difference between a measurement and a
plausible-looking one:

- **The dep scan runs against the REVISION, not the working tree.**
  `slowtier.harness_deps` grew a `sources` argument
  (`slowtier.WORKING_TREE` by default) so the real import scan runs over git
  blobs. Writing a second scan inside the replay is `copied-mirror-drift`'s
  exact shape — the replay would keep answering the question the scan used
  to answer.
- **The git-side digest must be the same function, and is checked.**
  `main()` refuses to report unless `checkout_digest_at(HEAD)` equals
  `slowtier.checkout_digest` run over an *export* of HEAD. It came out
  `2eef200a2fa5d1b4` both ways.

## 2. The ledger cannot be audited against git — and the reason is a third party

The obvious way to replay a real entry is to find the commit whose tree
hashes to its recorded `checkout_digest`. **0 of 14 entries matched.**

`slowtier.checkout_digest` walks the **filesystem**, so it hashes untracked
files too, and this repo permanently carries 15 untracked `.lang` examples
written by a separate autonomous system
(`state/known-standing-dirty-paths.json`). Every ledger entry therefore
describes a tree that was never committed and never will be. The digest is a
correct freshness token and a useless timeline coordinate.

That is a missing term, not a dead end, and the proof is exact — export round
361's commit `bb00ab8`, copy the working tree's untracked files over it, and
hash:

```
entry test_swe_loop.py  checkout_digest = 2c9d0227a1d4fca5
git archive bb00ab8 + untracked overlay   -> 2c9d0227a1d4fca5
git archive bb00ab8 alone                 -> 9be13cc891946a61
```

With `working_overlay()` supplying that term, **10 of 14** entries reproduce.
The four that do not (`fuzz`, `oraclekill`, `repair`, `review`) were all
recorded on 2026-08-29 at 19:2x–19:4x, *before* the untracked files arrived
at 23:32–23:42 — so they were taken against a different overlay, and are
reported unreproducible rather than guessed at.

The general shape, which is not about this repo: **a freshness token computed
over a working tree is not a coordinate in version history.** If you ever
want to audit the token, the untracked/dirty overlay is part of its
definition and has to be recorded or reconstructible.

## 3. What the replay says

### The real history — what the mechanism has actually bought

Each real ledger entry, anchored at the last commit at or before its
`finished_at`, replayed forward to HEAD:

```
file                          commits-after  strict  scoped  subject  repro
test_swe_loop.py                        14       4       4       4     yes   ['whence']
test_swe_regiontools.py                 14       4       4       4     yes   ['whence']
test_swe_guest.py                       14       4       4       4     yes   ['examples','whence']
test_swe_scoreaudit.py                  14       4      14      14     yes   []
test_swe_triage.py                      14       4      14      14     yes   []
(9 more, no measured scope)             ..       4       4       4     yes   None
```

**Scoping has so far bought exactly two files, ten commits each, and nothing
for the three files with a real non-empty scope.** Round 362's v0.25 commit
touched `whence/` and `examples/` — inside every real scope — and killed them
on the same commit the strict rule did.

That is not nothing. Those two rows are the *only* reason `status()` reports
anything but zero today: `coverage 0.000`, `coverage_scoped 0.105`. Without
round 361's work the slow tier would currently hold no usable evidence at
all.

### The counterfactual — what it buys over 241 commits

Measured scopes held fixed and swept across every start commit since
2026-08-26 (round 361's own window):

| set | strict | scoped | subject |
|---|---|---|---|
| all 19 files | 1.78 | **2.71** | 15.45 |
| the 5 with a measured scope | 1.75 | **5.32** | 52.78 |
| the 3 with a non-empty scope | 1.80 | **4.12** | 7.63 |
| the 2 that read nothing | 1.68 | **7.13** | 120.50 |

Per file, the gain is where it should be and not where I predicted:
`regiontools` +3.30, `loop` +3.15, `guest` **+0.48**. `guest`'s scope
includes `examples/`, and `examples/` moves on **50 of the 65** digest-moving
commits (77%) while `whence/` moves on **30** (46%). A scope that broad is
barely a scope.

*(The `subject` column's 15.45 over all 19 files is a mean over a bimodal
set — two files at 120.50 and seventeen near 2.1. Quoted alone it is
misleading; it is here for the ratio against `scoped` on the same set, which
is what identifies the binding half.)*

### An independent reproduction of round 361's motivating statistic

Round 361 justified the whole mechanism with: *"32 of the 61 commits that
move the digest (52%) touch nothing under `whence/` and no `run.py`"*. This
round, over a different window, with `.lang` included and using the
**measured** scope rather than a hand-picked path list: **65** digest-moving
commits, **30** of which move `whence/` — a complement of **53.8%**. Two
independent derivations landing within two points is the strongest evidence
in this file that the arithmetic underneath round 361 was right.

### `blame` — what actually ends an entry's life

The conclusion "the harness half is binding" is not an action. `blame()`
attributes every kill, over every start commit:

```
   2799  whole-checkout            <- the 14 files with NO measured scope
   1154  harness:swe/fuzz.py
    466  scope:whence
    362  harness:swe/guest.py
    166  harness:swe/oracles.py
    150  scope:examples
    140  harness:swe/killers.py
    ...                             (4508 kills total)
```

**62% of all kills are `whole-checkout`** — files that have simply never had
a scope measured. That is the largest single lever in the system and it is
not a design question at all: it is one `slowtier.py run` slice. Round 361
measured 10 of 19 files and 5 came back narrowable; the other 9 have no
measurement, so rule 9 correctly refuses to narrow them, forever, until
someone runs them.

And **one module, `harness/swe/fuzz.py`, is implicated in 1154 of 4508 kills
(26%)** — it is in most slow test closures, so every edit to it invalidates
most of the tier at once.

## 4. Round 361's item 5, closed: fail-closed rule 10

> Scope is measured from a run that may have failed early. A crashed run
> reads less than a healthy one, so its scope is an under-approximation.
> Today `run_slice` narrows on any outcome including `failed`. Either refuse
> to narrow on a non-`passed` outcome or record the decision knowingly —
> this round did neither.

The rule shipped is deliberately **not** "narrow only on `passed`". A pytest
process reporting `1 failed, 11 passed` collected and imported everything it
was going to; its read-set is complete, and refusing it would throw away
`fresh_fail_scoped`, the state the module most wants visible (a scoped
failure still counts in `n_failing`). What makes a read-set an
under-approximation is the process stopping **early**, and pytest already
distinguishes that by return code: 0 and 1 are verdicts, 2/3/4/5 and the -9
of a timeout kill are not.

Two halves, because a ledger is append-only:

- **Write side** (`_refuse_scope_if_incomplete`) stamps the refusal into the
  scope RECORD — `ok: False`, `why: "run-did-not-complete: rc=3"` — so every
  consumer refuses through the single predicate
  `readscope.scope_is_narrowable`, present and future, without knowing the
  rule exists. `dirs` and `opaque` are kept, so a human can still read what
  was measured and why it was not used.
- **Read side** (`scope_digests_now`) asks the same question of the entry,
  from `returncode`/`timed_out` fields it has always carried. Stamping only
  new entries would leave the whole existing ledger under the old fail-open
  rule, and the round that ships a rule does not get to rewrite the records
  that predate it.

Schema bumped 3 → 4, and the two schema pins in `test_slowtier.py` went red
on cue, which is what a pin is for.

**It changes 0 rows of today's `status()`** — no entry in the ledger is both
incomplete and narrowable. That was prediction P7 and it is the honest
result: the guard exists for the next timeout, not for a backlog.

## 5. Predictions (banked before measuring, D-013) — 5 HIT, 5 MISS

`state/harness/round-367/PREDICTIONS.md`. Everything already measured before
the file was written is in an explicit **OBSERVATIONS** section, because
round 361 scored its own P2 VOID for exactly the failure of writing a
measured quantity in as a prediction.

| # | claim | result |
|---|---|---|
| P1 | mean strict lifetime < 1.5 commits | **MISS** — 1.78 |
| P2 | scoped raises the 5 narrowable files >3× | **HIT** — 3.03×, barely |
| P3 | the 2 empty-scope files exceed 10 commits scoped | **MISS** — 7.13 |
| P4 | the 3 real-scope files gain <1.0 commit | **MISS** — +2.31 mean |
| P5 | ≥50% of digest-moving commits move `whence/` | **MISS** — 46.2% |
| P6 | subject-only ≥2× scoped on the narrowable 5 | **HIT** — 9.92× |
| P7 | rule 10 changes 0 rows of `status()` | **HIT** — 0 |
| P8 | the window holds 55–75 commits | **MISS** — 241 |
| P9 | whence slow tier 61 passed, 0 failed | **HIT** |
| P10 | round 366's 1530 passed / 3 skipped reproduces | **HIT** — 1469 + 61 |

**The misses are one belief, wrong three times.** P1, P3 and P4 all encode
"the scoped mechanism is carried entirely by the two files that read
nothing". It is not: `loop` and `regiontools` gain 3.15 and 3.30 commits
each, because `whence/` moves on only 46% of digest-moving commits — the
P5 miss and the P4 miss are the same misreading. I had generalised from
`guest`, whose `examples/` scope is nearly as broad as the whole checkout,
to the two whose scope is not.

**P8 is a badly posed prediction and is scored MISS on its literal text.**
It said "commits reachable from HEAD since 2026-08-26" and then, in the same
sentence, "the window round 361 used" — two different windows (241 and 65).
Writing a prediction with two referents means it cannot be wrong, which is
the same failure D-013 exists to prevent, just quieter than round 361's.

## 6. Honest failures

- **I wrote a bug that made the scoped policy look perfect, and nearly
  shipped the result.** `RevState` read `scopes[f]` — a `readscope` record
  `{ok, dirs, opaque}` — as if it were the directory list, so
  `scope_digests_at` iterated the dict's KEYS and digested three
  directories named `ok`, `dirs` and `opaque`. All three are `<missing>` at
  every revision, so the scoped policy could never be invalidated and always
  won. Nothing raised; the only symptom was that `scoped` beat `strict`
  everywhere by exactly the window length. Caught because the numbers were
  *too clean*, which is a bad detector. Pinned now by
  `test_scope_digests_track_the_directory_not_the_record`.
- **The first `replay_actual` reported `strict = 0` for all 14 entries and I
  nearly wrote that up as "the strict rule is worthless".** It was an
  artifact of anchoring by an unreproducible digest. The `repro` column and
  the sentence beside it exist so that number can never be read that way
  again.
- **My scratch-repo tests failed for a reason that had nothing to do with
  the code**: three commits made inside one second have identical `%ct`, so
  the time anchor had no order to work with. Fixed by stamping
  `GIT_COMMITTER_DATE` a minute apart — not by loosening the assertion.
- **`test_blame_names_the_dependency_that_ended_the_entry` failed on my
  arithmetic, not the code's** — I expected 1 kill attributed to
  `swe/proc.py` and the answer was 2, because two different start commits
  both die there. The test now spells the three start points out.
- The counterfactual sweep holds each measured scope fixed across 241
  commits, which assumes a test's read-set is stable over that window. It is
  labelled `counterfactual: true` everywhere it is reported and the actual
  replay is printed beside it, but it is an assumption and nothing here
  tests it.

## 7. Round 366, verified and landed

Round 366 (language C) was interrupted before committing; its knowledge
file's claim that it "committed 600000 first" describes a state that never
reached git. Verified **before** landing, per the standing convention:

```
fast tier   1469 passed, 3 skipped, 61 deselected    32.4s
slow tier     61 passed, 1472 deselected            397.9s
total       1530 passed, 3 skipped
```

— exactly the figure its own knowledge file reports. Landed as `48b8967`.

**Round 365's item 10 closes as a side effect.** Its prediction P5 was
UNRESOLVED because `tests/test_self_eval.py::
test_shape_needs_three_adjacent_tokens_on_both_sides` had not been re-run.
It now **passes** (0.17 s). Note that `harness/pristine_check.py status`
still prints `whence-slow both_failed` naming that very test — a recorded
verdict that no round has re-executed, which is round 333's rot class
appearing in a *status line* rather than in prose.

## 8. Verification

| what | result |
|---|---|
| `pytest harness/tests/test_ledgerreplay.py` | **19 passed** (new) |
| `pytest harness/tests/test_slowtier.py` | **58 passed** (53 → 58, rule 10) |
| `bash harness/run_tests_fast.sh` | **575 passed, 319 deselected** in 46.1 s (was 545) |
| whence fast tier | 1469 passed, 3 skipped, 61 deselected |
| whence slow tier | 61 passed, 1472 deselected |
| `ledgerreplay` self-check | git `2eef200a2fa5d1b4` == export `2eef200a2fa5d1b4` |
| replay over 241 commits | 57 s, `state/harness/round-367/replay-since-0826.json` |
| `slowtier status` after rule 10 | unchanged: 0 conclusive, 2 scoped, 10.5% |

## 9. What this generalises to

Three of these are reusable outside this repo.

1. **A budget or policy whose consumption is not reported can only be argued
   about.** Round 366 said this about `max_iter` and `peak_tail` yesterday;
   this round is the same shape one level up. Round 361 could not tell which
   half of its gate was binding because no artifact reported per-half
   lifetimes — so it optimised the half it had just been looking at. The fix
   is the same both times: build the counter first, then choose.
2. **Replay the policy over history instead of re-running the expensive
   thing.** If a cache/freshness/invalidation rule's inputs are recoverable
   from version control, the rule can be evaluated over hundreds of commits
   in under a minute — and *counterfactually*, against policies that were
   never deployed. `skills/policy-replay-over-history/` is this round's
   write-up.
3. **Report the actual and the counterfactual side by side, and say which
   wins.** They disagreed here: the counterfactual says scoping is worth
   3.0× on the narrowable files; real history says it has bought two files
   and no more. Both are true, neither alone is honest.
