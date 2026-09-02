# Round 452 (language C) — predictions, banked BEFORE measuring

Rule D-013: written and committed before any command in this round's subject
was run. Scored honestly in the round's knowledge file. Round 435's next-step
7 applies: where I have no basis I say so rather than guessing, and an
abstention is recorded as an abstention. Round 419's rule applies: the
DISPOSITION is fixed here, before the numbers, so no measurement can choose
the fix. Round 448's rule applies: every line carries a BASIS tag — `[MODEL]`
read the implementing source, `[SENT]` a previous round's prose about an
artefact I have not opened, `[CMD]` a command already run this round,
`[NONE]` no basis. Round 449's steps 11/12 apply: a wall-time band states its
contention condition and a count band names its counter. Round 450's rule
applies: **a bank line that quotes a predecessor's example inherits that
example's defects** — every program named below is one I will run, not one I
copied out of prose.

**Subject:** round 450's next-step 1 — *"`SHOW_NEST` is now the only thing
between a reader and a deep miss, and nothing measures how often that bites.
v0.43 reports what the renderer could not show, which is the honest answer
and not the complete one: a miss five levels down is REPORTED but never
RENDERED, so `print(x)` and `str(x)` still cannot show it to a program. The
open question is whether the FULL rendering should carry a depth-bounded-
but-deeper cap of its own (`SHOW_NEST` exists for host frames, and
`full_show` already pays O(n) in elements), and it needs a number: the
deepest value any corpus program actually builds. Nobody has measured
that."*

## The number this round is for, defined before it is taken

**Container depth `D(p)`** of a payload `p`:

* `D = 0` for every non-container payload — int, float, bool, str, `Miss`,
  `Closure`, `Builtin`, `Explanation`.
* `D(WList) = 1 + max(D(e.payload) for e in list)`, and `D = 1` for the
  empty list.
* `D(Record) = 1 + max(D(v.payload) for v in fields.values())`, and `D = 1`
  for the empty record.
* `D(Guess) = 1 + D(node.payload)` — because `_show`'s `Guess` branch
  descends with `nest + 1`, so a `Guess` costs a rendering level exactly
  like a container does.

This is chosen to line up with the renderer's own `nest` counter so the two
can be compared without a conversion: `full_show` renders a top-level
container's ELEMENTS at `nest = 0` and `_show` descends only while
`nest < SHOW_NEST`, so the full rendering shows `SHOW_NEST + 1 = 4` container
levels. **A printed value is rendered in full iff `D <= 4`.**

**Two populations, kept apart on purpose.**

* **BUILT depth** — `max D` over every payload reachable in a finished
  program's provenance graph (from the top-level `Env`, the recorded
  `checks`, and transitively through every node's `inputs`). Whence retains
  history, so this reaches intermediates, not just survivors.
* **PRINTED depth** — `max D` over the payloads that actually reach
  `full_show` during the run.

## DISPOSITION, fixed before the measurement

1. **`SHOW_NEST` will NOT change, whatever the number says.** It is the
   BOUNDED SNAPSHOT's cap; its O(1)-host-frames argument is real, eleven
   generated mutation killers quote its output, and `show()` is a published
   builtin whose contract v0.43 explicitly declined to move.
2. **`full_show` will get its OWN cap constant, separate from `SHOW_NEST`,
   whatever the number says** — because decision 52 already argued in this
   file that the bounded snapshot and the full rendering are *different
   promises*, and then left both promises reading one constant. Sharing the
   constant is the reason "lifting the cap" reads as impossible: it is not
   one cap, it is two promises wearing one number.
3. **The measured corpus maximum sets that constant's VALUE and nothing
   else.** If the corpus maximum turns out to be at or below the current 4
   visible levels, the constant is still introduced, its value is still set
   with stated headroom over the measured maximum rather than equal to it,
   and the round says plainly that the corpus does not currently exercise
   it. A measurement that says "no corpus value is truncated today" is an
   argument about TODAY'S CORPUS, not about the renderer's promise.
4. **Escape hatch, declared now so it cannot be invented later.** If I
   cannot demonstrate that the deeper full rendering stays clear of host
   recursion — the exact failure `SHOW_INT_DIGITS` exists to keep out of the
   explanation path — then item 2 is WITHDRAWN, the round lands the census
   instrument and its number only, and that withdrawal is reported as the
   round's result rather than buried.
5. The census is an ARTEFACT, not a script I run once: it lands in the tree
   with its own tests, so the next round to ask this question re-derives the
   number instead of quoting mine.

## Already DERIVED by reading, therefore NOT predictions

Recorded so I cannot later re-label them as hits.

- D1. `values.SHOW_NEST == 3`, and `full_show`'s own `WList`/`Record`
  branches render elements through `show_payload(e.payload, None)` at
  `nest = 0` rather than delegating the container itself, so the full
  rendering gets exactly one more visible level than `show_payload(p, None)`
  would. Read at `whence/values.py:520`, `646-762`; independently stated by
  `tests/test_v43.py:312-314`.
- D2. `named_misses` mirrors the renderer's bound explicitly (`if nest <
  SHOW_NEST` on both container branches, `SHOW_NEST + 2` as the revisit
  sentinel) and its docstring names `SHOW_NEST` as the thing it deliberately
  does not fix. Read at `whence/values.py:672-748`.
- D3. `Prov` retains `_ins` (its input nodes) and Whence keeps history, so a
  finished program's provenance graph is reachable from the final `Env`
  without instrumenting any hot path. `interp.py:727-748` returns that
  `Env`. So the BUILT-depth census needs no interpreter change at all.
- D4. The corpus is 33 `examples/*.lang`: 18 this program's own and 15 left
  by the Hermes gateway (`state/known-standing-dirty-paths.json` lists
  fifteen `examples/` paths; `state/whence/round-444/field-roster.json` is
  the membership declaration).

## Predictions

- **P1 [MODEL] (the headline number).** Corpus **BUILT** depth, max over all
  33 programs, lands in the band **4–6**, most likely **5**.
- **P2 [MODEL] (the printed number).** Corpus **PRINTED** depth, max over
  all 33 programs, lands in the band **2–4**, most likely **3**.
- **P3 [MODEL] (does it bite today?).** **No** corpus program's `print`
  output is truncated by the nest cap — zero occurrences of a `[…]` or
  `@{…}` produced by the `nest >= SHOW_NEST` branch across all 33 runs.
- **P4 [MODEL] (built exceeds printed).** At least **10** of the 33 programs
  have BUILT depth strictly greater than their own PRINTED depth. Counter:
  one program = one comparison, programs that print nothing excluded from
  the numerator and named.
- **P5 [SENT] (who is deepest).** The single deepest value in the corpus is
  built by a **self-hosting / meta program** — `meta.lang`, `self_eval.lang`
  or `self_host.lang` — not by a demo. Basis is this repo's prose about
  `meta.lang`'s 2.77 M nodes (`values.py:118`), which is a claim about node
  COUNT and not about depth, so this is a weak line and is banked as one.
- **P6 [NONE] (who is deepest, second axis).** The deepest value is built by
  one of the **15 foreign** programs rather than one of this program's own
  18. I have not opened the foreign programs and have no basis; banked so
  the split gets reported either way.
- **P7 [MODEL] (the practical stake).** Raising the full rendering's cap
  from 4 visible levels to 8 changes the printed output of **zero** of the
  33 corpus programs. Counter: byte-comparison of each program's full
  stdout, before vs after.
- **P8 [MODEL] (the shape of the deepest value).** The deepest value's spine
  is **mixed** — at least one `Record` level and at least one `WList` level
  — rather than a homogeneous list-of-lists or record-of-records.
- **P9 [MODEL] (the census needs a budget).** At least one corpus program's
  provenance graph exceeds **1,000,000** distinct `Prov` nodes, so the
  census needs an explicit node budget and must report when it hits one.
  Counter: distinct `id(node)` visited by the census walk.
- **P10 [MODEL] (recursion safety, the escape hatch's own test).** Host
  frames consumed per rendered container level, measured by
  `sys.setrecursionlimit` bisection or by frame counting, is **≤ 4**; so a
  cap of 8 costs at most 32 frames and disposition item 4 does NOT fire.
- **P11 [MODEL] (a value the cap already truncates exists).** At least one
  corpus program builds a value with `D > 4`. Note this is consistent with
  P7 and P3: a value can be BUILT deeper than the renderer's cap and never
  reach `print`. If P11 is TRUE and P3/P7 are also TRUE, that pair is the
  round's actual finding and I am saying so before I know it.
- **P12 [MODEL] (blast radius in `values.py`).** The number of `SHOW_NEST`
  references in `whence/values.py` that have to become cap-parameterised to
  give `full_show` its own constant is **4–6**. Counter: `grep -c SHOW_NEST
  whence/values.py` reports 8 at HEAD (1 definition + 2 comment lines + 5
  live uses, per D1/D2); the band is on the LIVE uses that change.
- **P13 [CMD] (test yield).** The whence tier is `2286 passed, 3 skipped, 98
  deselected` at HEAD (round 451's record, independently reported by the
  driver's own post-round check). After this round: **2298–2316 passed**, 0
  failed. Condition: run SOLO on this 1-core box, nothing else running.
- **P14 [MODEL] (the killers hold).** **Zero** of `tests/test_generated_
  killers.py`'s pinned regressions go red, because the full rendering's text
  changes only for values with `D > 4` and no killer builds one.
- **P15 [NONE] (declined).** I have no basis to predict the number of
  distinct payload objects in the corpus provenance graphs, nor the census's
  peak memory. Both will be REPORTED, neither is a bet.
- **P16 [MODEL] (the cheap wrong answer I am refusing).** The obvious fix —
  just make `full_show` unbounded, since it is already O(n) in elements — is
  wrong, and the census will show why: at least one corpus program builds a
  value deep enough that an unbounded full rendering is a real recursion
  risk, OR none does and the risk is instead that nothing in the corpus
  would ever catch the regression. I predict the **second**: the corpus's
  max built depth is small enough (P1) that an unbounded renderer would pass
  every test in this tree and still be wrong.
