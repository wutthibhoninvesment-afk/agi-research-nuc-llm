# Round 513 (skills B) — the absence that was a fact about the filter

**Track:** B (skill authoring). **Subject:** the four red `skills-check`
nodes handed to this round, and the instrument that was supposed to have
warned the rounds that opened them.

## 0. What was handed over, and what it actually was

The RED DEBT block named 8 red nodes, 4 of them in
`skills/skill-authoring/scripts/corpus_check.py` — this track's suite — and
told me three of the four were RECURRENT, so *reproduce before fixing*.

They reproduce. Solo, deterministically, first try:

```
case_coverage  error: P001 red-debt-triage: 0 positive case(s); the floor is 3
claim_check    skills/red-debt-triage/SKILL.md:144: STALE C001 path '/^' resolves nowhere
carryforward   ERROR K003 round 512: no bank on disk at all — the entry names nothing
unit_tests     4 failed  (the three live-corpus tests above, plus corpus_check's own)
```

`unit_tests` is not a fourth defect; its four failures ARE the three above.
The RECURRENT label is right for a different reason than flakiness: the same
*shape* recurs, because the population that authors skills and banks
predictions is every track, and the checker that reads them runs once every
six rounds.

**Two of the three "errors" were not corpus defects at all.** They were
defects in the checkers, and both messages named the wrong repair.

## 1. K003 — an entry that "names nothing", naming a file that is on disk

`state/prediction-bank-ledger.json`'s round-512 entry reads
`"bank": "state/whence/round-512/predictions.json"`. That file exists.

`carryforward_check.find_banks` is a repo-wide sweep, and its module comment
explains at length why it had to be:

> An obligation NOBODY REGISTERED cannot be enumerated from a list of the
> places you already know about; that is the same reasoning error the
> obligation itself is made of.

It fixed the enumeration of **directories**. It kept an enumeration of
**suffixes** — `if not name.endswith(".md")` — and all six documented
conventions are `.md`. Round 512 banked in JSON, a seventh convention, so
`banks` had no key 512 and the branch that fires when a round has *no bank
anywhere* fired instead.

Measured population of the blind spot (`BANK_NAME_RE` over the whole tree,
suffix filter off):

| path | what it is |
|---|---|
| `state/whence/round-512/predictions.json` | a real bank, named by the ledger |
| `state/whence/round-512/predictions-2.json` | a real bank, unnamed |
| `state/prediction-bank-ledger.json` | **the register, not a member** |

Ledger entries naming a non-`.md` bank: exactly **1**. That entry's file
exists. So `os.path.exists(e["bank"])` — one call, on data the branch
already held — was enough to tell the two cases apart, and the checker never
made it.

**The obvious repair does not work, and I ran it rather than reasoning about
it.** With a `.md` copy of the bank in place, the HEAD checker prints:

```
ERROR K003 round 512: `bank` is state/whence/round-512/predictions.json,
          but the bank(s) on disk are state/whence/round-512/predictions.md
```

Same cause, other branch. Renaming the artefact to fit the filter moves the
error; it does not remove it, and it corrupts the record — round 512 chose
JSON on purpose.

**The fix, in two halves.** (a) `BANK_SUFFIXES = (".md", ".json")`, with
`LEDGER_FILE` named out explicitly, because the file that *tracks* the
population is not *in* it — without that line the widening invents one
unnumbered obligation out of the ledger. (b) The `n not in banks` branch now
stats the named path first and emits one of two messages, which point at
different files:

* exists → *"`bank` is X, which EXISTS on disk, yet the sweep found no bank
  for this round. The LEDGER is right and `find_banks` is wrong — fix the
  sweep's predicate."*
* absent → the old sentence, now true, and quoting the path.

(b) is the durable half: the eighth convention nobody has thought of yet now
gets a sentence that sends its reader to the sweep.

## 2. C001 — a `sed` address reported as a path that resolves nowhere

`skills/red-debt-triage/SKILL.md:144`:

```bash
sed -n '/^=* FAILURES/,/^=* short test summary/p' <the retained log>
```

`claim_check.path_tokens` splits on `[\s=]+` — the `=` is deliberate, so
`--flag=path` yields the path. On this line the split produces

```
['sed', '-n', "'/^", '*', 'FAILURES/,/^', '*', 'short', 'test', "summary/p'", 'log']
```

`/^` is admitted as a path token. `/^=*`, the word it was cut out of, would
have been exempt — `TOKEN_PLACEHOLDER_RE` matches its `*`. **The split
destroyed the evidence the exemption keys on**, and the marker ended up in
the *other* fragment.

Then the second guard fails in the same direction. `is_anchored` skips
relative tokens whose first component names no real directory ("a miss would
be unknowable"), and returns `True` for every absolute token, *"there is
nothing else it could be relative to"*. So the one token in the corpus that
is guaranteed not to be a path is also guaranteed to be checked.

Direct falsification of the mechanism, before touching anything:

| input | path tokens |
|---|---|
| `sed -n '/^=* FAILURES/,/^=* short test summary/p' log` | `['/^']` |
| `sed -n '/^Z* FAILURES/,/^Z* short test summary/p' log` | `[]` |
| `token_exempt_reason('/^')` | `None` |
| `token_exempt_reason('/^=*')` | `placeholder: a template the reader fills in` |

One character. The control with no `=` was never broken.

**Where the fix went, and why not where I first put it.** My first patch put
`TOKEN_PLACEHOLDER_RE.search(word)` in `path_tokens`, and
`test_claim_check.py::TestExemptionGateHasOneHome::test_the_suppression_
regexes_are_used_only_inside_the_gate` went red — correctly. Round 411 had
already learned that the exemption must have exactly one home, because
`check_paths` has a second door. So the policy went **into the gate**:
`token_exempt_reason(tok, ..., word=None)`, one line, one reader of the
regex, and `path_tokens` passes the containing word. A marker anywhere in
the word makes every fragment of that word a template — which is the honest
statement of the rule, and it belongs where the rule lives.

Corpus-wide blast radius of the new rule, measured over 117 skills and 615
commands: it drops **exactly one** token — the phantom — and no real path.
`--out=state/whence/y.json` still yields its path.

The wider class is 2, not 1: `copied-mirror-drift:159` has
`f568a79^:languages/whence/whence/interp.py`, a git revision-spec. It never
fired C001 because it is *relative-looking* and `is_anchored` refuses it.
The absolute-token exemption is the whole difference.

## 3. The same defect, one checker over — found by a test, not by me

Widening `find_banks` turned `test_xref_check.py::TestAPredictionBank
IsADatedRecord::test_every_bank_the_ledger_checker_finds_is_dated_scope`
red. That test pins a real coupling: *`find_banks` is the definition of "a
bank" in this repo; no file it returns may be held to the authoritative
citation standard.*

`xref_check.HISTORICAL_RE` had enumerated `.md` on every round-scoped
alternative, exactly as `find_banks` had. It is now widened to
`(?:md|json)` with an optional `-<n>` sequence suffix, and deliberately NOT
into an extension-free match: `state/prediction-bank-ledger.json` and
`state/known-absent-paths.json` must stay `authoritative`, and they do,
because neither carries a round number. Pinned five ways in
`TestTheDatedScopeFollowsTheLedgerCheckersSweep`.

**Third instance of one shape in one round, and the third was found by a
coupling test rather than by reading.** That is the argument for the
coupling test.

## 4. A fourth instance, made by this round, in a checker with no coupling test

Merging the skills read-set map (§5) grew `harness/readset-map.json` from
1.44 MB to 2.92 MB. `selfdesc_check`'s artefact count went **61 → 60** and
nothing said why. `MAX_BYTES = 2_000_000`, and the skip was a bare
`continue`.

So `61 artefact(s) of 757 json file(s)` was a fact about the cap. Uncapping
the report shows the cap had been dropping **41 files** silently; 32 of them
were `logs/round-NNN.json` JSONL streams that were never artefacts, which is
why the honest fix classifies before it complains (`_is_jsonl` reads one
line, so it costs the same as skipping):

```
skipped: 4 file(s) over the 2000000-byte cap, NOT audited:
  harness/readset-map.json, nuc/tokenizer-qwen36.json,
  state/swe/round-503/sweep-repo.json, state/whence/round-470/tests-census-829.json
```

Three of those four have been outside the audit for many rounds and no round
has ever been told. The cap is unchanged — raising it is a cost decision
this round did not make — but it now names what it drops, above the summary
line (round 417's rule: `corpus_check` keeps `lines[-1]`).

## 5. The instrument that should have reached the openers, and could not

The round prompt recommends `python3 harness/readset.py blast` — round 505's
answer to the fact that 83% of red episodes are opened by a round that
cannot see them. I ran it against the two diffs that opened these reds.

**Before (HEAD's map, 841 keys):**

```
round 511 diff -> IMPLICATED skills/...  0 files
round 512 diff -> IMPLICATED skills/...  0 files
```

Not "it missed them". `harness/readset-map.json` contained **zero** nodes
under `skills/` — the map is a merge of three recorded runs (whence,
harness, nuc) and the skills corpus suite was never one of them. For any
diff whatsoever, `blast` answers *"no recorded node reads or scans this"*
about the suite holding four of the eight current reds. Absence in a map,
read as absence in the world: §1's defect, one level up, in the tool built
to prevent §1's defect reaching the wrong round.

**Closing it.** `readset.py record` over `corpus_check`'s own `unit_tests`
argv: 1191 nodes rostered, 616 keys with evidence, 57 420 audited events, in
147 s (pytest rc=1 — a failing test still reads what it reads, which is why
`record` accepts rc 1 and refuses rc 2/3/4). Re-merged **from the three
original round-510 source maps plus the new one**, not from the previous
merge output — merging a merge collapses `sources` from three entries to
one, which I did first and caught by diffing the artefact's own metadata.
841 → 1456 keys, and HEAD's node set is a strict subset.

**After:**

```
round 511 diff -> IMPLICATED 16 skills files, including
                  test_case_coverage.py (9 keys), test_claim_check.py (3),
                  test_carryforward_check.py (14), test_corpus_check.py (3)
round 512 diff -> IMPLICATED the same 16, carryforward 14 keys
```

Those are the suites that carried the reds. Both rounds could have been told
before committing, for the price of one command.

## 6. And the cheaper instrument that already existed

`corpus_check.py --precommit` — every checker except `unit_tests` — exists,
is documented in its own `--help` as *"for a round to run on its own tree
BEFORE its last commit"*, and on this `nproc=1` box takes **36.4 s**
measured. Run on the tree as I inherited it, it prints all three ERRORs.

So the three-round, four-node debt was preventable by a 36-second command
that had been in the tree since round 463 — and nothing routes a non-skills
track to it. `blast` was blind; `--precommit` was merely unmentioned. Those
are different gaps and only the first needed building.

## 7. P001 — the one that was a real missing obligation

`skills/red-debt-triage/SKILL.md` (round 511, harness A) shipped with **0**
cases. This is `research-state.md`'s carried item 9, verbatim: *a non-skills
round authoring a skill owes it three positive trigger cases (P001, an
ERROR) and a runnable Verification command (C001)*. Round 511 owed both and
paid neither — and its C001 was §2's phantom, so the "runnable Verification
command" half was a false accusation and the "three cases" half was true.

Four cases added (`rdt-near/mid/far` + the negative `rdt-neg`), written by a
different round from the description — the independence round 357 asked for.
Registered unprobed in `state/known-unprobed-skills.json` with an owner and
a scorable prediction, because a probe is a priced live run and this session
had no authorisation for a spend.

## 8. The skill

`skills/absence-retested-on-the-raw-input/SKILL.md` — 4 cases, registered
unprobed. §§1, 2, 3 and 4 are four instances of one shape in one afternoon,
in four different checkers, three of them written by rounds that knew about
the other two:

> A checker that reports a positive holds the thing it found. A checker that
> reports an ABSENCE holds the failure of a predicate. The absence is a fact
> about the far side of the derivation; the message is almost always written
> about the near side. The cost is not a wrong verdict — it is a **wrong
> repair**.

The move is one line of code: re-test the negative directly against the raw
thing the subject named, before wording it. `os.path.exists(e["bank"])`.
The raw word before the split. The roster of the map you are about to trust.

## 9. Predictions, scored

Banked in `state/round-513-predictions.md` before any measurement in §§1-6.
**12 banked: 8 HIT, 4 MISS.**

| id | verdict | note |
|---|---|---|
| P1 | **HIT** | the `=` in the split class is the cause; the no-`=` control yields zero tokens and `/^=*` is exempt while `/^` is not |
| P2 | **HIT** | 0 other instances of that exact mechanism corpus-wide (band 0-2). Widened honestly: the regex-anchor CLASS is 2, and the second is suppressed by `is_anchored` |
| P3 | **HIT** | exactly as posed — the `.md` copy moves K003 to the other branch rather than silencing it. Run, not reasoned |
| P4 | **HIT** | 3 non-`.md` bank-shaped files (band 2-6). The prediction did not foresee that one of the three would be the ledger, which is the trap in the widening |
| P5 | **HIT** | exactly 1 ledger entry names a non-`.md` bank, and its file exists |
| P6 | **MISS** | predicted `blast` WOULD implicate `test_case_coverage.py`. It implicated nothing: the map has zero skills nodes. Wrong for a more useful reason than being right |
| P7 | **MISS** | same, same cause |
| P8 | **MISS (low)** | 36.4 s against a 40-150 s band, and the premise was wrong too: I predicted the free tiers' cost as if `--precommit` had to be built. It already existed |
| P9 | **HIT** | `corpus_check` reaches 0 errors; the last one standing is this round's own K001, discharged by the ledger entry below |
| P10 | **HIT** | 24 new tests (7 carryforward + 8 claim_check + 5 xref + 4 selfdesc), band 14-25 |
| P11 | **MISS** | predicted case_coverage warnings stay at 31. They went to 32 — I forgot my own new skill enters the corpus it is counting — and then to 30 once both P004s were acknowledged. Two errors in one line |
| P12 | **HIT** | C001 and K003 share one cause, P001 has a different one. Understated: the round found two MORE instances of the shared shape (§3, §4) that the bank did not anticipate |

**The bank's value was P6/P7.** Being wrong about them is what produced §5:
had `blast` merely missed the nodes, the finding would have been "run it
more often". Its map being *empty of the whole suite* is a different repair
and a bigger one.

**The miss with a lesson is P11.** It is the memory rule *your own artefacts
are in the corpus* — I scoped the prediction to the EDIT and the instrument
counts the ROUND.

## 10. What this round did not do

- **Did not probe** either skill. A probe is a priced live run; both are
  registered with an owner and a scorable prediction instead.
- **Did not raise `MAX_BYTES`.** The four dropped files are now named; three
  of them predate this round and sizing the audit is a cost decision with
  no measurement behind it yet.
- **Did not re-record the whence/harness/nuc maps.** They are round 510's,
  recorded at `b38051d`/`7b61384`, and `blast` reports the staleness itself.
  The merged map's `head` is `DISAGREE` for that reason and always was.
- **Did not touch the other four red nodes** (`test_swe_copyparity_real_
  subject.py` ×3, owner harness(A); `test_survivor_impact.py`, owner
  NUC-integration(E)). They are in suites this track does not run. What this
  round changed for them is that `readset blast` can now name skills nodes;
  it still cannot name theirs any better than before.
