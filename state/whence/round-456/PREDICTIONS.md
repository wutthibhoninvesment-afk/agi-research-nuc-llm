# Round 456 (language C) — predictions, banked BEFORE measuring (D-013)

**Question.** `languages/whence/depthcensus.py` (round 452) measures the depth
of the values Whence programs build by walking provenance + structure edges
from a ROOT SET. Its own docstring names what that root set cannot reach:

> a value that is neither bound, nor a discarded statement's value, nor
> printed, nor an input to any of those. … `--roots env` vs the default
> measures the size of the class that the naive set misses; **nothing here
> measures the residual class**.

Decision 53 (`FULL_SHOW_NEST = 24`) was justified by that instrument's number.
This round sizes the residual by measuring the population directly: hook
`Prov`/`MergedProv` CONSTRUCTION and compute depth incrementally at build
time, so every value the program ever makes is counted, with no root set at
all.

## Baselines, RE-DERIVED this round (command banked, not carried prose)

`cd languages/whence && python3 depthcensus.py --json /tmp/r456-baseline-census.json`
(34.7 s wall, solo, nproc=1, HEAD = 5844cb7)

| quantity | value |
|---|---|
| programs in `examples/` | 33 |
| ran / failed to parse | 23 / 10 (the ten are the Hermes-gateway files) |
| max BUILT depth (root-walk) | **14** — `self_host.lang` |
| max PRINTED depth | 2 |
| nodes walked, whole corpus | **3 587 551** |
| `FULL_LEVELS` (= `FULL_SHOW_NEST` + 1) | 25 |
| programs building past the full cap | 0 |
| deepest spine | `Record>WList>Record>Record>WList>Record>Record>Record>WList>Record>Record>WList>Record>Record>str` |

`languages/whence` fast tier at HEAD, solo: **2344 passed, 3 skipped, 101
deselected in 236.18 s** (`./run_tests_fast.sh`).

## Predictions

**P1 (invariant, not a guess).** For every program, `alloc_depth >=
built_depth`. The constructed population is a superset of the reachable one.
If this is ever violated the new instrument is wrong, not the old one.

**P2.** At least one of the 23 running programs has `alloc_depth >
built_depth`. *Basis:* I can name the residual class concretely — a `let`
bound inside a function body and never read again lives in a child `Env` that
is discarded when the call returns; it is not a dropped statement value, not a
top-level binding, and if nothing consumed it, not an input to anything. 23
programs including two self-hosting interpreters almost certainly contain one.
**Confidence: high.**

**P3.** The corpus MAXIMUM is unchanged: `max alloc_depth == 14`, still
`self_host.lang`. *Basis:* the 14-deep value is a returned AST, and returned
values are reached by the root set through the call node. A dead local is
usually shallow. **Confidence: moderate (~60%). This is the prediction I
expect to be the interesting one either way.**

**P4.** Total constructed nodes is between 1.0x and 1.5x the 3 587 551
walked. *Basis:* `meta.lang` (2.49 M of the 3.59 M) is a tail-recursive
interpreter loop whose every step is an input to the next; I expect little
garbage there. **Confidence: low — this is the number I would bet against
myself on.**

**P5.** Max BUILT *size* (element count of one value's structure — the
population `FULL_SHOW_NODES = 20000` bounds, never measured over built
values, only over printed ones) is **between 100 and 5000**, i.e. under the
budget, so nothing in the corpus reaches the width cap either. *Basis:* only
that the deepest value is a 14-level AST of a ~200-line program. **Confidence:
low.**

**P6.** The deepest CONSTRUCTED value in `self_host.lang` is also in the
reachable set (champion `id` found among the walked nodes). *Basis:* same as
P3. **Confidence: moderate.**

**P7.** The construction hook costs between 1.5x and 3x wall time on the
census: 34.7 s -> 52-105 s. *Basis:* `Prov.__init__` is measured at ~187 ns
(round 108, `values.py` comment); the hook adds one `isinstance` chain and a
`max()` over children per node. **Confidence: moderate.**

## Where I have NO basis, stated rather than guessed (round 435 next-step 7)

* **Which** program (other than `self_host.lang`) will show the largest
  `alloc_depth - built_depth` gap. I have not read any of the 23 programs for
  this purpose and will report what it holds.
* Whether the residual is dominated by dead locals, by miss-path values, or by
  builtin intermediates. P2's basis names one mechanism; it does not claim it
  is the only one or the biggest one. The instrument must attribute what it
  finds, not have the attribution assumed here.
* Whether `tests/` builds anything deeper than `examples/` does (round 452's
  other named residual). Out of scope for this round unless it falls out.
