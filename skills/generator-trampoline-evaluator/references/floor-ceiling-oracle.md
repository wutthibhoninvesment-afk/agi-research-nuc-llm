# Steps 14–16: the value-model floor, the ceiling, and the frame-charge oracle

Continuation of the numbered steps in SKILL.md — read after direct mode (step 13)
exists and the next optimisation round is being planned. Each step ends in a
measurable outcome; the numbers quoted are from the interpreter this skill was
distilled from and are bands to reproduce, not targets.

14. **The value-model floor: remove the frames AROUND each node, not the
    nodes (round 108).** Once generators and calls are cheap, the profile
    is the value model — the constructor, the operator dispatcher, the
    helper called per field access — and the node COUNT is the semantics
    (a provenance language builds one node per operation, argument,
    binding, decision and call; 2.77 M for one meta.lang run). Do not try
    to build fewer; make each one cost one Python frame or none:
    (a) the constructor is a raw slot store — no `tuple()` normalisation,
    no unboxing test; move those into the general helpers and have hot
    sites pass the slot in its final shape (microbench 214 → 187 ns; a
    site-tuple 4-slot layout measured 145 ns but needs 94 call-site edits
    for ~2.4 % — measure, then decline); (b) one compiled closure PER
    operator with the common-type case inline (exact `type() is` tests,
    the native operator, one node) that falls back to the old dispatcher
    for everything else, so misses keep ONE wording; (c) pass-through
    cases (present record field, in-range list index) return the element
    from the closure and call the helper only for misses; (d) a guard
    that is two identity tests (`c is True` / `c is False`) with the
    miss-builder frame only on the bad path; (e) look for a subclass
    built per step whose only difference is a count of 1 — 99.99 % of
    the merged-decision runs were one decision long, each a two-frame
    `MergedProv` plus two lists; the plain node with the same shape is
    one frame and no lists. Count the runs before deciding: a loop
    through one `if` merges into a single long run and gains nothing.
    Price off tottime, but expect the wall-clock win to EXCEED the
    tottime sum for frame removal (Whence: estimate −15 %, measured
    −25 %; three rounds in a row the upper bound was too low — set it at
    2× the point estimate). Prove identity with a REFERENCE differential
    (`bench/ref_diff.py`: the working tree vs `git show HEAD:` of the
    package on every example, every binding's why-tree, outputs, checks,
    counters) before believing any number.

15. **Find the ceiling before the next optimisation round (round 110).**
    After step 14 the profile is flat: the busiest frames are the tiny
    operand closures (name lookup, constants — 3 M of 17 M calls in the
    big example) and the call function itself. Do NOT build the obvious
    next thing (operand fusion, a source-to-source transpiler) — price it
    with three cheap experiments first: (a) `timeit` a parent closure with
    a name/constant operand fused in vs. called — Whence: 10–20 ns per
    operand, the env walk IS the cost, the call is not; (b) hand-write
    the function body a transpiler would emit for the hot function (every
    closure of the body folded into one Python function, why-tree
    byte-identical) and run it through the real call path — Whence:
    **1.09×**; (c) subclass the interpreter with the call function's
    bookkeeping ablated (no depth/peak/counters/try, cached entry,
    unrolled binding) — **1.14×**, the upper bound of slimming. Then do
    only what (c) covers: cache the body's `(evaluator, frames charged)`
    pair on the body node, unroll the 1-/2-parameter bindings, read
    `depth`/budget once and store back (fib −11.6 %, the big example
    −2 %). Write the ceiling into the spec so the next round does not
    re-derive it: what remains is the value model — one node per
    operation, one env per call — and a different value representation,
    not fewer frames, is the only lever left.
16. **Automate the budget bug class: a frame-charge oracle (round 110).**
    A frame the charge does not know about (round 108's comprehension) is
    invisible under the default limit because the reserve absorbs ~150
    uncounted levels; it surfaces only at the CLI's limit, and only on a
    deep enough program. Make it an oracle of the fuzz campaign: run the
    program under `sys.setprofile` counting call/return events, arm at
    the entry point (`exec_stmt`), read the budget the interpreter
    measured at its first driver call, and at every call event compute
    `excess = (frames above the entry) − (budget measured − budget now)`.
    The maximum excess over the run is the transient the reserve must
    cover; it is bounded by construction (fast-closure recursion ≤ the
    compile height cap, one nested driver, render helpers) and an
    undercount makes it grow with guest depth. Measure the distribution
    over the corpus BEFORE setting the slack (Whence: examples ≤ 19, most
    programs 5–20, the fuzzer's `1 + 1 + …` chains 98 = the height cap,
    all at guest depth 0 — a first guess of 60 would have been four
    false positives), then set the slack between the corpus maximum and
    the injected bug (161 at 160 levels; 1400 at limit 6000). Pin it with
    an injected wrapper that adds one uncharged frame per call. Separately
    measure the reserve's true need in the LIMIT's own units (C-level
    recursion entries count toward the limit but not toward the profile
    hook): binary-search the smallest reserve per program in fresh
    processes (`bench/reserve_probe.py`) over deep templates that exhaust
    the budget, the examples and fuzz programs, and set the reserve at a
    multiple of the corpus maximum.
