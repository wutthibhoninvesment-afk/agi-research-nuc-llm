# Round 482 (language C) — predictions, banked BEFORE measuring (D-013)

**Base commit:** `0b9e1dc` (this round's first commit, which lands round
481's harness diff and touches nothing under `languages/whence/`).
**Box:** `nproc` = 1. **Subject:** round 476's next-step 2, carried
un-run through rounds 477-481 and restated as round 480's next-step 2:

> "Decision 58's rule is stated for `Env` and applied to `Env` only. The
> generalisation — *every value this implementation hands a caller is a
> surface* — has not been swept. The unrendered candidates a caller can
> reach: `Explanation` (payload of `why`), `Closure`, `Builtin`, `WList`,
> `PMap`, `Record`, `Miss`, `Guess`. `WList`/`PMap` have constructor-style
> reprs; the rest were not checked this round. Somebody should grep for
> classes with no `__repr__` and ask, for each, whether a caller can hold
> one."

## 0. Read set — what this bank is entitled to be confident about

**READ before banking:**

- `whence/values.py`: the class map (`grep -n "^class |__slots__|__repr__"`),
  and in full the bodies of `WList.__repr__`, `Prov.__repr__`,
  `PMap.__repr__`, `Prov.show`'s tail, `MergedProv`, `Miss`, `Guess`,
  `Record`, `Closure`, `Builtin`, `Explanation`, `QUOTE_ESCAPES`/`quote_str`
  head.
- `whence/interp.py` lines 205-290: `Env`, its decision-58 `__repr__` and
  the comment block above it; `_Call`, `_TailCall` headers.
- The same `grep -n "^class |__repr__|__str__"` map over every other module
  in the package (`ast_nodes`, `foreign`, `lexer`, `parser`, `timetravel`).
- `SPEC.md` § Decision 58 in full; `knowledge/round-476-...md` §10.
- `state/research-state.md` next-steps for rounds 476, 480, 481.

**ESTABLISHED BY READING, not predicted** (so no row below takes credit
for it): at `0b9e1dc` the classes carrying a `__repr__` anywhere in the
package are exactly `Node`, `Env`, `Token`, `WList`, `Prov`, `PMap` —
six. `Miss`, `Guess`, `Record`, `Closure`, `Builtin`, `Explanation`,
`FullRendering`, `_FullCtx`, `_Bare`, `_PNode`, `_Call`, `_TailCall`,
`_UnboundType`, `MergedProv` (which inherits `Prov`'s) carry none of
their own. That is a grep, not a finding.

**NOT read before banking** — so the rows below are honest `[MODEL]`
guesses about them: any test file under `languages/whence/tests/`; the
body of `Interpreter.run`; `Env.get`; `_install_builtins`; the `why`
builtin; anything that formats a value into a diagnostic string; and the
in-flight fast-tier baseline's output file, which is running as this is
written and has not been opened.

## 1. The rows

Each row states the falsifier. A row with no falsifier is not banked.

**P1 [MODEL] — what a caller actually holds.** `Interpreter.run(src)`
returns an `Env` (decision 58 says so). The value a caller then pulls out
by name is a **`Prov`**, not a bare Python `float`/`str`, so `Prov` — a
class that HAS a repr — is the class a caller holds most often, and the
sweep's subject is not only the six unrendered classes.
*Falsifier:* the by-name lookup returns a bare Python scalar, or a `_Bare`.

**P2 [MODEL] — reachability, the thing round 476 declined to check.** Of
the six unrendered candidates it named (`Explanation`, `Closure`,
`Builtin`, `Record`, `Miss`, `Guess`), **all 6** are reachable by a caller
holding nothing but `Interpreter.run`'s return value plus attribute access
(`.payload`/`.vars`). *Falsifier:* any one of the six cannot be produced
that way. I bank 6/6 rather than "at least 4" — round 481's two misses
were both lower bounds met by a factor of five, and a floor is a row that
cannot teach anything.

**P3 [MODEL] — the two round 476 waved through are ALSO defective, and
for a second reason.** `WList.__repr__` (`"WList(%r)" % self.to_list()`)
and `PMap.__repr__` (`"PMap(%r)" % self.to_dict()`) satisfy neither half
of decision 48's dichotomy — `WList([...])` is not a Whence literal an
author can type back, and it is not prose — **and neither has a length
cap**, which was decision 48's own fourth defect. A 5,000-element list
reprs to a string longer than 2,000 characters.
*Falsifier:* either repr is bounded, or either is a legal Whence literal.

**P4 [MODEL] — the address leaks THROUGH a repr that exists.**
`Prov.__repr__` interpolates `self.show`, and `WList`/`PMap` interpolate
their elements with `%r`. So a caller who holds a rendered class can
still be shown `<whence.values.Record object at 0x...>` nested inside it,
which means the six missing reprs are not six isolated holes.
*Falsifier:* no nesting of an unrendered class inside a rendered one
produces `object at 0x` in the outer repr.

**P5 [MODEL] — magnitude.** Counting every class in the package that (a)
a caller can hold and (b) whose `repr()` violates decision 58's stated
rule (bounded, deterministic, no heap address, prose-or-Whence-literal),
the count at `0b9e1dc` is **≥ 8** — the six unrendered plus `WList` and
`PMap`. *Falsifier:* the audited count is 7 or fewer.

**P6 [MODEL] — the Whence-level surface is CLEAN.** Distinct from P1-P5:
no *Whence* program can get a heap address into a *Whence-level*
diagnostic (a `miss` reason, a `why` rendering, a printed value). The
`0x...` leak is confined to the Python embedding API. I bank this as the
optimistic direction on purpose: if it is wrong the defect is much worse
than round 476 described, and I would rather be caught predicting the
better world. *Falsifier:* one input program whose Whence-visible output
contains `object at 0x`.

**P7 [MODEL] — the fix is inert.** Adding a `__repr__` to the six changes
**zero** existing test outcomes: nothing in the suite asserts against a
default `<... object at 0x...>` repr. *Falsifier:* any currently-green
test in the fast tier goes red from the reprs alone.

**P8 [SELF] — the baseline, cited not re-guessed.** The fast tier at
`0b9e1dc` reports **2661 passed, 3 skipped, 115 deselected** — the
driver's own whence-health-check figure for round 481, whose tree differs
from `0b9e1dc` in no file under `languages/whence/`. The run is in flight
as this is banked and its output has not been opened.
*Falsifier:* any of the three numbers differs.

**P9 [MODEL] — the shape of the durable artefact.** Six hand-written
`__repr__`s do not close this; the next class added to `values.py` opens
it again. What has to ship is an *enumerating* check — walk the package's
classes, decide reachability, assert the rule — and I predict it finds at
least one class **round 476's list does not name**. *Falsifier:* the
enumeration's defective set is exactly the eight of P5, no more.

**P10 [MODEL] — where the sweep will hurt.** The hardest class to render
honestly is `Closure`, because a closure captures an `Env` and decision
58's `Env.__repr__` is itself unbounded in nesting depth. A naive
`Closure.__repr__` that names its env recurses or prints a scope listing
of arbitrary size. *Falsifier:* `Closure` renders in one obvious bounded
line with no such tension, and some other class is the hard one.
