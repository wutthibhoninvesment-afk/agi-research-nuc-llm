# Round 456 (language C) — the values nothing kept

**Subject.** Round 452's `depthcensus.py` named, in its own docstring, a class
of values it could not reach and could not size:

> a value that is neither bound, nor a discarded statement's value, nor
> printed, nor an input to any of those. … `--roots env` vs the default
> measures the size of the class that the naive set misses; **nothing here
> measures the residual class**.

Whence v0.44's rendering cap (`FULL_SHOW_NEST = 24`, decision 53) was set
against that instrument's number: *"24 leaves ten levels of headroom over the
deepest value any example builds."*

**Result.** The deepest value any example builds is **1201**, not 14 — 48x
past the cap, in `examples/self_eval.lang`. The corpus constructs **7 418 398**
values and the root-set census reaches **3 587 551** of them, 48%. And the
width bound decision 53 called *"a safety valve, not a limit anyone reaches"*
is reached **2813 times** in that one program. Both champion values are
**provenance-as-data** — the language's own feature — and neither is
reachable from any root the old census had.

No constant changed. **Decision 54** rewrites the justification, and the two
false sentences in decision 53 are corrected in place rather than left to be
re-quoted.

Instrument: the allocation census inside `languages/whence/depthcensus.py`
(+319 lines), 21 new tests in `tests/test_depthcensus.py`, artefacts in
`state/whence/round-456/`.

---

## 0. Housekeeping first (the standing cross-track convention)

`check_round_recorded` reported one uncommitted unattributed path,
`state/slow-tier-ledger.jsonl`. Inspected before landing: one appended row,
`test_swe_exemptmap.py`, `passed`, 114.1 s, `finished_at` 1788358212.64 =
**2026-09-02 14:10:12 UTC** — after round 455's last commit (466f3b5) and 82
seconds before this round's process started (14:11:34 UTC). Its
`checkout_digest` (`6a525eab44f60c1c`) matches the three preceding rows. A
driver-written ledger append, committed as part 0.

**This is the FIFTH consecutive round to land this exact file for its
predecessor** (451→450, 452→451, 453→452, 454→453, 455→454, 456→455 — six in
a row counting the whole chain, five of them this file). Round 452 already
wrote the diagnosis: the append is *deterministic*, not a race — the driver
always appends after the round's last commit, so it is a step in the wrong
order, not a flake. Nothing has acted on that yet.

`languages/whence/SECURITY.md` is untouched: escalated, not this program's,
and the operator's. The checker's own line is the only source for its carry
count. `state/round_counter` is allowlisted standing-dirty.

---

## 1. What the old census could and could not see

`depthcensus.py` walks provenance edges (`node._ins`) and structure edges from
three roots: the top-level `Env`, every value handed to
`Interpreter._note_drop`, every payload handed to `full_show`. That reaches a
great deal — an intermediate sub-expression is an *input* and is reached, so
`let a = [[[…]]]` followed by `len(a)` is fully visible.

What it cannot reach is a value **nothing consumes**. A `let` inside a
function body binds into a child `Env` that dies with the call; if nothing
reads the name, the value is not a top-level binding, not a discarded
statement value, not printed, and not an input to anything that survives.
Pinned as a matched pair:

```python
# tests/test_depthcensus.py
def test_a_value_no_root_reaches_is_invisible_to_the_root_walk_and_seen_here()
    fn deep() { let a = [[[[[[[1]]]]]]]   0 }      built 0   alloc 7
def test_a_returned_value_is_reached_by_both_censuses()
    fn deep() { let a = [[[[[[[1]]]]]]]   a }      built 7   alloc 7
```

The first program's root walk reports depth **0** for a program that builds a
7-deep list. That is not a bug in round 452's instrument; it is what a root
set means.

## 2. The instrument: measure at construction, so there is no root set

`Prov` and `MergedProv` are replaced, for the duration of one census run, by
subclasses that compute depth `D` and tree-unfolding size `N` in the
constructor and keep the champion of each. Every value that ever existed is
counted; there is no root set and therefore no residual.

```python
class _CountingProv(base):
    __slots__ = ("_d", "_n")
    def __init__(self, op, detail, line, ins=(), show=lazy, value=None):
        self.op = op; self.detail = detail; self.line = line
        self._ins = ins; self._show = show; self.value = value
        _TRACKER.measure(self)
```

Four things that had to be right, and are pinned:

**The constructor is inlined, not delegated.** `values.Prov`'s own comment
measures it at 187 ns and 2.77 M nodes for one `meta.lang` run. A second host
frame per node is the difference between an instrument and an outage.

**`Value` is deliberately NOT repointed.** `whence/timetravel.py` does
`isinstance(v, Prov)` against the name it imported. Rebinding an isinstance
TARGET to a subclass makes every node built *before* the patch fail a check it
used to pass. `_install_counting` patches the two constructor names in
`values` and `interp` and nothing else —
`test_value_is_deliberately_not_repointed` pins it, because "patch every
alias" is the obvious edit and is silently wrong.

**It is not O(n²), and the reason is a language design decision.**
`values.WList` is a length-bounded view over an append-only shared buffer, so
a list grown by `push` produces n views over ONE buffer. Recomputing `max`
over each view's elements would be quadratic in the length of every list any
program builds. The tracker keeps **per-buffer prefix aggregates** — valid
precisely because the buffer is append-only — and holds a reference to each
buffer, because an `id` is only a valid key while its object lives. A node
whose payload is *identical by `is`* to an input's payload (the
`Prov("call", …, result, …, result.value)` re-wrap, which is most nodes)
copies its `D`/`N` in O(1).

**Both numbers are re-derived by walks that share no code with it.** After
each run the champions are re-measured with `depth_of` (round 452's) and a new
`_payload_size`, and the census reports `alloc_agrees`. Over the whole corpus:
**no disagreement, and no invariant violation** (`alloc_depth >= built_depth`
everywhere).

## 3. The number

`cd languages/whence && python3 depthcensus.py --json state/whence/round-456/alloc-census.json`
— 3 m 09.9 s wall, solo, `nproc` 1.

| | root walk | allocation |
|---|---|---|
| max depth, whole corpus | **14** (`self_host.lang`) | **1201** (`self_eval.lang`) |
| nodes | 3 587 551 | **7 418 398** (2.07x) |
| programs whose deepest built value the roots miss | — | **6 of 23** |
| largest gap | — | **1191** levels |

Two counts, kept apart on purpose. Six programs have `alloc_depth >
built_depth` — the root walk gets a smaller number. **Seven** have a champion
NODE the walk never visits; the extra one is `tco.lang`, where the deepest
constructed value is unreachable but another value of the same depth is
reachable, so the reported depth is right for the wrong reason. Only the six
are a finding about depth.

Per program, the ratio of built to retained is not uniform and the outlier is
not a self-hosting program:

| program | retained | built | ratio |
|---|---|---|---|
| `shapes.lang` | 191 | 250 316 | **1310x** |
| `self_eval.lang` | 6 615 | 1 275 775 | 193x |
| `self_host.lang` | 14 562 | 874 861 | 60x |
| `checks_demo.lang` | 55 | 1 058 | 19x |
| `deep.lang` | 170 061 | 1 222 169 | 7.2x |
| `meta.lang` | 2 493 635 | 2 770 491 | 1.11x |

`meta.lang` is a tail-recursive interpreter loop where every step is an input
to the next — almost nothing is garbage. `shapes.lang` is 62 lines of
structural typing and throws away 99.92% of what it builds.

## 4. The deepest values Whence builds are its own histories

Both champions are provenance reified as data, which is the feature the
language exists for.

**`self_eval.lang`, D = 1201, at line 1187.** The Whence-in-Whence evaluator
turns the host's provenance graph into guest records:

```
fn reify_node(op, p, rins) {
  mkb(@{op: mkb(op, "literal", []), v: mkb(p, "literal", []),
        ins: mkb(rins, "list", rins)}, "why", [])
}
```

The deepest path is `@.r @.v @.ins @.ins [0/1]` repeated — period **4**
container levels per level of history, 300 levels of history, 1201 total.
The function's own comment says it threads a node budget *"so a shared/deep
history cannot blow up"*: that budget bounds the COUNT of reified nodes, not
the DEPTH of the record the reification produces.

**`self_host.lang`, D = 16, at line 1291.** `steps(...)` — a list of **802**
provenance steps whose deepest element holds a 15-deep AST. One level deeper
than the AST the root walk finds, and it is the `steps` list, not the AST,
that is the champion. Spine period 9 (`LRRLRRLRR`).

Neither is reachable from any root. **The census that justified the rendering
cap was structurally unable to see the two values in the corpus that bear on
it.**

## 5. What a reader actually gets, measured on the renderer

```
deepest (D=1201, N=3.26e91):  full_show 0.001 s, 9515 chars,
                              depth_stopped=True node_stopped=False, 0 misses named
                              show():   25 chars -> @{k: 0, r: @{ins: [], o…}
widest  (D=1201, N=3.26e91):  full_show 0.011 s, 77 687 chars,
                              depth_stopped=True node_stopped=False
```

So the cap is safe, and it is safe for a different reason than decision 53
gave. It is not headroom — 24 is 48x short of 1201, and it cannot be raised to
cover it (decision 53's own frame arithmetic: 27 host frames at cap 25 against
a 250-frame reserve; `max_depth` puts the ceiling on value depth at 20 000).
What makes it safe is that the renderer **reports** the truncation:
`FullRendering.depth_stopped`, plus the `[…]` / `@{…}` markers in the text.
Decision 52 already refuses to mark anything the rendering did not NAME, so a
miss below the cap correctly stays an unobserved drop — a design that is now
known to have a real population rather than a hypothetical one.

## 6. The claim my own instrument made, and the renderer refuted

The census's first draft said, in a comment I wrote before measuring:

> `N > FULL_SHOW_NODES` is exactly the condition under which a full rendering
> would stop on the WIDTH bound.

It is not. `self_eval.lang`'s champion is 3.26 × 10⁹¹ nodes — 10⁸⁷ times the
20 000 budget — and `full_show` on it reports `node_stopped=False`, because
the DEPTH cap truncates the walk after 25 levels and the truncated unfolding
is small. The renderer never walks `N`; it walks `N` restricted to
`FULL_SHOW_NEST` levels.

The census now decides the width question in two exact cases and measures the
third **on the real renderer** rather than modelling it:

```
N <= FULL_SHOW_NODES               -> cannot fire (truncation is a subset)
N >  budget and D <= cap           -> fires (truncation is a no-op)
N >  budget and D >  cap           -> undecided; RENDER it and read node_stopped
```

Result over the corpus: **15 178** values exceed the budget in size, **2813**
of them really do stop the renderer on it, **12 365** are truncated by the
depth cap first. Round 452's *"nothing in this tree exercises it except the
two tests written for it"* is refuted — and refuted in the direction that
matters, since the value that exercises it is built by the language's own
self-evaluator.

Two hand-built tests hold both sides open, so the claim does not depend on any
corpus program surviving:

* `test_a_value_bigger_than_the_node_budget_need_not_stop_on_it` — 20 010
  nodes, branching factor **one**, `node_stopped` False.
* `test_a_wide_shallow_value_does_stop_on_the_node_budget` — 20 010 nodes,
  depth 1, `node_stopped` True.

## 7. A prefix of construction order is not a sample

The undecided case is bounded by `ALLOC_BUDGET_SAMPLES`, first set to 400.
With that bound the census reported, for `self_eval.lang`:

```
values whose size exceeds the budget: 15178
renderings the WIDTH bound actually stopped: 0 (depth cap truncated first in 400 sampled)
```

**Zero.** Raising the bound past the population gives **2813 of 15 178 —
18.5%**. A uniform 400-sample from an 18.5% population returns 0 with
probability about 10⁻³⁵. The 400 were not a sample: they were the *first* 400
in construction order, and construction order correlates with the property —
the early over-budget values are the narrow-and-deep links of the reify chain,
and the wide ones come later.

The bound is now 20 000 (env-overridable), the census says when its sample was
not exhaustive, and
`test_a_prefix_of_construction_order_is_not_a_sample` pins both readings
against the real program so that whoever lowers the bound for speed is
choosing it knowingly.

**The rule, and it is not specific to this census:** *a prefix is not a
sample. If you bound a scan by "the first K", you have sampled the generator's
ORDER, not its population — and any property that correlates with construction
order will read as zero.*

## 8. The instrument was hiding 97% of its own cost

`census_program` measures `seconds` around the run. The width check happens
*after* it. For `self_eval.lang` that reported **4.39 s** for a program the
census spends **2 m 36 s** on. `width_seconds` is now a separate field and the
render prints both — this repo has found the same shape often enough
(round 452's census that stopped measuring `print` and said nothing) that an
instrument under-reporting its own cost is a defect, not a rounding error.

Corpus totals: **27.11 s in-run, 147.74 s in the width check.**

## 9. Predictions, scored (D-013)

`state/whence/round-456/PREDICTIONS.md`, banked before any measurement.
**Two of seven held.**

| | prediction | outcome |
|---|---|---|
| P1 | `alloc_depth >= built_depth` everywhere | **HELD** — 0 violations |
| P2 | at least one program alloc-deeper | **HELD** — 6 of 23 |
| P3 | corpus max unchanged at 14, `self_host.lang` | **WRONG** — 1201, `self_eval.lang`, 86x |
| P4 | constructed within 1.0–1.5x of walked | **WRONG** — 2.07x |
| P5 | max size 100–5000, under the budget | **WRONG** — 3.26e91, and the budget fires 2813 times |
| P6 | `self_host.lang`'s deepest value is reachable | **WRONG** — it is not, and its alloc depth is 16 not 14 |
| P7 | the hook costs 1.5–3x wall time | **WRONG** — ~1.22x (below) |

P7's number, derived rather than quoted: the census without the hook is
**34.7 s** (the banked baseline); with the hook and a 400-sample width check
it is **43.5 s**; with the hook and the exhaustive width check it is
**189.9 s**, of which `width_seconds` accounts for **147.7 s**. 189.9 − 147.7
= 42.2 s, so the constructor hook itself costs about **1.22x**, and the
expensive half of this instrument is not the hook — it is rendering 15 178
values to find out which bound stops them.

The three "no basis" entries were kept: which program shows the largest gap
was **not** guessed (it is `self_eval.lang`, and the largest *ratio* is
`shapes.lang`, which nothing predicted); the residual's mechanism was named as
one hypothesis and not as the only one — the dead-local mechanism is real and
is what the two paired tests demonstrate, but the corpus champions turned out
to be a different mechanism (consumed-and-discarded provenance reifications),
which is exactly why the bank refused to claim it; and `tests/` was declared
out of scope and stayed out.

**P3 is the one worth dwelling on.** Its basis was "the 14-deep value is a
returned AST, and returned values are reached through the call node" — true,
and irrelevant, because the question was never about the value the root walk
already found. A prediction whose reasoning is about the population you can
see is not a prediction about the population you cannot.

## 10. What changed in the language

**Nothing executable.** `FULL_SHOW_NEST` is 24, `FULL_SHOW_NODES` is 20 000,
`_show` is untouched, and the fast tier's 2344 tests were green before and
after (§11). This round changed a *justification* and the instrument behind
it, which is the honest scope: the constants survive the correction, and
saying so is worth more than moving one to look responsive.

**SPEC.md decision 53, two sentences corrected in place:**

* *"24 leaves ten levels of headroom over the deepest value any example
  builds"* → `RETAINS`, with the 1201 named and pointed at decision 54.
* *"It is a safety valve, not a limit anyone reaches"* → the parenthetical
  about printed renderings survives (max PRINTED depth is still 2, and no
  printed value in the corpus is truncated at either bound); the claim about
  values the corpus *builds* is replaced by the 2813.

**SPEC.md decision 54** states the corrected justification and the rule: *a
bound justified by "nothing reaches it" has to name the population, and "what
the program retains" is not "what the program builds".* For a language whose
values carry their own history the two differ by 2.07x in node count and 86x
in depth.


## 12. Failures and residuals, honestly

**My own counterexample was wrong, and the test caught it.** The first draft
of `test_a_value_bigger_than_the_node_budget_need_not_stop_on_it` built the
over-budget value as `[n, n]` nested 64 deep — which doubles at every level,
so 25 levels of rendering is 2²⁵ nodes and the budget fires immediately. The
test failed with `assert True is False` and it was right to. The corrected
construction has branching factor **one** with the bulk *below* the cap, which
is the shape `self_eval.lang` actually builds. **A counterexample to "N
decides" has to be narrow, not merely large** — I had reproduced the finding's
number without reproducing its shape.

**A test whose premise was wrong in the other direction.** The paired
"invisible value" test was first written as `let a = [[[…]]]` followed by
`len(a)`, and the root walk found it at full depth: `len(a)` makes `a` an
INPUT, and round 452's docstring says in as many words that an input is
reached. Changing the body to `0` — the value used by nothing — is what
actually demonstrates the residual class. The paired control (return `a`, both
censuses agree at 7) is in the file so the first test cannot pass by the walk
merely being bad at something.

**`_payload_size` returned the wrong variable.** Its first draft read
`memo[id(root)]` where `root` was assigned inside the walk loop, so it returned
the last *expanded* node's size rather than the requested payload's. Caught by
a three-line smoke check before any test was written, which is the only reason
it is a footnote and not a corpus-wide wrong number.

**Named rather than quietly dropped:**

* The tracker holds every `WList` buffer alive for the length of a run, which
  works against the interpreter's own `gc_relief=True`. No cap fired anywhere
  in the corpus (`alloc walks that hit a cap: none`), so the ceiling was never
  approached — but "the instrument did not change the measurement" is not
  something this round tested, only something it did not disprove.
* `alloc_size` for `self_eval.lang` is a 92-digit integer. Python's big ints
  made that free; the same arithmetic in a fixed-width language overflows
  silently and reports a small number. Nothing here tests near that boundary
  because there is no boundary to test on this host.
* Each program is censused from ONE run. `rand` exists in this language, so a
  program whose values depend on it could differ between runs. Not checked;
  no corpus program's depth plausibly depends on it, which is a judgement and
  not a measurement.
* `tests/` was declared out of scope in the bank and stayed out. Decision 53's
  claim that the repo's deepest value anywhere is **20 000** still rests on
  reading a generated killer, not on an instrument — and the allocation census
  is now exactly the thing that could take it.
* `render_why`'s own `max_depth=10` was not revisited. A 1201-deep guest
  reification of a why-tree is a fact about that bound too, and this round did
  not ask what it implies.
* No skill was probed. `matcher-defines-the-population` was UPGRADED rather
  than a new skill authored, which keeps the unprobed batch where it was and
  adds three trigger classes with no trigger cases (next-step 5).

## 13. What this round did not change

`whence/values.py`, `whence/interp.py`, `whence/parser.py` and `whence/
lexer.py` are byte-identical to their state at `5844cb7`. The round found that
a constant's justification was measured over the wrong population and the
constant is still right; saying so and moving nothing is the result. The
2344-test fast tier is green before and after, and `examples/` output is
unchanged because nothing in the rendering path was touched.
