# Round 368 (language C) — predictions, banked BEFORE measuring (rule D-013)

Subject: Whence's SPEC section **"Limits that are errors, not crashes"** and
the language's rule 2 ("No exceptions, no null. Every runtime error ... yields
a `miss` value"). Round 366 found one entry in that section that was neither
an error nor a crash (a runaway tail loop hung) and bounded it with
`max_iter`. This round asks the sibling question: **`max_iter` bounds how
many times a program may go round; nothing bounds how big one value may
get.**

## Already observed before these predictions were written
Two things were measured while choosing the subject, and are NOT scored:
- `dbl(40, "ab")` (a tail loop doing `s + s`) under `ulimit -v 2000000`
  raises a raw Python **`MemoryError` traceback, exit 1** out of
  `whence/interp.py:1914 f_add`.
- `range(100000000000)` runs past a 20 s timeout with no output.

Everything below was written before it was run.

## Predictions

**P1 — the four growth sites.** The complete set of places a Whence program
can build a value LARGER than the sum of its inputs' sizes is exactly four:
`+` on two strings, `+` on two lists, `*` on two integers, and `range(lo,hi)`
(the only one whose output size comes from a NUMBER rather than from a
value). No other builtin or operator in the 36-name table can do it.

**P2 — `str()` of a big integer is a SECOND uncaught host exception.**
CPython 3.12 caps `int.__str__` at `sys.get_int_max_str_digits()` = 4300 and
raises `ValueError` past it. Whence's `str(n)` builtin does not catch it, so
`str(x)` on a 5000-digit integer is a Python traceback, not a miss. (If this
is right it is a crash reachable with ~30 lines and NO memory pressure at
all — a much cheaper repro than the MemoryError.)

**P3 — the corpus is nowhere near any plausible budget.** The largest single
value built by any program in `languages/whence/examples/*.lang` is under
**100 000** units (characters for a string, elements for a list, bits for an
integer). I expect the maximum to be a LIST, from `range`, in `deep.lang` or
`tco.lang`.

**P4 — the int-multiply guard is the only one with a hot-path cost, and it
is under 2%.** `f_mul`'s inline numeric path is the one place a size check
lands on code that runs millions of times per program. Guarding it (an
operand magnitude test before the multiply) costs **< 2%** on
`bench/`'s existing timing, and the string/list/range guards cost **< 0.5%**
because they are already off the numeric hot path.

**P5 — no existing test builds a value over the default.** After the change,
the whence fast tier is green with **zero edits to existing tests** — only
new ones added. (1469 passed / 3 skipped / 61 deselected is the baseline,
re-measured at the top of this round.)

**P6 — the guest needs no parity change.** `examples/self_eval.lang` has no
notion of value size; a guest program that grows a value grows a HOST value,
so the host budget fires for guest and host alike and
`tests/test_self_eval.py` stays green untouched.

**P7 — `--max-value 0` must mean unbounded**, mirroring `--max-iter 0`
(v0.26), and `run.py` will have the same latent bug v0.26 found in
`--max-depth`/`--max-iter`: passing the value unconditionally so a
class-level default is unreachable from the CLI. I predict the v0.26 fix
already generalised, so this one will be right by construction.

**P8 — a size miss is reachable in under 60 iterations.** Because the growth
is multiplicative, whatever default is chosen, a doubling loop reaches it in
`log2(budget)` steps — so the new miss will fire in well under 60 iterations
of `s + s`, i.e. `max_iter` (1 000 000) can never see it. This is the
structural reason `max_iter` cannot cover this class and a separate budget
is required rather than a re-tuning of the old one.

**P9 — list concat is NOT a doubling hazard in practice** because
`WList.concat` shares the buffer when the left side is the tip. I predict it
IS a hazard anyway: `xs + xs` calls `buf.extend(other)` and materialises 2n
real pointers, so memory doubles for real. (Scored on whether the doubling
is observable in `len()` and in RSS.)
