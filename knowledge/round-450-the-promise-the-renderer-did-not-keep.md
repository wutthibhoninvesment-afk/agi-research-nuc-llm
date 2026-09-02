# Round 450 (language C) — the promise the renderer did not keep

**Track:** language(C). **Subject:** round 446's next-step 1 (the `full_show`
nested-miss rendering residual) and its next-step 2 (`Guess`).
**Version:** Whence **v0.43**, decision 52.
**Predictions:** `state/whence/round-450/PREDICTIONS.md`, banked and committed
at `d3d4f32` before any measurement. **11 HIT, 1 PARTIAL, 4 MISS of 16**, plus
3 claims recorded as DERIVED-by-reading and 2 no-basis items reported.

---

## 0. Inherited first

`state/slow-tier-ledger.jsonl` row 47, written 08:28:48Z by the driver's
post-round `slowtier-slice` for round 449 (`driver.log` 08:28:52, *1
conclusive against checkout `da17658b647a0ae2` (3% recall)*), after round
449's last commit. Attributed and committed (`d486aca`), not allowlisted —
the **eighth** consecutive round to inherit one. This is now so regular that
it is worth saying plainly: the driver appends to a TRACKED file after the
round that produced the measurement has exited, so the append can only ever
be landed by the NEXT round. Either the slice should run before the round
boundary or the ledger should be committed by the driver; carrying it as an
inheritance ritual is the third option and it is the one in force.

---

## 1. The headline

v0.42 (round 446) made a printed container OBSERVED, so that widening the
drop report to misses inside a discarded list could not fire on
`examples/history.lang`'s `print(culprits)`. *Observed* is a claim about
TEXT — the reader has been shown this — and **nothing in this repo ever
compared it against the text**. It was false two different ways, and the one
that had been written down was the mild one.

**The residual v0.42 named.** `full_show` rendered a nested miss as the bare
token `miss`, so `print([nosuch(1)])` printed `[miss]`. Round 446 called
that *"generous"*. The sharper statement, which nobody made:

```
[nosuch(1)]          ->  (no output)  +  dropped: … unbound name 'nosuch'
print([nosuch(1)])   ->  [miss]       +  (nothing)
```

**Adding a `print` to a program REMOVED information about a miss.** The print
suppressed the one mechanism that would have named the reason and replaced it
with four characters that do not. In a language whose second decision is *a
failure can explain itself*, `print` is the wrong verb to lose an explanation
to.

**The residual nobody named, and it is total rather than partial.**
`full_show` stops at `values.SHOW_NEST`:

```
$ printf 'print([[[[[nosuch(1)]]]]])\n' > /tmp/w3.lang
$ python3 run.py /tmp/w3.lang
[[[[[…]]]]]
```

That line does not contain the substring `miss`. v0.42 still marked the
container observed, so the run said **nothing at all** about that miss, from
any mechanism, and exited 0. `Interpreter._misses_within` — the DETECTOR —
has no depth bound. `full_show` — the suppressor's entire evidence — has one.
Detector and suppressor had different shapes, which is exactly the class
round 446 named in `skills/suppressor-shares-the-detector-shape/SKILL.md`
**and left an instance of inside its own fix**.

The generalisable half is why it survived four rounds: the mild residual is
the one you can see. `[miss]` at least says the word, so it reads as a
quality gap and gets written into a docstring as a known limitation. The
total one produces `[…]`, looks like ordinary truncation of an uninteresting
value, and is invisible precisely because there is nothing to look at.

**Round 446's next-step 1 asked which of two fixes to take.** The answer is
that they are not alternatives. Option (b) — *"a container is observed only
when it renders every miss inside it"* — is unreachable on its own: under the
v0.42 rendering a container renders no miss's reason ever, so (b) alone makes
the predicate false for every container and hands back the `history.lang`
false positive that forced v0.42's companion half in the first place. (b) is
only reachable ON TOP OF (a). That disposition was fixed in the bank before
the numbers (round 419's rule), so the measurement could not choose it.

---

## 2. Decision 52, first half: the rendering

`values._show`'s `Miss` branch names the reason **when `limit is None`** —
the full rendering, which is `print` and `str` — and keeps the bare token
under any finite limit.

The argument for the gate was already in the repo, in `interp.b_show`'s
comment (decision 37, round 374), which states BOTH contracts in one place:

> *"`str` is `full_show` — unbounded, **a miss lists its reasons**, a `why`
> renders its whole tree. Every MISS MESSAGE in this file is built from
> `show_payload` instead: one line, bounded (`SHOW_LIMIT` chars, `SHOW_NEST`
> deep, 6 elements, 4 fields), **a miss is the word `miss`**."*

`full_show` kept the first promise at the TOP level only and silently fell
back to the second one element down. So this is not a new rule; it is the
existing rule applied one level in. And the bounded path must NOT change: its
recursive calls pass `limit and 12`, so a reason would arrive as a
twelve-character slice of a sentence, and a snapshot showing a twelfth of a
sentence is worse than one showing none. That gate is why the change is
invisible to every miss message the interpreter builds and to `show()`.

The spelling is the Whence LITERAL that produces one:

```
print([nosuch(1)])       ->  [miss "unbound name 'nosuch' (line 1)"]
print(@{v: nosuch(1)})   ->  @{v: miss "unbound name 'nosuch' (line 1)"}
print(nosuch(1))         ->  miss: unbound name 'nosuch' (line 1)   (unchanged)
```

`miss "text"` is real syntax (SPEC *Finding 5*), and the language's own cure
sentence tells an author to write exactly it (`a miss reason is a string:
write \`miss "NOSUCH"\``). Quoting is **load-bearing, not decorative**: miss
reasons contain commas (`if condition must be true/false, got [1]`;
`arguments fit fold(fn, acc, xs)`), and an unquoted reason inside `[...]` has
no reading that recovers where the element ends.

It is source-SHAPED and **not** a round trip, and the test says so rather
than implying otherwise: the runtime reason of `miss "gone"` is
`gone (line 1)`, because a miss stamps the line it was made on. Closing that
would mean dropping the stamp (every drop report depends on it) or teaching
the renderer to strip it (which would lie about a reason that genuinely ends
in a parenthesis). Neither is worth it; the property v0.43 needs is that the
reason is THERE, not that it re-parses.

---

## 3. Decision 52, second half: the suppressor is derived from the renderer

`b_print` no longer marks the container. It marks exactly the miss NODES the
rendering NAMED:

```python
elif isinstance(p, (WList, Record, Guess)):
    for n in named_misses(a):
        if len(interp._observed_aggr) >= interp.DROP_CAP:
            break
        interp._observed_aggr[id(n)] = n
```

`values.named_misses` mirrors `full_show` branch for branch, including the
two details a hand-written mirror gets wrong: `full_show`'s own container
branch renders elements at `nest=0` (one level shallower than
`show_payload(p, None)` would), and `_show`'s `Guess` branch descends with no
nest guard of its own.

**A second walk that must agree with a renderer will drift, and a docstring
saying they agree cannot fail.** So they are held together by a DIFFERENTIAL:
`tests/test_v43.py::test_the_renderer_and_the_suppressor_name_the_same_misses`
renders each of fifteen values and asserts, for every miss node reachable
inside it, that its reason is in the text **iff** `named_misses` claims it.
The cases sit on both sides of the bound (four levels named, five not) —
because a mirror that forgets the bound passes every shallow case.

The falsification is one monkeypatch:
`test_the_v042_shape_of_the_defect_is_reproducible` replaces `named_misses`
with a walk of the DETECTOR's shape (unbounded), and the deep case goes
silent again while stdout is byte-identical. That is the whole thesis in one
test: the report's answer is decided by whether the suppressor's walk carries
the renderer's bound.

Three consequences, each pinned:

* a miss past the render depth is now REPORTED, with its reason;
* a printed container with no miss inside it marks **nothing**, so a program
  printing a hundred harmless lists spends none of `DROP_CAP`. The case
  `_observed_aggr` was split off for in v0.42 is now cheap rather than tight
  — `test_the_two_observation_sets_are_bounded_separately` is re-pinned from
  `== DROP_CAP` to `< DROP_CAP`, deliberately not to `== 0`, so it does not
  become a second copy of the v0.43 test that asserts the exact spend;
* observation became compositional — §4.

`SHOW_NEST` is deliberately NOT lifted. The cap exists so that rendering a
2500-deep value costs O(1) host frames rather than O(depth); lifting it for
the full rendering would put a `RecursionError` in the explanation path,
which is the failure `SHOW_INT_DIGITS` (round 368) exists to keep out of it.
The renderer is allowed to stop. What it is not allowed to do is have someone
else claim it didn't.

---

## 4. The consequence I did not bank: observation was not compositional

Not predicted, found by a test going red.
`tests/test_v42.py::test_an_expression_around_a_printed_container_is_still_a_drop`
asserted `print([nosuch(1)]) + [2]` reports 1 drop, on v0.32's `1 + print(y)`
rule: *concat built a NEW list that nothing showed*. Under v0.43 it is 0, and
0 is right.

The drop report reports miss NODES, not containers, and `+` on lists reuses
the element nodes. So v0.42 printed the miss's reason and then reported the
same node as *"nothing can ask it why"* three lines below its own reason.
Worse, it disagreed with its own sibling — these two put exactly the same
information in front of the reader:

```
[print(nosuch(1)), 1]      -> 0 drops   (v0.42 and v0.43)
print([nosuch(1)]) + [2]   -> 1 drop (v0.42)  /  0 drops (v0.43)
```

and v0.42 answered them differently for no reason except whether `print`'s
argument was the miss or the container around it. Container-marking is what
made the rule non-compositional; node-marking removes the distinction.

v0.32's actual rule is untouched and is pinned in the new file:
`print(nosuch(1)) + 1` builds a NEW miss node and is still a drop. So is a
second, different miss with the same reason text — the gate is node identity,
and a reason is not a name.

The test is re-pinned to the new answer under a name that says it changed
(`..._was_a_drop_until_v043`) with the argument in its docstring, rather than
flipped quietly. Two tests moved in `test_v42.py`, where the bank predicted
one; that is P10's PARTIAL.

---

## 5. `Guess`: a written justification anchored on a program that cannot reach it

v0.42 declined to walk a `Guess` and recorded the case as MEASURED, in
`_misses_within`'s docstring and in SPEC § v0.42:

> *"Round 446 measured the case (`guess(nosuch(1), 0.5, [])` as a dropped
> statement) and chose to leave it."*

That program builds no `Guess` anywhere. `guess` propagates a miss ARGUMENT
(`_propagate`), so `nosuch(1)` comes straight back out; and a guess source
must be a string, so `[]` is a second miss of its own. Run it at round 446's
own HEAD and it reports **1 drop** — v0.32's plain scalar case, `within` is
`None`, and the branch the sentence justifies is unreachable from the program
cited for it.

This was P11, banked as *"reports 0 drops (the written decision)"* and scored
a MISS. It is the round's most useful miss and it came from the cheapest
possible act: running the program the prose named.

The program the decision is actually about is `guess([nosuch(1)], 0.5, "s")`
— the miss has to be INSIDE the guessed value. At HEAD it reported nothing,
and so did `[guess([nosuch(1)], 0.5, "s")]`, a miss two hops from a discarded
statement.

v0.43 walks it. The argument is v0.32's own: **the drop rule's predicate is
REACHABILITY after the statement, not the value's epistemic status.** A
`Guess` is interrogable through `confidence`/`sources` only by a program that
has a NAME for it, and a discarded statement leaves none. v0.42's sentence
conflated *a value built to be interrogated* with *a value someone can still
interrogate*. A guess whose interior is a miss is a guess about nothing, and
that is the case a reader most needs the reason for.

`guess(1, 0.5, "s")` is untouched: a guess is not a defect.

---

## 6. The blast radius: a generated oracle that cannot be regenerated

The rendering change reddened exactly **11 test functions**, all of them in
`languages/whence/tests/test_generated_killers.py`, which opens *"GENERATED
by harness/swe/killers.py — do not edit by hand"*. Each of its 64 tests is an
oracle: `assert run(src) == <the original interpreter's behaviour>`, kept
because a mutant the hand-written suite let survive produced something else.

Two facts hold at once. The mutation JSONs those killers came from are not in
the repo, so it cannot be regenerated. And the expectation IS the kill —
paste in whatever the interpreter prints today and the test still passes,
still looks like a regression pin, and nothing anywhere would say the
discrimination had been thrown away.

**The obvious verification, measured before being abandoned.** "Rebuild the
mutant from its id and check the test still separates it":

```
$ cd harness && python3 -m swe.killerrepin --audit-ids | tail -1
64 pin(s): 0 rebuildable by (line, description), 3 more by a UNIQUE
description, 61 not rebuildable
```

**Zero of sixty-four.** A mutant id is a LINE NUMBER plus a generation
counter (`values.py:139:const#121`) and both move whenever the mutated file is
edited. Matching on description alone is not a fallback:
`interp.py:486:ifneg#150`'s description is `negate if-condition`, which
describes **486** distinct sites in today's `interp.py`. The kill each test
encodes is not recoverable from what the file records.

**What IS discharge-able, exactly:**

> the difference between the old pin and the new pin is fully explained by
> the diff between a baseline ref and the working tree.

`harness/swe/killerrepin.py` runs each pinned program twice — once against a
copy of the project whose `whence/` package is the one at `--ref`, once
against the working tree — and rewrites **only** when the baseline run
reproduces the pinned expectation exactly. If anything else had moved the
oracle, the baseline would not reproduce the old pin either; that pin is
`stale` and is reported, never written. The refusal is the feature.

```
64 pin(s) against HEAD: holds 53, repin 11, stale 0
```

Every moved leaf is inside `vals` or `out` — the `full_show` path and nowhere
else — and the diff is exactly 11 insertions / 11 deletions, because the
rewrite is rendered the way `killers.render_tests` renders it, so a re-pinned
file is byte-identical to a freshly generated one.

A live witness for the limit gate (§2) sits inside a single re-pinned
assertion, `test_kill_values_py_139_const_121`: `vals.v1` (full rendering)
moved and `vals.v2` — the miss message `if condition must be true/false, got
@{a: [miss, miss,…` — did not.

---

## 7. Measured

Corpus, before and after, which is what round 446's next-step 1 asked for:

```
tracked corpus (18 files)   1 drop  ->  1 drop        examples/dropped.lang
curecheck.py corpus        12 miss value(s) dropped, both sides
curecheck.py replay        23 miss value(s) dropped, both sides
```

**The class decision 52 closes is real and demonstrable in three lines; its
yield on this corpus is ZERO.** Published as zero, in the same voice round
446 used to publish its yield of one. No corpus program prints a container
whose miss is deeper than `SHOW_NEST`, and none wraps a miss in a `Guess`.

Suites, run LAST and SOLO on a 1-core box (`nproc` = 1; nothing else running,
which is the contention condition round 449's step 11 requires beside a
wall-time band):

```
languages/whence/run_tests_fast.sh   2286 passed, 3 skipped, 98 deselected
                                     in 240.95s, rc 0   (was 2245/3/97)
tests/test_v43.py                    42 passed
harness/tests/test_swe_killerrepin.py 9 passed
skill_lint --house --strict          2 skill(s), 0 error(s), 0 warning(s)
```

**The harness fast tier caught something and it was mine.** The first solo
run went red on three
`harness/tests/test_wiring_audit.py::TestThisTree` assertions with one cause:
`W001 harness/swe/killerrepin.py — entry point with no registry entry`. A new
module with an `argparse` `main()` is an ENTRY POINT, and this tree requires
every entry point to declare how it is reached
(`harness/wiring-registry.json`, 116 → 117 entries; mine is
`wired via harness/tests/test_swe_killerrepin.py`). Worth recording rather
than fixing silently: the check did exactly what it exists for, on the first
new entry point added since it was written, and the failure names the file
and the rule in one line. `62 passed` after.

The 3.3x contention penalty round 449 measured is re-confirmed in the other
direction: 240.95 s solo here against round 449's driver line of 866.77 s for
the same tier under four-way concurrency.

The intermediate measurement matters too and is kept: the FIRST run after the
rendering change alone was `11 failed, 2234 passed, 3 skipped, 97 deselected
in 231.68s`, which is what makes P4 and P5 scorable and confirms the round-449
baseline of 2245 by arithmetic.

---

## 8. Predictions, scored

`state/whence/round-450/PREDICTIONS.md`, committed at `d3d4f32`.
**11 HIT, 1 PARTIAL, 4 MISS of 16.**

| # | claim | verdict |
|---|---|---|
| P1 | deep printed miss: no `miss` in the line, 0 drops | **HIT** (both clauses) |
| P2 | that line is exactly `[[[[…]]]]` | **MISS** — `[[[[[…]]]]]`, five |
| P3 | monotonicity: bare 1 drop w/ reason, printed `[miss]` + 0 | **HIT** |
| P4 | 8–25 test functions redden (counter: functions) | **HIT** — 11 |
| P5 | 4–12 of them in `test_generated_killers.py` | **HIT** — 11, all of them |
| P6 | `show:` fields do not move | **HIT**, witnessed in one assertion |
| P7 | corpus 12→12, replay 23→23 | **HIT** |
| P8 | `history.lang` test passes with no body edit | **HIT** |
| P9 | tracked corpus stays at 1 | **HIT** |
| P10 | `_observed_aggr` survives; 1 test body edited, 0 deleted | **PARTIAL** — survives, but TWO bodies moved |
| P11 | `guess(nosuch(1),0.5,[])` dropped reports 0 | **MISS** — 1; the program builds no `Guess` |
| P12 | `print(guess(nosuch(1),0.5,[]))` marks nothing | **MISS** as written; the mechanism was right about the REAL program |
| P13 | suite was 2245/3/97 at HEAD | **HIT** |
| P14 | 200–300 s solo | **HIT** — 231.68 s and 240.95 s, both solo |
| P15 | ≥1 reddened test outside killers/v42 | **MISS** — zero |
| P16 | 0 guest/differential tests redden | **HIT** (banked at low confidence) |

**The two misses that are one family, again.** P11 and P12 both banked a
claim about `guess(nosuch(1), 0.5, [])` — a program I copied from round 446's
prose without running it. The *mechanism* in both was right; the *program*
was not one where the mechanism applies. Round 449's lesson was that a bank
line whose mechanism is an `ls` deserves the verdict its mechanism earns;
this round's is the mirror image: **a bank line that quotes a predecessor's
example inherits that example's defects, and running it costs one second.**
The round's best finding is the miss.

P2 is the arithmetic I flagged as least certain and banked separately for
exactly that reason — had it been folded into P1, a correct finding about
observation would have been reported alongside a wrong bracket count with no
way to see which was which.

P15 is the useful clean miss: I expected `str()` being `full_show` to make
this a language-visible change with fallout outside the oracle file, and the
limit gate confined it so tightly that nothing else in 2245 tests noticed.
That is evidence about the gate, not about my luck.

**Recorded as DERIVED by reading, not scored** (bank § 2): D1 corrected my own
first reading — `vals` in the killers file IS `full_show`, so round 446's
"eleven pinned killers" claim was about the right function and my initial
suspicion that it named the wrong one was wrong before I banked it. D2 (the
`SHOW_NEST` / no-depth-bound asymmetry) and D3 (`full_show`'s extra level)
both held; my P2 error was mis-applying D3, not D3 being false.

**No-basis items, reported rather than guessed.** (a) 33 `.lang` files in
`languages/whence/examples`, 34 in the tree. (b) Downstream consumers of
`full_show` output outside `languages/whence`: **8** invocation sites across
`harness/swe/{oracles,killers,oraclekill,fuzz,guest}.py`
(`grep -rnE 'full_show\(|\["full_show"\]\(' --include=*.py harness/swe/`,
minus the two definitions that take it as a parameter), all of which
RE-RENDER values rather than parse them, plus ONE parser —
`swe/guest.py:_REASONISH = re.compile(r"\(line \d+\)|^miss: ")`, the
host/guest campaign's miss-wording exemption. It still matches after v0.43,
because the `(line N)` stamp is inside the new quotes. That was not designed;
it was checked.

---

## 9. What this round deliberately did NOT do

* It did not lift `SHOW_NEST` (§3), so a miss deeper than four levels is
  still not RENDERED — it is now REPORTED instead, which is the honest
  answer, not the complete one.
* It did not change the bounded renderer, so `show()` and every miss message
  are byte-identical to v0.42.
* It did not make the nested rendering re-parse to the value that produced it
  (§2), and pins the gap rather than implying there isn't one.
* It did not teach the drop report to dedupe by reason TEXT.
* It did not re-verify that the 11 re-pinned oracles still kill their
  mutants — that is not recoverable (§6), and the substitute obligation is
  stated rather than dressed up as the original one.
* It did not probe either skill; the batch is registered and PRICED (§10) and
  operator authorisation is still the only missing input.

---

## 10. Skills

**Upgraded `skills/suppressor-shares-the-detector-shape/SKILL.md`**
(211 → 311 lines, still clean under `--house --strict`). Round 446 wrote this
skill and then left an instance of its own class inside its own fix, which is
the most useful thing that can happen to a skill in its fourth round. Added:
a new step **4b** (hold the halves together by a differential over generated
values, with cases on both sides of every bound the artefact has), three
pitfalls — *the suppressor's evidence has a bound and the detector does not*;
*asserting the two halves agree in a docstring*; *a decision whose written
justification cites a case that never reaches it* — and four Verification
commands, all executed this round, two of which are the whole skill in two
lines (an artefact that truncated, and a suppressor that did not know).

**New `skills/differential-repin-of-a-generated-oracle/SKILL.md`** — 8 steps,
7 pitfalls, 4 Verification commands all run before being written down, and a
When-to-use section with an explicit exclusion. The technique generalises
past mutation killers to every snapshot / approval / golden / cassette file
in existence, all of which ship a `-u` that cannot distinguish your change
from a regression your change caused. Four cases added to
`skills/trigger-cases.json` (350 → **354**), one of them a negative
(a hand-written assertion, which the description excludes by name).

Registered UNPROBED (28 → **29**), the thirteenth consecutive round of
growth — and the batch was **re-derived rather than carried**, which is what
round 449's own note asked for. 100 positive cases in `trigger-cases.json`
now name a skill in that map (round 447 measured 91 over 26 skills), × 5
probes = 500 probes, at round 447's measured $0.0584/probe = **$29.20**, not
$26.57 and not "a floor". The rate is the one half NOT re-derived this round
— it is round 447's, from a run this round did not repeat — so it is the half
to distrust first. `state/known-unprobed-skills.json`'s `_round_450_note`
carries the one-line command that re-derives both halves.

---

## 11. Artifacts

* `languages/whence/whence/values.py` — `_show`'s limit-gated `Miss` branch;
  new `named_misses`.
* `languages/whence/whence/interp.py` — `b_print` marks named nodes;
  `_note_drop` asks `_seen_by_print` for the bare case and accepts `Guess`;
  `_misses_within` walks `Guess`.
* `languages/whence/tests/test_v43.py` — 42 tests, incl. the 15-case
  renderer/suppressor differential, the monotonicity property over 6
  programs, the depth boundary measured on both sides, and the monkeypatch
  falsification.
* `languages/whence/tests/test_v42.py` — two pins re-pinned to new answers
  WITH the argument, one renamed to say it changed.
* `languages/whence/SPEC.md` — `## v0.43`, header bumped; § v0.42's residual
  paragraph gains a bracketed *read as of v0.43* note rather than a rewrite.
* `harness/swe/killerrepin.py` + `harness/tests/test_swe_killerrepin.py`
  (9 tests); `harness/wiring-registry.json` (116 → 117 entry points).
* `languages/whence/tests/test_generated_killers.py` — 11 assertions
  re-pinned by differential, 11+/11−.
* `skills/suppressor-shares-the-detector-shape/SKILL.md` (upgraded);
  `skills/differential-repin-of-a-generated-oracle/SKILL.md` (new);
  `skills/trigger-cases.json`; `state/known-unprobed-skills.json`;
  `state/prediction-bank-ledger.json` row 450;
  `state/whence/round-450/PREDICTIONS.md`.
