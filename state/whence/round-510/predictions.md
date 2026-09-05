# Round 510 (language C) — predictions, banked BEFORE any measurement

**Rule D-013.** Written and committed before the instrument below was run
even once. Scored honestly in `knowledge/round-510-*.md` §Predictions.

**Subject.** Round 506's next-step #1, carried unpaid for four rounds:

> `self_eval.lang`'s `apply_builtin` has at least one branch no program
> reaches, and nothing measures how many. Round 506 found the `typed`
> propagation branch by running out of other explanations; `abs` (1 run /
> 2 written) and `shapeof` (5/6) are the same shape and were not chased. A
> per-BRANCH reachability census over the self-evaluator is the obvious
> next instrument, and `runlive.py`'s hook is the wrong level for it — this
> needs the guest AST, not the host dispatch slot. language(C).

**Artefact to be built:** `languages/whence/branchlive.py` — the fourth
level of this program's liveness question (503 `scopecall` = is the Python
def referenced; 504 `builtinlive` = is the guest name called in source; 506
`runlive` = is the builtin invoked at runtime; 510 `branchlive` = is the
guest AST BRANCH taken at runtime).

---

## A. The hook

**P1 — the funnel is `Prov.__init__`, not a dispatch method.** Every one of
the interpreter's branch-decision sites (`eval_If`, `_if_inline`,
`_if_chain`, the compiled `f_if`, the direct `d_if`, and `_wrap_ifs` /
`_finish_call` for decisions a tail call carried) materialises the decision
as a provenance node whose `op` is the literal `"if"` and whose `detail` is
`"took then-branch"` or `"took else-branch"`. Hooking the constructor is
therefore all four dispatch paths at once, with no compiler change.

**P2 — and the funnel has a hole that inheritance hides.**
`MergedProv.__init__` does NOT call `Prov.__init__`; it re-inlines the six
slot assignments deliberately (a v0.10 speed change, "one frame, not two").
So a census that hooks only `Prov.__init__` silently misses every run of
≥2 identical `if` decisions merged by a tail loop. **Falsifiable form:**
over the self-evaluator corpus, hooking both constructors will report
strictly more reached `(line, branch)` pairs than hooking `Prov` alone, and
the difference will be **≥ 1 and ≤ 40** pairs.

**P3 — `rescue` is NOT censusable at this hook.** `Rescue`'s recovery path
builds `derived("rescue", "recovered", …)`; its pass-through path returns
`left` unchanged and builds **no node at all**. So the constructor hook can
see that a rescue recovered and can never see that a rescue did not. Any
honest `branchlive` reports `if` only, and says so.

**P4 — the hook's wall-clock overhead on one `run.py examples/self_eval.lang`
is a factor between 1.2× and 2.5×.**

## B. The denominator

**P5 — `self_eval.lang` parses to between 380 and 520 `A.If` nodes.**
(`grep -c "if "` is 503, which over-counts comments and `else if` text and
under-counts nothing.)

**P6 — an `if` with no `else` still yields an `A.If` node with a synthesised
empty `otherwise` Block**, so "else-branch never taken" will be reported for
guard-shaped ifs and is NOISE unless the census marks a synthesised arm.
If the parser instead emits something other than `A.If`, P6 is a MISS.

## C. The measurement

**P7 — one `run.py examples/self_eval.lang` reaches BOTH arms of fewer than
60 % of the file's `A.If` nodes.**

**P8 — one such run leaves ≥ 30 `A.If` nodes with NEITHER arm taken** (the
node's condition was never evaluated at all).

**P9 — `test_self_eval.py`'s corpus (library + one `run_src` per case, the
~60 cases in `CORPUS` plus the shape/record/ret-chain case lists) reaches
strictly more `apply_builtin` branches than the standalone run**, and the
increase is **≥ 20** `(line, branch)` pairs.

**P10 — `apply_builtin` (from its `fn` line to the end of its body) holds
≥ 60 `A.If` nodes**, and **≥ 8** of them have an arm that the standalone
run and the corpus run BOTH fail to reach.

**P11 — round 506's `typed` propagation branch is one of the unreached
ones** under the standalone run. If it is reached, P11 is a MISS and the
round says so.

**P12 — `abs` and `shapeof`, round 506's two unchased "same shape" cases,
are NOT the same shape as `typed` at branch level:** at least one of them
will turn out fully reached, i.e. round 506's source-level ratio (1 run / 2
written, 5/6) does not predict branch reachability.

## D. Cross-cutting

**P13 — the census finds at least one branch that is unreachable as written
(dead code), not merely unexercised**, in `self_eval.lang`.

**P14 — no existing whence fast-tier test goes red** from adding
`branchlive.py`, and `copyparity escapes --root languages/whence` stays at
0 escaping expressions (the round-413 guard is used from the start).

**P15 — the round-509 readset merge, once landed, makes
`blast languages/whence/branchlive.py` name at least one
`languages/whence/tests/` node** — i.e. the instrument round 509 built
would have warned THIS round about the tree it is editing. Measured on this
round's own diff.
