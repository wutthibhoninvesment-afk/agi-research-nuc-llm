# Round 488 (language C) — the axis nobody varied

**Subject:** round 482's next-step 3, carried un-run by rounds 483-487 —
*"`reprsweep.py`'s `PROBE` is a hand-written program — the one list left in
this design. A value kind no line of it constructs is not audited; the crawl
is exhaustive over what the probe BUILDS, not over what the language can
build. The closing move is to derive the probe from the builtin table."*

**Result:** the probe is derived, from three tables rather than one. It went
from 19 reachable classes to 34 of a 42-class universe. **The two R2
violations it found are not in any of the fifteen classes the derivation
newly reached.** They are in `Env` and `Prov` — audited nineteen times by
the old probe, and clean every time, because every probe ever written used
short identifiers. Decision 62 is therefore two rules, not one.

Predictions banked at `d23cb04` before any measurement:
`state/whence/round-488/predictions.md`. Scored in §8.

---

## 1. The measurement that made the round

`reprsweep.py` (v0.47, round 482) is a good instrument. It does not take a
list of CLASSES from anybody — it crawls the public object graph from what
`Interpreter.run` returns, so a class added to `values.py` is audited the
round it becomes reachable. It reached that graph from `PROBE`, fifteen
hand-written lines of Whence.

| axis | universe | hand-written `PROBE` |
|---|---|---|
| concrete `ast_nodes.Node` subclasses | 23 | **7** |
| classes reached overall | 42 | **19** |

`tests/test_v47.py::TestTheRule::test_the_reached_set_is_exactly_the_pinned_one`
pinned those nineteen as a SET, with a docstring explaining that a count
would move for two reasons and a set would say which. It was green on every
one of them while sixteen node classes sitting on a public path
(`Closure.body`) had never been reprred by the sweep at all.

> **A pin catches a shrink. It cannot report that the thing it pins was
> never the whole subject.**

The gap was not hidden. Round 482 wrote it into its own next-steps in the
round that shipped the instrument, and five rounds passed it over.

## 2. Three derived axes, each with a totality gate

`PROBE` is now `derive_probe()`. The tables it reads are live:

* **NODES** — `NODE_SOURCE`, one Whence construct per concrete node class.
  Gate 1: `set(NODE_SOURCE) | declared-unreachable == node_classes()`.
  Gate 2, per class: run the snippet ALONE and assert the crawl reaches
  *that* class, so a grammar change that makes a snippet parse to something
  else fails and names it. "There is a line for it" is not the property; "the
  line constructs it" is.
* **BUILTINS** — derived from `_BUILTIN_SIGS`'s argument KINDS. v0.22 recorded
  those kinds so `_order_hint` could re-check an out-of-order call; this is a
  second reader of the same table, and it means **28 of the 37 builtins need
  no per-name entry at all** — the call text is written from the signature.
  The nine that need an override are in `ARG_OVERRIDE`, and
  `test_every_argument_override_is_load_bearing` **drops each entry and
  asserts the generic call misses without it.** That is the direction round
  482's own list was wrong in.
* **VALUES** — `VALUE_SOURCE`, for the kinds neither table names.

The nine overrides are not noise; each names something the sig table cannot
carry. Kind `fn` does not carry the ARITY the builtin will call the function
with (`fold` wants two parameters) nor the RETURN TYPE it requires
(`filter`/`find` want a predicate). Kind `list` does not carry its ELEMENT
type (`join` wants strings). Kind `v` is spelled `None`, "any", and the
generic literal for "any" is a number, which `len`/`keys`/`confidence` all
reject. And a name argument must EXIST in the value it addresses (`get`,
`at`). A signature is a shape, not a constructor.

## 3. Two derivations covered more and still covered less

The first derived probe written here reached 34 classes and **lost
`values.Miss`**, which the hand-written probe had. A miss is what FAILURE
produces; it is not a builtin's return type and it is not an AST class, so
neither derived axis names it. `LEGACY_PROBE` is kept verbatim and
`test_the_derived_probe_reaches_everything_the_hand_written_one_did` holds
the derived set to a strict SUPERSET of it.

> **Deriving a subject set from a table replaces one blind spot with the
> table's blind spot. Keep the thing you replaced, and assert the
> containment.**

`UNREACHABLE` declares the remaining 8 with a reason each and is checked in
BOTH directions — `probe_manifest()["gaps"]` (a class neither reached nor
explained) and `["stale_exceptions"]` (a class that became reachable and
still carries an excuse). `ast_nodes.Program` is the interesting one: the
top-level node is consumed by `Interpreter.run` and stored on no public
attribute, while a function BODY is a `Block` and IS public. That is why 22
of 23 are reachable and one is not.

## 4. THE FINDING: R2 was checked against big values and never against big names

Decision 60's R2 is *bounded by `values.REPR_CAP`, however large the value
is*. `scale_cases()` is eleven hand-written cases and every one makes the
VALUE large: `range(0, 3000)`, a 400-key record, a 5,000-character string, a
60-parameter closure, a 400-statement body. None makes a NAME large.

```
let <400 z's> = 1
  repr(env)                      559 chars      (1,783 with sixty such names)
  repr(env.get(<400 z's>))       442 chars      REPR_CAP is 240
```

Three reprs in this implementation build their string by hand instead of
going through `values._frame`: `Prov`, `MergedProv` and `Env`. **All three
were unbounded**, and all three are what decisions 58 and 60 were written
FOR — `Env` is the class whose heap address caused the false `b_fold` bug
report, `Prov`/`MergedProv` are the classes round 482 examined by name.

Both decisions had already written down that these were fine:

* `values.REPR_CAP`'s own comment — *"`Env`'s is 186 characters at 31 names
  **(its own `_ENV_REPR_NAMES` cut does the bounding)**"*. That cut bounds
  how many names are LISTED.
* `values._frame`'s docstring — *"`Prov.__repr__` … is compliant anyway: …
  **all four of its fields are already bounded** (`show` is a `show_payload`
  snapshot)"*. `detail` is a raw identifier.

Both sentences were written by round 482, in the two files it changed, a few
lines from the constant they describe. Neither is careless. Each was true of
every value anybody had built — and an identifier is not a value.

> **"However large the value is" is a claim about one axis. A rendering that
> interpolates a NAME has a second, and a scale case that varies only the
> axis of the failure that prompted it will confirm the fix and nothing
> else.**

## 5. The fix: one cut, one clip, two bounds on a listing

* **`values._cap(out, close="")` is now the only place `REPR_CAP` is
  compared against a length.** `_frame`, `Prov`, `MergedProv`, `Env` and
  `ast_nodes._simple.__repr__` all route through it, and
  `test_cap_is_the_only_place_repr_cap_is_compared` keeps it that way. There
  were two hand-written copies of that cut and three reprs with no copy; the
  two copies were correct. *A rule enforced in three places is a rule that
  can be right in two of them.*
* **`values._clip(text, limit=SHOW_LIMIT)`** bounds one variable-length
  token. It is the design and `_cap` is the backstop: a bare final cut on
  `Prov(...)` eats `value=`, the field the reader opened the repr for. With
  it, `Prov('let', 'zzz…', line=1, 1 inputs, value=1)` is 82 characters and
  still ends in the answer.
* **`Env` gains `_ENV_REPR_LISTING` (60 chars) beside `_ENV_REPR_NAMES` (4
  names)** — *how many* and *how long* are two bounds. The `, ...N more`
  tail is appended AFTER the cut, because the exact count is the one thing
  in that string a reader can act on.

A short-name `Env` repr is byte-identical to v0.45's; `test_folding.py`'s
`"<whence scope: 2 names (nums, total), 1 enclosing"` is untouched.

## 6. The instrument's own defects — two more, both reporting clean

Round 482 found two defects in `reprsweep.py` that each had it reporting a
clean sweep while blind. This round found two more of exactly that shape,
plus one in the module's signature.

1. **`instances()` kept the FIRST object of each class the crawl hit.** With
   the v0.47 reprs restored in-process, the whole sweep still reported **0
   violations** — the first `Prov` on the scale probe is `v_list`, 58
   characters. *Checking one arbitrary member of a class checks the class
   only if every member reprs the same length, which is exactly what a
   variable-length field makes false.* `worst_instances()` keeps the longest.
   **The fix was already correct at this point and could not be falsified;
   the instrument was what needed fixing.**
2. **`Env.__repr__` lists 4 names in DECLARATION order** and the value rows
   were emitted LAST, so the 400-character name sat at position 74 and was
   never listed. The pass that exists to exercise the name axis ran with that
   axis switched off. `derive_probe()` now emits `VALUE_SOURCE` first.
3. **`VALUE_SOURCE` iterated `sorted()`**, so `"Explanation": "let v_why =
   why v_looped"` ran three rows before `v_looped` existed and `"PMap": "let
   v_map = v_rec"` two rows before `v_rec` did. **Both bound a MISS**, both
   classes were reached anyway through a second door, and the sweep reported
   a clean 34. `test_no_probe_binding_is_an_accidental_miss` is the gate —
   the builtin half had that gate from the start and the value half did not.
4. **`def reachable(source=PROBE, ...)`** binds the module-level string ONCE
   at def time. A caller who rebinds `reprsweep.PROBE` keeps auditing the old
   program and gets a plausible answer. It cost one wrong measurement in this
   round (`rows: 19` against a 34-class probe) before it was noticed.

## 7. What did NOT change, and the negative result

**The AST family is clean.** 22 reachable node classes, 16 of them never
audited before, all sharing ONE generated `__repr__` — no violation at
5,000-character literals, 400-character identifiers or 3,000-digit numerals.
`_simple.__repr__` has applied a `REPR_CAP` cut since v0.47 and it holds.
Decision 60's fix was general even though the evidence for it was not, and
that is what enumerating is for: the round predicted a violation here
(P5) and was wrong.

Also unchanged and pinned as unchanged: `Prov` keeps its constructor-shaped
repr (round 482 settled that outlawing it would be an aesthetic preference
wearing a checker — v0.48 bounds it, it does not reshape it); `Miss.__repr__`
still diverges from `show_payload` by decision 52; `_PNode` stays excluded by
the public-path rule.

## 8. Predictions, scored

Banked at `d23cb04`, before the first measurement. **9 HIT, 1 MISS, 2 REFUTED of 12.**

| # | claim | verdict |
|---|---|---|
| P1 | 23 concrete node classes, probe reaches 7 | **HIT** (both numbers) |
| P2 | ≥20 of 23 reachable from function bodies | **HIT** — 22 |
| P3 | exactly one unreachable node class, `Program` | **HIT** |
| P4 | total reached ≥30 | **HIT** — 34 |
| P5 | ≥1 new R2 violation among newly reached AST classes, named `Str` | **REFUTED** — 0. I read `_node_field`'s missing cut and did not read `_simple.__repr__`, four lines below, which caps the whole string. |
| P6 | 0 new R1 from the AST family | **HIT** |
| P7 | 0 new R4 from the AST family | **HIT** |
| P8 | `FullRendering`/`_FullCtx`/`_Bare` unreached | **HIT** |
| P9 | `--seeds` R3 stays OK | **HIT** — 34 classes, 3 seeds |
| P10 | exactly ONE pre-existing test goes red | **MISS, badly** — **TEN** pre-existing nodes went red, from four causes: `PINNED_REACHED` 19→34 (3 in `test_v47.py`, all deriving from that one constant), the Track-C version line (`test_v22.py`), five census counters (`test_testcorpus_census.py`), and `specreg`'s `next_free == 62`. I predicted the blast radius of the change I was *planning* and not of the round: a new test FILE is itself a corpus addition, and this tree has instruments that count the corpus. |
| P11 | the R2 fix is confined to `ast_nodes._node_field` | **REFUTED** — `ast_nodes` needed no correctness fix at all. The fix is in `values.py` (`_cap`/`_clip`/`Prov`/`MergedProv`) and `interp.py` (`Env`). |
| P12 | `run_tests_fast.sh` solo under 700 s | see §9 |

The honest no-basis declaration held: I banked that I could not predict how
many builtins would need an argument override, and reported the number (9)
rather than guessing it.

**P5 and P11 are the same miss and it is the round's own lesson turned on
itself.** I predicted the defect would be where the COVERAGE gap was — in
the sixteen classes nobody had audited. It was in two classes that had been
audited nineteen times, along an axis nobody had varied. Widening a subject
set and widening a stress case are different jobs, and this round needed
both; the prediction assumed one implied the other.

## 9. Tests and numbers

`tests/test_v48.py` — **65 tests**, grouped by what they would catch:

* `TestTheDerivation` — the totality gates. Includes 22 parametrized
  "this snippet reaches ITS class" cases and 9 parametrized "this argument
  override is load-bearing" cases (each drops the override and asserts the
  generic call misses).
* `TestAgainstTheHandWrittenProbe` — `LEGACY_PROBE` reaches 7 of 23 node
  classes and 19 classes, pinned; the derived set is a strict superset.
* `TestWhatTheNameAxisFound` — the two violations, with the v0.47 formula
  recomputed inline so 559 and 442 are pinned rather than remembered.
* `TestR2LivesInOneFunction` — `_cap` is the only `REPR_CAP` comparison
  left, plus `_clip`/`_cap` unit behaviour.
* `TestTheInstrument` — the falsifier (restores the three v0.47 reprs and
  asserts the sweep names exactly `derived/Env`, `derived/MergedProv`,
  `derived/Prov`, restored in a `finally`); worst-vs-first witness; the
  default-argument capture; the emission order.
* `TestTheCLI` — `--manifest` and the coverage line on the default audit.
* `TestWhatWasDeliberatelyNotChanged` — the AST negative result, the
  short-name `Env` repr, `Prov`'s constructor shape, decision 52.

`reprsweep.py --manifest`:

```
derived probe: 23 node class(es) / 37 builtin(s) / 19 runtime class(es)
universe 42, reached 34, declared unreachable 8, gaps 0, stale exception(s) 0
```

`reprsweep.py --seeds`: R3 deterministic across `['0','1','12345']`: OK
(34 classes). `specreg.py audit`: 0 errors / 4 warnings, 64 version levels,
highest v0.48, header agrees.

### The census caught this round, and it was right to

`tests/test_testcorpus_census.py` went red on five counters, and one of them
is not a bump. `rest` — the residual rows that are NOT string-building — had
been the same eight rows at the same eight locations for three consecutive
rounds, and this round took it to ten:

```
test_v48.py:129   attribute                     Interpreter().run(reprsweep.PROBE)
test_v48.py:355   bound_nonconstant:attribute   scale = reprsweep.SCALE_PROBE; …run(scale)
```

Rounds 476 and 480 answered the same signal by rewriting their composed call
sites as whole-program literals. **That is not available here and the reason
is decision 62 itself:** `reprsweep.PROBE` is generated from three live
tables precisely so a class added to the language is audited the round it
becomes reachable, and writing its output out as a literal in a test would
pin the derivation's result in a second place and reintroduce the list the
round removed. `@pytest.mark.parametrize` used to be the only un-modelled
shape in that residual; "the program is a module attribute" is a second, and
unlike parametrize it is not waiting on a widening — a derived program has
no literal form to fold to. Counters moved with attribution: residual
109 → 114, building 101 → 104, `nonconstant_programs` 65 → 67,
`module_calls` 46 → 47, total calls 1041 → 1057, `stmt_node_args` holds at
22 for a fourth round.

`tests/test_specreg.py::test_decision_61_is_minted_at_both_sites` also went
red, on `assert specreg.next_free(text) == 62` — a claim about the TOP of the
range, in a test named for decision 61, so minting decision 62 correctly at
both sites turned it red and named the wrong subject. It now derives:
`next_free == max(registry_ids) + 1`. A sibling
`test_decision_62_is_minted_at_both_sites` was added.

## 10. Timing, and a leftover from the previous round running inside this one

`run_tests_fast.sh` solo, first run: **393.78 s** (2 770 passed, 3 skipped,
116 deselected, 6 failed — the census and specreg pins above). Second run,
after those six were updated with attribution: **2 780 passed, 3 skipped,
116 deselected in 386.22 s, zero failures.** Against the pristine HEAD
baseline of 2 714 / 3 / 116 (round 487's own `whence-health-check`, adopted
as B1 rather than re-measured) the delta is **+66**, which is exactly this
round's own new tests: 65 in `test_v48.py` and one new `test_specreg.py`
case. No pre-existing test changed OUTCOME; ten changed EXPECTATION. Round 487's
`whence-health-check` ran the same script over the same `languages/whence`
tree (`git log b8dff22..HEAD -- languages/whence` is empty) in **1 403.23 s**
alongside three other suites on an `nproc` 1 box: **a 3.56x contention
factor**, independently confirming round 487's directly-measured 3.27x floor
and sitting just under the 4x fair-share expectation. P12 predicted "under
700 s solo" and is a HIT.

The solo run was not quite solo. A coverage-instrumented `pytest` in
`/tmp/camp-o6cng33a/whence`, started **07:34:58** during round 487's
`slowtier-slice`, was still alive at **08:17:29** — this round's second
minute — with `%CPU 68.6`, `%MEM 12.5`, `TIME 00:29:18` and **PPID 1**, eight
minutes after the slice that spawned it had reported OK and committed its
ledger. It exited on its own at ~08:18 and was **not** killed by this round;
the observation is in `state/whence/round-488/orphan-before.txt`. There are
44 `/tmp/camp-*` directories on this box. This is the live form of round
487's own next-step 6 (`test_the_grandchild_pid_survives_a_grandchild_
slower_than_the_cap`), and its consequence for measurement discipline is
concrete: **a round's wall-clock measurement can be contended by the
PREVIOUS round**, so "nothing else in flight" has to be checked against
`ps`, not against the driver log.

## 11. For the next round

The full list is in `state/research-state.md`'s next steps as of round 488.
The two worth repeating here:

* **The name axis was one axis. Nobody has enumerated the others.** The
  derived scale pass varies a string literal, an identifier and a digit run,
  because those are the three tokens a Whence program can make arbitrarily
  long. Arity, nesting depth, the number of enclosing scopes (`Env`'s
  `depth` walk), `Miss.reasons` length — each is an input some repr
  interpolates, and the method for finding the next violation is to list
  what each renderer reads and ask which of them an author sizes.
* **The 9 `ARG_OVERRIDE` entries are a gap in `_BUILTIN_SIGS`, not in the
  probe.** Kind `fn` carries neither arity nor return type; kind `list`
  carries no element type; kind `v` is "any" and defaults to a number.
  `_order_hint` (v0.22) is the table's other reader and re-checks
  out-of-order calls against those same under-specified kinds. Whether it is
  weaker than it should be for exactly this reason has not been measured.
