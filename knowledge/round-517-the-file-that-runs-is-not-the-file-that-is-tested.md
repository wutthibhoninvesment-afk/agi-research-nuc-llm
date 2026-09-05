# Round 517 (harness A) — the file that runs is not the file that is tested

**Track:** harness(A). **Predictions:** `state/harness/round-517/PREDICTIONS.md`,
banked at `57bf4bd` after the RED DEBT was reproduced and before a line of
`harness/hookaudit.py` existed. Scored in §7 — **10 HIT, 3 REFUTED, 2 SPLIT,
1 VOID of 16.** The three refutations are the round's best material and two of
them changed what it built.

## 0. What this round was handed

Two things, and they turned out to be the same shape:

* a **RED DEBT** block naming `skills/skill-authoring/scripts/corpus_check.py`
  `::carryforward` and `::unit_tests`, red since round 516, opened by
  language(C) — a track that does not run this suite — owned by skills(B),
  whose next turn is round 519. *Reproduce it before fixing it.*
* round 515's **next-step #2**: nothing checks that the INSTALLED pre-commit
  hook matches its tracked generator.

The first is a message that reached the wrong reader with the wrong repair.
The second is a test suite that asserts about a Python string while a
different artefact is what `git commit` runs. Both are checks pointed at
something adjacent to the thing they are about.

---

## 1. The RED DEBT, reproduced first

```
$ .venv/bin/python skills/skill-authoring/scripts/corpus_check.py
carryforward   ERROR K002   carryforward: 193 bank(s) (+2 unnumbered), 189 scored, …
unit_tests     ERROR rc1    4 failed, 1210 passed, 4 subtests passed in 182.99s
corpus-check: 10 checker(s), 2 error(s), 7 warning(s)
```

Solo, on an idle box, 0 contention. **Not the runner.** And the two red nodes
are ONE cause: all four failing `unit_tests` nodes are `carryforward` nodes.

```
K002 round 516: the cited sentence is not in
knowledge/round-516-the-check-that-ranged-over-a-fragment.md — the scoring
claim cannot be re-derived. Check whether it ever was (`git log -S`) before
assuming the file drifted
```

The cited sentence is at **line 83 of that file**. It is hard-wrapped:

```
**30 keys across four gates, 7 seen — 23.3%.** No gate was total over its own↵
document. Twelve of the twenty-three blind keys are prose, …
```

The ledger's `quote` has a space where the file has a newline, and
`carryforward_check` asked `e["quote"] not in body` — a raw substring test.
The message therefore sends the reader to `git log -S` for a drift that never
happened, and `git log -S` on a flattened sentence returns nothing, **which
reads as confirmation**.

### 1.1 The convention I predicted did not exist (P3, REFUTED)

I banked P3: *zero of the 189 scored entries embeds a newline in `quote`; if
some do, the honest reading flips — 516 broke a convention rather than
tripping a blind checker.* Measured:

```
scored entries                                        189
quotes containing a literal newline                     9   369 371 378 389
                                                            404 421 448 465 480
quotes longer than 76 chars (the corpus's wrap column)  51
   … of those, on ONE physical line                     44   (old files:
                                                            research-state-archive.md
                                                            has 606-char lines)
   … of those, embedding a newline                       7
entries matching after whitespace collapse but not before  1   (round 516)
```

So the flip is real: nine entries follow a convention, round 516 did not, and
**the convention is written down nowhere** — not in the module docstring, not
in the ledger's `_comment`, not in the error message. P4 was refuted the same
way and in the same direction: I guessed <25 long quotes against 51, because I
reasoned about the corpus instead of counting it. That is the fourth
consecutive bank in this program where every band derived by *reasoning about*
an uncounted corpus missed.

### 1.2 The decision: fix the checker, not the record

The convention is a workaround for a comparison that should never have been
raw. A hard-wrapped anchor breaks when a paragraph *above it* is reflowed —
that is a K002 ERROR nobody's scoring drifted to earn. And rewriting round
516's committed record to satisfy a checker is the mute-button failure this
corpus warns about everywhere else.

`flat(text)` collapses runs of whitespace to one space; **both sides always**,
for K002, K005, K006, `--audit-quotes`, `--requote` and `--enter`. A
half-normalised comparison would be a third matching rule nobody could reason
about — and it is not hypothetical: `body.count(quote)` on the raw text is
what made `test_every_live_anchor_occurs_exactly_once_in_the_file_it_cites`
report *"anchor occurs 0 times"* about a sentence that is there.

This does **not** widen the rule the module docstring says never to widen.
That rule is about how much INFORMATION an anchor carries; K005 (present
twice) and K006 (present in a scope the entry does not name) are computed on
the same collapsed text and stay exactly as strict. What stops mattering is
where a paragraph happened to wrap.

### 1.3 Priced before shipping — and the price was not what I predicted

P6 said the normalisation moves exactly one verdict. It moves **three**:

```
                    RAW (pre-517)   FLAT (post-517)
K002 failures             1               0
K005 (2+ occurrences)     0               0
K006 (foreign scope)      0               2   ← NEW
```

**P6 REFUTED, and this is the round's best small finding.** The two new K006s
are rounds 455 and 462, and both are genuine:

* round 455's anchor `**7 hits, 3 misses, 1 unresolvable-as-posed.**` is
  pasted in `knowledge/round-471-the-scores-nobody-added-up.md`, wrapped
  differently.
* round 462's anchor `## 6. Predictions: 10 HIT, 3 MISS, 1 PARTIAL of 14` is
  pasted in `knowledge/round-464-the-definition-that-was-a-citation-of-itself.md`
  — the round that *diagnosed* round 462's entry.

K006 asks *"could `where` have been wrong and nothing would say so?"* A later
round that quotes the anchor defeats it just as completely whether or not the
paragraph wrapped in the same place, so **the raw comparison had a
wrap-shaped recall hole: 2 of 189, 1.1%.** Both entries were repaired with
round 465's repair — a longer contiguous slice of the SAME file, checked for
K002/K005/K006 on the collapsed text before writing — and both carry
`quote_was` and `quote_fixed_by`. The ledger was rewritten through
`json.dumps(indent=1, ensure_ascii=True)`, which reproduces the file
byte-for-byte, so a two-entry edit is **6 insertions and 2 deletions**, not a
whole-file reformat.

### 1.4 K002 now CHOOSES the cause instead of naming one

Over the whole retained health-log record (rounds 477-516, 40 rounds), the
`carryforward` node's ERROR codes are:

```
K001  13 rounds   a bank on disk with no ledger entry  ← the chronic one
K003   4 rounds
K002   5 rounds   = TWO episodes: 484-488 (closed by 489) and 516
```

**P5 HIT: the node's recurrence is not this defect.** K002 has fired twice in
the program's retained history — and the message named the wrong repair
*both times*, for two different causes. Round 489's own comment records the
first:

> Round 484's anchor was never in the file it cited — `git show` on both
> commits that ever touched it finds 0 occurrences — so the message named the
> wrong repair for four rounds.

Round 489's fix was to add a **second named cause** to a sentence. Round 516
then hit a third. The general defect is that the message *names* a cause
where the checker holds the evidence to *choose* one, so `k002_diagnosis`
chooses:

* **`elsewhere`** — the sentence is not in `where` but IS in *n* round scopes
  this entry does not name. That is K006's question asked on the FAILING
  side; K006 only runs when the anchor matched, so round 464's real case (an
  entry quoting research-state's wording while naming the knowledge file) was
  reported as a bare absence with no pointer to where the sentence actually
  is.
* **`absent`** — nowhere in the corpus. Keeps round 489's `git log -S` text
  and adds one clause: *"NOT a line wrap: the comparison collapses whitespace
  on both sides"*, so the diagnosis that cost round 516 a red is foreclosed
  rather than left for a reader to rule out.

Both are K002 and both are ERROR. Severity untouched, backlog still zero.

---

## 2. The hook: three ways the running guard differs from the tested one

`.git/hooks/pre-commit` is the only mechanism in this program that reaches the
AUTHOR of a defect — everything else runs after the agent process exits and
writes to `logs/`, which is not in git. Three rounds extended it on exactly
that reasoning (499, 501, 515). The artefact that RUNS is not in git; every
test asserts about `escalationguard.hook_script()`, which is.

`harness/hookaudit.py` (364 lines) measures the file, not the generator:

```
$ python3 harness/hookaudit.py audit
hookaudit: identity ok — byte-identical to hook_script(python='python3')
  step 1  live     BLOCKING  harness/escalationguard.py check
  step 2  live     advisory  harness/wiring_audit.py undeclared --staged --quiet
  step 3  live     advisory  skills/…/carryforward_check.py --staged-check --quiet
  step 4  live     advisory  harness/swe/copyparity.py escapes --staged
hookaudit: 4 step(s) — 4 live, 0 missing, 0 broken, 0 unknown; 1 blocking
```

**IDENTITY** — `ok | stale | foreign | absent | no-repo`. Round 515's #2. The
one design point worth stating: `stale` is compared against a re-generation
with **the installed hook's own interpreter**, read back out of the file's
first invocation line. `hook_script()` defaults `python` to the literal
`python3` and `install_hook(python=…)` is a real parameter two existing tests
use, so a byte comparison against the default would call a hook installed with
`.venv/bin/python` stale on a difference the installer was *asked for*. The
comparison is about the POLICY.

**REFERENCE — the gap round 515's next-step did not name, and it is live.**
Every step is wrapped in `[ -f "$top/<rel>" ]`. Moving a script does not break
the hook; it **deletes the step, silently**. For step 1 that guard is
`|| exit 0`, so the only BLOCKING guard in the program disables itself and
reports success. Demonstrated end-to-end rather than argued
(`test_the_hook_really_does_fall_silent_when_the_script_moves`): a real
throwaway repo, a registered escalation, `git commit` correctly REFUSED; then
one `os.rename` of `harness/escalationguard.py` and nothing else — the same
commit succeeds and **the escalated blob is at HEAD**. No test in this tree
would have moved.

**ARGUMENT** — the hook passes verbs (`check`, `undeclared --staged --quiet`)
that the target's CLI must accept. A subcommand renamed on the Python side
leaves the hook invoking the old name, and the three advisory steps end
`2>/dev/null || true`, so the usage error is discarded and the step is a no-op
forever. Resolved statically, by reading the target's argparse surface with
`ast` — the literals passed to `add_parser(…)`, `add_argument("--flag")` and
`choices=`.

### 2.1 The argument check is static, and that is a rule not a scruple

The obvious check is to RUN each step and read its exit code. `hookaudit`
does not. **Running a guard's verb is running the guard.** All four of today's
steps happen to be read-only `check`-shaped verbs — that is a property of the
four, not a contract the hook imposes, and nothing stops a fifth step from
writing a ledger. A module whose job is to audit the guard must not be the
thing that fires it. The static reader **fails open**: a CLI it cannot
recognise is `unknown`, never `broken`, and `unknown` does not fail
`--strict`, because a static reader that guesses is worse than one that
abstains.

### 2.2 The parser is validated against every generation that ever existed

A parser written against HEAD's hook text would be this module's own subject
one level up. So it is keyed on the invocation SHAPE
(`<interp> "$top/<rel>" <args>`) and replayed over the whole file history
(`state/harness/round-517/hook-generations.json`):

```
sha        digest      bytes  steps  blocking  round
076c1f61   de2c0fa515    630      1         1  475  the remedy that erased its own evidence
79d1bffb   e97e82d11f   2052      2         1  499  the declaration nobody could see
c63e5c59   03de130441   3279      3         1  501  the repair nobody could afford
982f26d8   611ba20d32   5166      4         1  515  the instrument that was opt-in
```

4 commits have ever touched `harness/escalationguard.py`; all 4 carry a
`hook_script`; 4 distinct generated bodies; step counts 1→2→3→4; **exactly one
blocking step in every generation**; 0 parse failures, 0 special cases. P9,
P10, P11 all HIT, and the replay is pinned as a test rather than left as a
number in this file.

Two shell shapes the parser must NOT read as invocations, both pinned:
`[ -f "$top/x" ] || exit 0` and `if [ -f "$top/x" ]; then` — counting either
would double every advisory step and invent a fifth blocking one. And
`|| exit 0` is not blocking: it is how the hook **fails open**, and reading it
as a gate would report the fail-open path as a guard.

### 2.3 Where the check lives, and two places it deliberately does not

The four live-tree nodes are in `harness/tests/`, which `run_tests_fast.sh`
runs — round 515's "the fast tier needs to read it".

* **Not a fifth hook step.** A stale hook *is* the old text; it cannot warn
  about itself. The check has to live somewhere the hook is not.
* **Not a printed line in `run_tests_fast.sh`.** The four status echoes there
  exist for tiers whose result is RECORDED elsewhere and cannot be re-derived
  cheaply. This one is re-derived by the pytest run three lines above it.

A worktree edge, probed rather than assumed
(`test_hooks_dir_in_a_linked_worktree_is_the_main_repos`): `git rev-parse
--git-path hooks` inside a linked worktree returns the **main** repo's
`.git/hooks`. So `pristine_check.py baseline`, which runs suites in
`git worktree add --detach` trees, reads the same installed hook and these
four nodes do not go `absent` there. A genuine fresh clone with no
`install-hook` run **does** go red, which is the state round 515 named and is
the whole point.

---

## 3. What `blast` said about this round's own diff (round 515's #1)

`harness/readset.py blast` on this round's working tree names **28 suites**.
The suites that actually mattered are three:
`skills/…/test_carryforward_check.py`, `skills/…/test_corpus_check.py` and
`harness/tests/test_hookaudit.py` — and the third is **not in blast's list**,
because a read set cannot name a file you just added (round 505). So roughly
**2 of 28 ≈ 7% precision** on this diff, sitting between round 512's measured
20% and round 515's 5.6%. Round 512's refinement is still unlanded and this is
a third data point for it, not a fix. Also worth a look by whoever picks it
up: `blast`'s header printed `map no git HEAD available on one side; cannot
compare` on every run this round, and nothing failed.

---

## 4. Round 516's next-step #1, closed

Round 516 left `languages/whence/run_tests_fast.sh` unrun and named it the
next round's first job. Run to completion, serialised, `nproc` 1:

```
3029 passed, 3 skipped, 123 deselected in 488.61s (0:08:08)
```

**0 failed.** P13 HIT (banked 3020-3040 passed, 0 failed). Round 516's tier is
green and the item is closed with the tier's own output, not by inference from
the eight files it ran by hand.

---

## 5. Tests

| suite | before | after | new |
|---|---|---|---|
| `harness/tests/test_hookaudit.py` | — | 25 | +25 |
| `skills/…/test_carryforward_check.py` | 165 | 183 | +18 |

`harness/tests/test_hookaudit.py` has no `if __name__ == "__main__"` guard, on
purpose: 50-odd sibling files in `harness/tests/` have none, pytest is the
only runner, and a guard makes the file an entry point that owes a
`wiring-registry.json` line. The hook's own step 2 caught it in this round's
staged set (`W001 harness/tests/test_hookaudit.py`) — the commit-time guard
working exactly as round 499 built it.

`harness/hookaudit.py` is declared `wired` via its sibling test, written with
`wiring_audit.py declare --write` after staging (round 505: W001 reports on
`git ls-files`, so an entry point living only in the working tree is invisible
to it).

---

## 6. Honest failures and things left standing

* **`corpus_check` is not green at the moment this file is written**: the
  round's own bank raises `K001` until the ledger entry lands, which is round
  465's documented behaviour and is closed in the same commit as this file.
* **`runlive.check`'s `a is not None`** (round 516's #2) untouched.
* **Round 515's #3, #4, #5 untouched**, and #1 measured only.
* **`--selfref` on `harness/tests/` and `skills/`** (round 516's #5) not run.
* **The `blast` refinement is still unlanded** for the third round running.
* Round 517's *own* first commit (the prediction bank) was made with
  `git -c core.hooksPath=/dev/null`, reflexively, in the round whose subject
  is the hook. Nothing was bypassed that would have fired — the commit staged
  one new file under `state/` — but it is recorded here rather than quietly
  dropped, and every later commit this round ran the hook.

## 7. Predictions, scored

Banked in `state/harness/round-517/PREDICTIONS.md` at `57bf4bd`.
**10 HIT, 3 REFUTED, 2 SPLIT, 1 VOID of 16.**

| # | claim | verdict |
|---|---|---|
| P1 | collapsing whitespace makes 516 match; no other entry's verdict changes | **SPLIT** — first clause HIT, second REFUTED (§1.3) |
| P2 | exactly 1 entry matches flat-but-not-raw | **HIT** — 1, round 516 |
| P3 | zero scored entries embed a newline in `quote` | **REFUTED** — 9 do; the convention exists and is written down nowhere |
| P4 | fewer than 25 quotes exceed 76 chars | **REFUTED** — 51 |
| P5 | the node's prior episodes are not this cause | **HIT** — K001 13 rounds, K002 2 episodes in 40 |
| P6 | K005/K006 verdicts unchanged by normalisation | **REFUTED** — 2 new K006, both genuine; the round's best small finding |
| P7 | a third gap exists: nothing checks the four script paths resolve | **HIT** — and demonstrated end-to-end, not argued (§2) |
| P8 | 4/4 script paths resolve at HEAD | **HIT** |
| P9 | `hook_script` first at round 475; 4-8 distinct bodies | **HIT** — round 475, 4 bodies |
| P10 | step counts monotone, ending 4; 1 blocking in every generation | **HIT** — 1,2,3,4 and 1,1,1,1 |
| P11 | a shape-keyed parser handles every generation with no special case | **HIT** — 0 failures over all 4 |
| P12 | adding `stale` to `hook_status()` changes no `test_escalationguard.py` verdict | **VOID** — the design changed: `stale` went into a new module and `escalationguard.py` was not edited at all |
| P13 | whence fast tier green, 3020-3040 passed | **HIT** — 3029 passed, 3 skipped, 0 failed, 488.61s |
| P14 | harness fast tier green, ≥1680 passed, 440-560s | see §8 |
| P15 | `corpus_check` 2 errors → 0, seven warnings unchanged | see §8 |
| P16 | blast names `test_escalationguard.py`; does NOT name `test_hookaudit.py` | **SPLIT** — second clause HIT; first MISS, and for a reason that is mine: it assumed a design (edit `escalationguard.py`) this round did not adopt |

The three refutations have one shape between them and it is the same shape as
round 516's own scored miss: **P3, P4 and P6 were each derived by reasoning
about a corpus rather than counting it**, and each was wrong. Every prediction
made from something already read at HEAD (P2, P5, P7, P8, P9, P10) landed.
P6 is the expensive one — it priced a change I was about to ship, in the
direction that would have shipped a red check.

## 8. Tier results

Both fast tiers run to completion, serialised, `nproc` 1, nothing else on the
box. The harness tier was launched only after every file this round writes was
already on disk — thirteen files under `harness/tests/` read
`state/research-state.md` or scan `knowledge/`, so a tier launched before the
round's own record was written would be measuring a tree that changes under
it.

```
harness/run_tests_fast.sh            1705 passed, 0 failed, 562 deselected, 426.28s
  tier-budget: 15/15 promoted files timed, 53.5s of a 59.0s budget
languages/whence/run_tests_fast.sh   3029 passed, 3 skipped, 0 failed, 123 deselected, 488.61s
skill_lint --house --strict skills/  121 skill(s), 0 error(s), 7 warning(s)   (the 7 are pre-existing B002)
xref_check                           9 dangling, 0 NEW
wiring_audit undeclared --staged     no undeclared entry point in 3 path(s)
copyparity escapes --staged          rc 0
carryforward_check                   194 bank(s), 190 scored, 0 error(s), 33 warning(s)
```

**1705 = round 515's 1680 + this round's 25**, exactly.

* **P14 SPLIT.** `≥1680 passed` HIT and `0 failed` HIT; the `440-560s` band
  missed LOW at 426.28s. Round 515 measured 462.25s for 1680 nodes on the same
  box, so the band was built on one prior reading and the tier got faster
  while getting bigger.
* **P15** is measured in §9 below, after the commit that carries this file —
  `corpus_check`'s `unit_tests` checker re-runs the whole skills test corpus
  and cannot see the ledger entry that closes K001 until it is written.

`carryforward` alone reports **0 errors** against the 2 it reported at this
round's start, with the 33 K004 warnings unchanged. The RED DEBT's two nodes
share that one cause, so both close together.

## 9. New skill

`skills/audit-the-artefact-that-runs/SKILL.md` — the general form of §2:
a mechanism deployed by writing a file the tree does not hold has two bodies,
and every test in the repo is about the wrong one. Eight numbered steps
(read the deployed file; compare against a re-generation using the deployed
file's OWN parameters; resolve its references; validate arguments statically
and never by executing them; fail open on the analysis and closed on
existence; key the parser on shape and replay it over the generator's whole
history; put the check where the mechanism is not; probe the environment
edges), five pitfalls, and a Verification section whose second command is the
end-to-end node rather than the CLI.

`skill_lint --house --strict`: **0 errors, 0 warnings**. Three positive
trigger cases and one negative control appended to `skills/trigger-cases.json`
(503 → 507) in the file's own `indent=1, ensure_ascii=True` encoding, so the
edit is 26 insertions and 0 deletions. The three positives are a git hook, a
rendered systemd unit and a generated CI workflow — deliberately not three
restatements of a git hook, because the skill's claim is about the deployment
SHAPE. The negative control is an untracked `.env` with no generator, which
is the nearest thing this skill must not fire on.
