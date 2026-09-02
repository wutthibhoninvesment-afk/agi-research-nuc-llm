# Round 462 (language C) — predictions, banked before the change

**Subject.** Round 458's next-step 2: *"The harvester's residual is 257
programs and nothing narrows it. 127 unresolved names … and 130 non-constant
source nodes (BinOp 120, List 38, Call 23, Subscript 9, IfExp 1). … The
cheapest next slice is the BinOp class."*

**Baseline, MEASURED at HEAD before this file was written** (round 460's
item 5 and round 461's P1-P4: a baseline taken from a predecessor's prose is
not a baseline). `depthcensus.harvest_tests()` at `508b95f`:

    files 62   calls 985   programs 488 (499 before dedup)
    unresolved_args 127    nonconstant_programs 131
    forwarded_args 81      parse_only_programs 73
    unparsed_programs 3    ambiguous_scopes 22
    executing_runners 69   parse_only_runners 29

and the non-constant class, re-derived node by node:

    38 List      35 BinOp:Add   25 BinOp:Mod   18 Call:join
     9 Subscript  4 Call:read    1 IfExp        1 Call:replace   = 131

Round 458's published breakdown (`BinOp 120, List 38, Call 23, Subscript 9,
IfExp 1`) sums to 191 against its own stated total of 130. The BinOp class is
**60**, not 120, and the total is **131**, not 130. Recorded here as a
baseline correction, not as a prediction.

## The predictions

**P1 — precision, not recall, is the larger defect.** More than a quarter of
the 131 non-constant residual nodes are call sites that are not Whence
runners at all, so the instrument overstates its own blind spot.

**P2 — `subprocess.run` is the single biggest false class**, and it accounts
for **35-50** of the 131.

**P3 — `.exec_stmt`'s first argument is an AST statement node, never source
text**, so every `exec_stmt` call in a source position is a false residual:
**5-12** of the 131.

**P4 — the false positives have contaminated the residual and NOT the
corpus:** the number of harvested PROGRAMS attributable to a `subprocess` or
`exec_stmt` call site is **0**.

**P5 — separating "this call executes" from "this call's arg0 is source"
does not shrink the program count.** After the split, programs stay at
**488**; `executing_runners` stays at **69** or falls by at most 2.

**P6 — folding `%`, f-strings, `IfExp` and constant `.join` recovers between
40 and 120 new programs**, i.e. the corpus lands in **528-608**.

**P7 — the champion does NOT move.** The deepest test-corpus value stays
`test_v44.py` at D = 20000 in suite mode, and the second stays 3001
(`test_v04.py:259`).

**P8 — at least one recovered program fails to parse.** The `%`-folded
class substitutes case data into templates, and some cases are deliberately
ill-formed source; `unparsed_programs` rises above 3.

**P9 — a multi-valued fold is required, not optional.** At least one node
(the `IfExp`, and every `%` whose right operand iterates a table) denotes
MORE than one string, so a `str|None` folder cannot express the answer:
`_const_strs` returning a list is the only shape that closes the class
without guessing. At least **10** of the recovered programs come from a node
that denotes 2 or more strings.

**P10 — the total residual falls by at least 60** (from 258 = 127 + 131) and
**does not reach zero**; `Call:join` over a loop-built list and `Call:read`
over a runtime `listdir` are not statically foldable and will remain.

**P11 — sizing.** Harvest (AST only, both corpora) stays under **20 s**.
A full `census_tests` in one mode stays under **200 s** at the new corpus
size; the round runs at most one full census per mode.

**P12 — no constant in `SPEC.md` changes.** Decisions 53, 54 and 55 stand as
written; this round adds a decision about the harvester's precision rather
than amending a number.

**P13 — the `unresolved_args` class is dominated by one name.** `src` alone
is **70-95** of the 127, and after the fold it falls by at least half.

**P14 — wiring.** `depthcensus.py` has no CLI path to the test corpus at all
(`main()` parses `--program`/`--roots`/`--json` and calls `census()`, never
`census_tests`), so round 458's item 1 ("not wired into any tier") is
understating it: the census cannot be RUN from the command line, by any
tier, today.
