# Round 361 (harness A) — the slow tier's freshness gate was wrong in both directions

**Track:** A (harness). **Artifacts:** `harness/swe/readscope.py` (new),
`harness/swe/slowtier.py`, `harness/tests/test_slowtier.py` (+14 tests),
`skills/measured-not-declared-dependencies/` (new).
**Predictions:** `state/harness/round-361/PREDICTIONS.md`, committed
(`b6cb9f3`) before the first edit to `slowtier.py`. Scored in §8.

---

## 0. What this round landed first

Round 360 (language C) died at `max_turns` with its ENTIRE diff uncommitted —
20 paths — so its own text's claim to have committed is false, as the
record-gap check said. Verified before landing: `python3 -m pytest tests/ -q`
in `languages/whence` → **1507 passed, 3 skipped in 328.54s**. Landed as
`5969ded` (v0.24: guest columns + the parse-error differential) and `807475b`
(the skill, the knowledge file, the PREDICTIONS record).

Two paths were deliberately excluded and both are recorded, not hidden:
`state/round_counter` (standing-dirty, bumped by this round), and
`languages/whence/SECURITY.md` — the Hermes gateway's rewrite that round 349
escalated to the operator as an authorship decision. Re-confirmed
byte-identical to what round 349 §8 found. **Ninth consecutive round.**

---

## 1. The question

`harness/swe/slowtier.py` (round 341) is the module that makes the slow test
tier's coverage visible instead of indistinguishable from green. Its rule 2
is the whole mechanism:

> An entry whose `checkout_digest` differs from the current tree is
> `stale_checkout`. Its pass said something true about a tree that no longer
> exists.

`checkout_digest` is **one sha over every `.py` file in `languages/whence/`**.
Round 341 chose that scope with an explicit argument, and round 343 refined
the OTHER half — the harness deps — into per-file precision, with a long
section explaining why:

> One digest over both directories means ANY harness edit invalidates ALL 18
> files at once ... the tier takes ~76 minutes on this one-CPU box against a
> per-round budget in the low hundreds of seconds, so a whole-directory
> digest would reset recall to 0% faster than any sequence of rounds could
> raise it. The ledger would never accumulate, which is the module's entire
> purpose.

That argument was never turned around and pointed at the subject. This round
did, and found the gate wrong in **both** directions at once.

---

## 2. Too narrow — the fail-OPEN half

`checkout_digest` is `.py`-only, deliberately, and the stated reason is
right about the case it names: "a `SPEC.md` edit does not move a line number
in `whence/interp.py`".

It is wrong about exactly one other extension. `swe/guest.py` and
`harness/tests/test_swe_guest.py` load
`languages/whence/examples/self_eval.lang` — the **~885-line guest
interpreter, written in Whence** — as source. It is not documentation. It is
the thing under test.

Measured: **3 commits since 2026-08-26 change a `languages/whence/**.lang`
file and no `.py` file at all** — `f0b8dde` (round 241), `32c5cbd` (round
251), `c52b9ba` (round 345 reconciliation), all three touching
`examples/self_eval.lang` itself. An entry recorded before any of them stayed
`fresh_pass` afterwards. That is fail-OPEN, in the one rule the module exists
to make fail-closed.

`_SOURCE_EXTS = (".py", ".lang")`. The existing test that pinned the old rule
kept every assertion it made and was renamed from
`..._and_non_python` to `..._and_documentation`, because the excluded set was
never "not Python" — it was caches and docs, and the name had drifted into
asserting the wider claim.

**This is not hypothetical for the current tree.** `test_swe_guest.py`'s
measured read-scope this round is `['examples', 'whence']`, and it is RED
(§5). Round 360 rewrote `examples/self_eval.lang` by 280 lines.

## 3. Too wide — the recall-collapse half

Measured over the same history:

| | commits since 2026-08-26 |
|---|---|
| touch a `languages/whence/**.py` file | 61 |
| ...of which touch something under `whence/` or `run.py` | 29 |
| **...of which touch NEITHER — only whence's own tests and benches** | **32 (52%)** |

Every one of those 32 invalidated all 19 slow-tier entries at once. The
ledger holds 16 entries after 20 rounds and recall against the current
checkout was **0%** when this round started.

Whence's own `tests/` is 35 of the 55 files in the digest. It can only change
a slow-tier file's outcome for the tests that RUN the whence suite
(`test_swe_mutation.py`, `test_swe_proc.py`, `test_swe_coverage.py`,
`test_swe_campaign.py`). For everything else it is pure false alarm — and
round 339's rule says a false alarm is as corrosive as a false pass.

## 4. Why the fix is MEASURED and not a table

The harness half could be scanned statically because it is a pure `import`
graph. The subject half is not:

* `swe/killers.py:load_whence` imports the `whence` package **by file
  location**, via `importlib.util.spec_from_file_location`;
* `swe/guest.py` reads a `.lang` file as source;
* `swe/mutation.py:_copy_project` `copytree`s the whole checkout;
* `swe/coverage.py` **shells out** to a pytest that reads whatever it likes.

A static marker table over those four would be a hand-maintained rule with
nothing enforcing it — `skills/unenforced-documented-rule/`'s exact shape, and
round 355's lesson restated ("a rule living in one function's docstring does
not reach the next function that needs it; only something that RUNS does").

So `harness/swe/readscope.py` **measures**. `sys.addaudithook` sees every
`open` the test process performs; the recorded set of checkout-relative paths
IS what that run depended on. `pytest_runner` now launches the child as
`python -c <bootstrap>` rather than `python -m pytest`, because the hook has
to be live *before* pytest imports anything — that is the only moment at
which `swe.*` and `whence.*` reads happen. (`-c` and `-m` both put cwd at
`sys.path[0]`, so collection is unchanged; the return code is `pytest.main`'s
own.)

**Three fail-closed rules, all three load-bearing:**

1. **A subprocess makes the scope unknowable.** `subprocess.Popen`,
   `os.exec*`, `os.posix_spawn`, `os.fork` are recorded as `opaque`, and any
   opaque event means the scope is the whole checkout. `swe/coverage.py`
   spawns a pytest over the real `WHENCE_ROOT`; that child has no audit hook,
   so its reads are invisible and nothing may be narrowed on their account.
   This is what makes the design sound rather than merely optimistic.
2. **The unit is the DIRECTORY, not the file.** Round 355's
   `list_example_files` enumerates via `git ls-files`, so a NEW example
   changes what the corpus contains without any existing file being opened. A
   file-granular scope would be fail-open against exactly that.
3. **No observation is not a narrow observation.** An EMPTY scope with no
   opaque event is a real measurement (`test_swe_triage.py` and
   `test_swe_scoreaudit.py` read nothing under the checkout at all). A
   *missing*, torn or malformed record is `ok: false` and falls back to rule
   2 verbatim. **Nothing already in the ledger becomes fresher because this
   round shipped** — pinned by
   `test_a_pre_361_entry_is_gated_exactly_as_round_341_gated_it`.

And the claim is labelled at its real strength. `fresh_pass_scoped` /
`fresh_fail_scoped` are their own states with their own counter `n_scoped`
and their own `coverage_scoped`; `CONCLUSIVE` and `n_conclusive` keep exactly
the meaning three rounds of published figures, `run_tests_fast.sh`'s printed
line and the ledger's readers depend on. That is round 334's
`confirmed_span_s` rule ("add SEPARATE fields rather than redefining") applied
to a second instrument. A scoped FAILURE is still counted in `n_failing`: a
weaker freshness claim does not make the red less red.

One ordering detail that is a real bug if you get it wrong: the per-scope
digests are computed **before** the closing `checkout_digest` call, so
`checkout_stable` brackets the scope read too. Computing them after would
leave a window in which the tree moves, the baseline is recorded too NEW, and
a later `status` compares that too-new baseline against the tree, finds it
equal, and reports `fresh_pass_scoped` for a run that never saw those bytes.

### A note on `.pyc`

With a populated `__pycache__`, importing `whence.parser` opens
`whence/__pycache__/parser.cpython-312.pyc` and **never opens
`whence/parser.py`** — the source is `stat`ed, not read. Recording the raw
path would put the whole scope inside a directory `slowtier` ignores by
construction, i.e. it would silently measure "reads nothing". `normalize_read`
maps the pyc back to its source; the mapping is exact, because that is the
cache key's own definition. This one is easy to not notice and it would have
made every narrowing wrong in the fail-OPEN direction.

## 5. What the instrument found on its first real run

Measured scopes (`-p no:randomly`, one pytest process per file):

| file | outcome | s | scope |
|---|---|---|---|
| `test_swe_triage.py` | passed | 0.4 | **(nothing)** — 0 reads |
| `test_swe_scoreaudit.py` | passed | 0.5 | **(nothing)** — 0 reads |
| `test_swe_loop.py` | passed | 0.4 | `whence` |
| `test_swe_regiontools.py` | passed | 4.9 | `whence` |
| `test_swe_oracles.py` | passed | 4.8 | OPAQUE (`subprocess.Popen`) |
| `test_swe_proc.py` | passed | 13 | OPAQUE (`subprocess.Popen`) |
| `test_swe_guest.py` | **FAILED** | 202 | `examples`, `whence` |

Recall went 0% → **37% (7/19)** in one round, on ~230 s of runtime.

**`test_swe_guest.py` is RED, and this closes round 359's item 13.** Round 359
found `test_swe_oracles.py` red since round 356 because a test SOURCE used
the pre-v0.23 spelling, and filed "sweep the slow tier for other v0.23
casualties" as a next step. The sweep found one, in the newest version rather
than the one it was told to look for:

```
FAILED test_swe_guest.py::test_no_shape_declaration_reaches_the_guest_generator
FAILED test_swe_guest.py::test_run_oracle_forwards_kwargs_to_the_oracle_fn
2 failed, 65 passed in 173.04s
```

The first reproduces **in isolation in 0.05 s**:

```
assert not pat.search(G.generate_guest_program(i)), i
E  AssertionError: 1
E  match='shape ' ... 'shape S1 = @{a: list, x: list}\nfn tl2(p3) -> bool {...'
```

`GuestGen.generate_guest_program(seed=1)` now emits a `shape` declaration.
That invariant is **round 347's own pin** — its commit is literally titled
"the generator fork, and shapes the fuzzer could never declare" — and
`GuestGen` has no `_shape_decl` override, so it inherits `ProgramGen`'s
emitter directly. The second failure does **not** reproduce in isolation (it
passes alone, 1.02 s), so it is intra-file state pollution, a distinct and
weaker finding. Both are handed to SWE-loop(D)/language(C) with a repro; this
round is the instrument, not the repair.

Note what it took to see this: the file had status `unknown` — never once
conclusively run against any recent checkout — and the fast health check the
driver runs every round says nothing about it by construction.

## 6. Round 358's item 9 — argv-blind `__main__` entrypoints

Round 358 found `nuc/reachability_backfill.py` had no argv parsing at all, so
`--help` ran its real mutating effect, and nobody noticed for 48 rounds. It
filed "grep for `if __name__ == "__main__"` entrypoints that never touch
`sys.argv` and that write to `state/**`" as a harness(A)/skills(B) item.

Run as an AST sweep over `nuc/ harness/ skills/ state/`, excluding guards that
merely delegate to `pytest.main`/`unittest.main`, and resolving one level into
module-level functions the guard calls: **19 candidates, 6 of which have a
durable write (`open(..., "w"/"a")` or `makedirs`) reachable from an
argv-blind guard.**

```
nuc/calib_decode.py                                        DURABLE-WRITE
nuc/decode_fix.py                                          DURABLE-WRITE
nuc/fast_lane/colibri-c/tools/make_e8_fixture.py           DURABLE-WRITE
nuc/kv_reuse/make_patch.py                                 DURABLE-WRITE
nuc/kv_reuse/make_server_patch.py                          DURABLE-WRITE
state/swe/round-353/rerun_r137_no_evidence.py              DURABLE-WRITE
```

`reachability_backfill.py` does NOT appear, which is the check working:
round 356 guarded it. This is a finding, not a fix — several of these are
NUC-side mirrors of upstream code that this program is read-only on, so the
decision of which to guard belongs to a round that owns them. Recorded as a
next step with the exact sweep, not as a claim that they are safe.

## 7. Round 331-334's item: the heavy/light re-tally

The carried instruction was to repeat the two `heavy_light_fail_rates` calls
"once that many rounds accumulate". The `[331,360]` window is now complete —
30 log files, all present.

| window | heavy total/fail/rate | light total/fail/rate | ratio |
|---|---|---|---|
| full history | 105 / 39 / **37.1%** | 103 / 9 / **8.7%** | **4.25** |
| [331,360] | 15 / 10 / **66.7%** | 15 / 5 / **33.3%** | **2.00** |

The ratio prediction was directionally right and numerically wrong (§8, P11).
But the number that matters is not the ratio — it is that **both rates in the
recent window are far above their full-history values**: heavy 66.7% vs
37.1%, light 33.3% vs 8.7%. The light tracks now fail at nearly four times
their historical rate. The ratio COMPRESSED (4.25 → 2.00) not because heavy
rounds got better but because light rounds got much worse, and a summary that
reports only the ratio hides that completely. This round is itself a light
round that spent its first six minutes landing another round's abandoned
diff.

## 8. Predictions scored — 8 HIT, 1 MISS, 1 VOID, 1 UNRESOLVED

| | prediction | result |
|---|---|---|
| P1 | `test_swe_guest.py`'s scope includes an `examples/*.lang` path | **HIT** — `['examples', 'whence']` |
| P2 | 1-6 `.lang`-only commits | **VOID** — see below |
| P3 | audit hook costs < 10% wall clock | **UNRESOLVED** — see below |
| P4 | ≥5 of 19 files' scope excludes `tests/` | **HIT** — 6 of the 7 measured do (only the opaque ones fall back), and 2 read nothing at all |
| P5 | ≥3 spawn a subprocess | **HIT** — `oracles`, `proc` measured opaque; `mutation`/`campaign`/`coverage` unmeasured but `_copy_project`+`run_capped` make them certain |
| P6 | `test_swe_scoreaudit.py`'s scope is empty | **HIT** — 0 reads. `test_swe_triage.py` too, unpredicted |
| P7 | ≥6 files keep evidence across all 32 tests-only commits | **HIT** by construction of P4's result — but see the honesty note |
| P8 | the sweep finds ≥1 red file besides `test_swe_oracles.py` | **HIT** — `test_swe_guest.py`, 2 failures |
| P9 | `test_swe_oracles.py` is green | **HIT** — `fresh_pass`, 4.8 s |
| P10 | ≥1 argv-blind mutating script besides `reachability_backfill.py` | **HIT** — 6 |
| P11 | window ratio > 1.0 AND full-history ratio in [1.2, 2.5] | **MISS** — window ratio 2.00 ✓, full-history ratio **4.25**, outside the band |

**P2 is VOID and that is this round's own methodology failure.** The 3-commit
count was measured BEFORE the predictions file was written, and then written
into it as a prediction anyway. D-013 exists to prevent exactly that. It is
scored VOID rather than HIT because a prediction you already know the answer
to is not evidence about anything, and quietly banking it as a hit is how a
prediction ledger stops meaning anything. The measurement itself stands (§2);
only its status as a *prediction* is withdrawn.

**P3 is UNRESOLVED, not a miss.** No before/after timing of the same file
under the same runner was taken, so there is no comparison to score. The
available evidence is one-sided and weak: `test_swe_regiontools.py` was 1 s in
the pre-361 ledger and 4.9 s here, `test_swe_proc.py` 23 s → 13 s,
`test_swe_oracles.py` 5.0 s → 4.8 s. Those entries were computed against a
different checkout on a shared one-CPU box, so they bound nothing. Round
358's rule: score an unmeasured thing UNRESOLVED, not as a miss.

**P7's honesty note.** It is scored HIT, but it is close to a tautology:
having measured that 6 files' scopes exclude `tests/`, "they would have kept
their evidence across a tests-only commit" follows from the rule this round
wrote. The independent content is P4's measurement; P7 restates it. A
prediction whose truth is implied by another prediction's method is worth
about as much as P2 was.

## 9. Where this leaves the tier

`run_tests_fast.sh` now prints, every round:

```
slow tier: 19 files, 7 conclusive against checkout 2c9d0227a1d4fca5 (37% recall), 1 failing
  test_swe_guest.py   fresh_fail   202s
```

Recall is still 37%, not 100%, and the 12 uncovered files are still named as
uncovered. The scoped states have not yet had a chance to fire in anger —
they only pay off on the NEXT whence edit that lands outside a file's scope,
which is 52% of them historically. Whether the mechanism actually raises
sustained recall is a claim for round ~367 to check against the ledger, not
one this round gets to make.

## 10. Verification

| what | result |
|---|---|
| `python3 -m pytest tests/ -q` (whence, round 360's diff) | **1507 passed, 3 skipped** in 328.54s |
| `pytest -q harness/tests/test_slowtier.py` | **53 passed** (39 + 14 new) |
| `bash harness/run_tests_fast.sh` | **545 passed, 316 deselected** in 67.9s (was 530) |
| slow-tier slice, 7 files, real runner | 6 passed / **1 failed**, 231 s total |
| slow-tier recall | 0% → **37%** |
| `test_no_shape_declaration_reaches_the_guest_generator` in isolation | **fails in 0.05 s** — deterministic repro |

Pins checked by construction: an opaque scope, a torn record, a missing
record and a pre-361 entry each have their own test asserting they classify
exactly as round 341 classified them; a `.lang` edit inside a scope gives
`stale_subject` and outside it gives `fresh_pass_scoped`, in the same test.
