# Whence — a provenance-first language

*Spec level: **v0.33** (round 386). The `## vN` sections below are the
authoritative version list and each names the round that built it; this
line deliberately no longer enumerates rounds, because the enumeration it
replaced had said "v0.16.6 + v0.14.2" since round 266 while the file went
on to document v0.17, v0.18, v0.19 and v0.20 — a header asserting a number
no round re-executes, which is the rot class round 321 item 14 named and
round 345's `xref_check.py` was built for. Round 348 wrote that sentence
and the sentence rotted in ONE round: round 350 added `## v0.21` and left
the header saying v0.20, so round 354 arrived to find it two levels stale.
A better sentence was never the fix. `tests/test_v22.py::
test_spec_level_header_matches_the_highest_version_section` is, and it is
what keeps this line true from here on.*

**One idea:** every value remembers where it came from. `why x` returns the
derivation tree of `x` as a first-class value. Failures are values too, so a
failed computation can be asked to explain itself. **v0.2:** history is
*data* — you can fold over it, travel back into it, and ask a failure for its
origins as records — and recursion depth is a language tunable, not a host
limit. **v0.3:** keeping *all* history is cheap (lists share storage, so
growing one in a loop retains every intermediate in O(n) memory), tail
calls run in one frame and leave one merged history node, and two
histories can be diffed to find the origin of a difference. **v0.4:** a
value *is* its history node (one object, not two), a source literal is one
node however often it runs, a tail loop's repeated decisions merge into one
node per run, call-free code runs as compiled closures (3–5× faster), and
`contrast` shows two histories side by side.

## Anti-mainstream design decisions
1. **Provenance-carrying values.** Every runtime value is `(payload, prov)`;
   `prov` is a DAG node `(op, detail, line, inputs, show, value)` recording
   how the value was made — and, since values are immutable, *the value
   itself* (one pointer). `why x` reifies it; `snip x` truncates history;
   `note("label", x)` inserts a human waypoint.
2. **No exceptions, no null.** Every runtime error (division by zero, unbound
   name, bad index, arity mismatch, parse failure in `num`, non-callable call,
   negative `sqrt`, recursion past `max_depth`, …) yields a `miss` value
   carrying *reason strings* plus provenance. `miss` propagates through every
   operator like NaN — but unlike NaN it can tell you *why*. Recover with
   `a rescue b` (the recovery's provenance keeps the miss it recovered from).
   Test with `missed(x)`, inspect with `reasons(x)`, locate with `blame(x)`.
3. **No assignment, only binding.** `let` binds once; rebinding a name in the
   same block is a **parse error** (shadowing in inner blocks is fine). All
   iteration is recursion / `map` / `filter` / `fold`.
4. **Tests are statements.** `check "label": expr` runs inline; a failing check
   automatically prints the why-tree of its value. The interpreter prints a
   check report and exits nonzero if any check failed.
5. **Strict booleans.** Only `true`/`false` are conditions. `if 0 {…}` is a
   miss, not "falsy". `==` on functions is a miss (identity lies, structure is
   undecidable). `miss == miss` is a miss (like NaN — use `missed`).
6. **History is queryable data, not a printout (v0.2).** `steps(x)` is the
   whole derivation as a list of step records; `at(x, "let a")` is the real
   value a named step had — live, computable, with its own history;
   `blame(x)` is the list of steps that *created* a failure (misses with no
   missing input). Programs check their own provenance structurally instead
   of grepping `str(why x)` (which is render-capped and can silently miss).
7. **Recursion is trampolined (v0.2).** Whence calls do not consume host
   stack; depth is capped by `max_depth` (default 20000; `run.py --max-depth
   N`) and exceeding it is an ordinary miss naming the function and depth.
   **v0.9:** the first few hundred levels of a recursion run by plain host
   recursion under a frame *budget* measured from the live recursion limit
   (direct mode); deeper levels fall back to the trampoline. Depth is still
   a language tunable, host stack depth is still bounded by construction —
   the budget only decides which levels pay for a generator.
8. **Tail calls merge, they do not forget (v0.3).** A call in tail position
   of a function body (the body's final expression, through `if` branches
   and nested blocks) re-enters the current frame: no depth, no host stack.
   Its provenance is ONE node `call f` with `count` = frames merged (rendered
   `call f ×N`; mutual recursion renders `call even/odd ×N`) whose inputs
   are the final result followed by the `if` decision of every iteration —
   so `why` still explains every branch taken. A tail loop is bounded by
   `max_iter` (default 1000000, `run.py --max-iter N`), which turns a
   too-long one into a miss; `--max-iter 0` (`max_iter=None`) opts out and
   makes it unbounded again. **Until v0.26 (round 366) unbounded was the
   DEFAULT**, and `max_depth` cannot substitute for it — a tail call spends
   no frame, which is the whole point of the rule — so a non-terminating
   tail recursion had no bound at all and hung. `interp.peak_tail` reports
   the longest single loop, as `peak_depth` does for depth. A call under
   `let`, `rescue`, an operator, an argument, `why`, `snip` or `check` is
   not a tail and still costs a frame.
   **Tail position changes space, never meaning (round 336).** Lifting any
   tail call out of tail position with a `let` must not change the value,
   the miss, which `-> Type` contract is blamed, or the line the miss
   reports — only the frame count. `tests/test_v13.py`'s
   `test_tail_and_lifted_chains_agree_exhaustively` drives the whole
   `f0 -> f1 -> …` family (every combination of return annotations up to
   4 hops, plus loops that revisit a closure) through both forms, laid out
   line for line, and requires byte equality. **It cannot drive a
   NON-terminating chain** — the tail side would hang the suite rather than
   fail it — and until v0.26 that was the one shape where lifting changed
   the answer from "no value, ever" to a depth miss in 0.07s. Bounding the
   tail loop is what makes that comparison expressible;
   `tests/test_v26.py` is where it is now made.
9. **Full history is the default, and it is affordable (v0.3).** Lists are
   immutable views over a shared append-only buffer: `push(xs, x)` and
   `xs + ys` extend in place when `xs` is the buffer's tip and copy
   otherwise, so a list grown inside a fold keeps every intermediate list
   reachable from the history in O(n) total memory (v0.2: O(n²)). No
   retention policy, no `snip` required; the old values can never see the
   new elements because a view only reads its own prefix.
10. **Histories can be diffed (v0.3).** `diverge(a, b)` walks two histories
   in lockstep and returns the *origins* of their difference: steps whose
   inputs agree but whose result differs (kind `"value"`, e.g. the literal
   that changed between two runs) or where the computations have different
   shapes (kind `"step"`). Consequences downstream of an origin are not
   reported; naming steps (`let x` vs `let y`, `note`) never count as
   divergence. **v0.4:** `diverge([r0, r1, …])` compares every run with the
   first and tags each origin with `which` run diverged; `contrast(a, b)`
   renders the lockstep paths from the roots to each origin side by side.
11. **A value is its provenance node (v0.4).** There is no separate
   "value" object: the node that records how a value was made *is* the
   value (`v.prov` is `v`, `v.payload` is `v.value`). Retaining full
   history therefore costs no extra objects, and every step of a history
   is a real value for free. A source literal evaluates to the same node
   every time (`steps(x, "literal")` counts source literals, not
   evaluations); everything derived is a fresh node.
12. **Repeated decisions merge (v0.4).** Within a tail loop, consecutive
   identical branch decisions (same `if`, same branch) become ONE node
   `if took else-branch ×N` whose inputs are the N individual conditions —
   the same trick as `call f ×N`, and just as lossless. A tail loop that
   always takes the same branch leaves a flat history: `call f ×N` → its
   result, plus one merged `if` holding every condition. Decisions that
   alternate (or come from different `if`s) stay separate.
13. **Call-free code runs compiled (v0.4).** A subtree with no call in it
   cannot recurse into Whence code, so it is compiled once into Python
   closures and evaluated inline; only calls (and what contains them) run
   on the trampoline. Semantics are shared, not duplicated:
   `Interpreter(fast=False)` runs everything on the trampoline and must
   produce identical values and identical why-trees (the test suite checks
   a corpus both ways). Subtrees taller than 100 levels stay on the
   trampoline so host stack depth is never a function of program shape.

<!-- 14-26: never minted. The list above was written for v0.1-v0.4 and then
     stopped being appended to for ~200 rounds while the prose kept citing
     it; round 338 resumed at 27, not 14, and nothing in this tree has ever
     defined OR cited 14 through 26 (`skills/skill-authoring/scripts/
     xref_check.py --provenance`, rounds 345/346: "never-defined in 46
     revision(s)"). The range is left RESERVED rather than closed by
     renumbering, because 27/28/29 are cited from 17 authoritative sites —
     SPEC prose, `whence/parser.py`, `ast_nodes.py`, `values.py`,
     `test_v12.py`, `test_v13.py`, `research-state.md` — and a renumber
     would break every one of them to buy nothing. Do not reuse 14-26 for
     new decisions: the gap is evidence of the rot round 345 found, and
     this list is the registry `xref_check.py` reads. Append here in the
     SAME round that mints a number. -->

14-26. *(reserved — never minted; see the comment above.)*
27. **A self-hosted implementation may RECOVER host state instead of
   threading it — and a rule the guest cannot express is a rule the two
   sides will silently disagree about (v0.12/v0.13 guest parity, round
   338).** `whence/parser.py` keeps `self.shapes`, a mutable dict
   `shape_def()` writes and `parse_type()` reads. Whence has no mutation,
   and threading an accumulator would not have sufficed either: the host's
   set was deliberately NOT scope-aware, so all ~25 parser functions —
   expression parser included — would have had to return it too.
   `self_host.lang`'s `shapes_declared_before(toks, p)` is instead a PURE
   function of the token stream, exact rather than approximate on two
   premises verified against the host and pinned as tests: ADJACENCY (the
   three tokens `shape` NAME `=` must be adjacent, which is what the
   host's own `peek(1)`/`peek(2)` require, and NAME NAME never occurs
   adjacently in a legal expression, so a match implies statement start)
   and COMPLETION (the closing `}` must precede `p`, because the host
   writes `self.shapes[name]` only after `expect("}")` — which is what
   rejects `shape Foo = @{x: Foo}`). Cost is zero on every pre-existing
   program: the primitive-tag branch is tested first, so the scan is
   reached only for a non-primitive name.
   **The general rule, which two later decisions lean on:** the guest sees
   only what the language exposes, so any host rule depending on state the
   language cannot reach is a rule the guest cannot mirror. v0.18
   (decision 28) removed one such asymmetry rather than mirroring it;
   v0.20 (decision 30) chose sorted field order over declaration order for
   exactly this reason.
28. **The type namespace IS the value namespace, so it has exactly one
   scope rule — decision 3's (v0.18, round 342).** `shape Name = @{…}`
   desugars to a `let`, so the name already obeyed decision 3 at RUN time
   (bound in its block, shadowable, gone when that block closes) while the
   parser used one flat file-global table and accepted the name in any
   later annotation anywhere in the file. `Parser.self.shapes` becomes
   `self.shape_scopes`, a frame stack pushed and popped by `stmt_list`
   (whose only two callers are `block()` and `parse_program()`, so a frame
   is exactly a `{ … }`), looked up innermost-out — the same walk the
   desugared `let`'s `NameRef` performs at run time. Sibling blocks may
   each declare the same shape name; an inner block may shadow an outer
   one; and an annotation naming a shape whose block has closed is a parse
   error at the annotation's own line and column instead of one of three
   unrelated run-time outcomes. See `## v0.18` for the measured
   before/after table.
29. **A parameter contract and a return contract are ONE rule, resolved at
   ONE moment in ONE environment (v0.19, round 344).** `-> Type` (v0.13)
   was carried on the fn node and resolved once, in the DEFINING env, at
   closure creation. `p: Type` (v0.12) was ERASED by the parser into a
   `let p = typed(p, spec, label)` statement prepended to the body, so its
   spec was an ordinary expression re-evaluated in the CALL env on every
   call. One signature could therefore name two different shapes with one
   name — `fn f(P, p: P)` resolved the annotation's `P` to the ARGUMENT,
   because the parameter was bound before the guard statement ran. v0.19
   carries the parameter half on the node too (`FnDef.param_types`,
   `FnExpr.param_types`), resolves it with the SAME `_closure_spec` in the
   SAME env at the SAME moment as `ret_type`, and checks it with the same
   `_check_contract` — `_check_ret` renamed, because it was never about
   returns. The four asymmetries that REMAIN are deliberate and are listed
   in `## v0.19`; each is a place where the two ends genuinely differ, not
   a place two implementations drifted.
30. **A type miss names the FIELD, not just the shape (v0.20, round 348).**
   `_type_match` walks a record spec field by field and knows exactly which
   field broke a match and how — and, until v0.20, returned only the spec's
   NAME, so the whole contract system answered a structural mismatch with
   `expected Point, got record`: the one thing the reader already knew. On
   a spec with no `__shape` — legal, and ordinary under this file's own
   "structural, not nominal" rule — it degenerated to `expected record, got
   record`, which says nothing at all. That is decision 2's promise
   ("unlike NaN it can tell you *why*") going unmet at the newest and
   most-used contract surface. A failed check now appends the PATH to the
   field that broke it: `(no field 'a'.'y')`, `(field 'x' expected num, got
   str)`, `(field 'x' is a miss)`. Fields are visited in SORTED order, not
   declaration order, because declaration order is not recoverable through
   `keys()` and a rule the guest cannot express is one the two sides would
   silently disagree about (decision 27). Because decision 29 had already
   made the two contract ends one rule, the change was written once and
   arrived at four surfaces at once: `typed`, `-> Type`, `p: Type`, and
   every `shape` in every example.
31. **A rule the guest cannot express is a rule the language does not have
   (v0.21, round 350).** The lexer classified characters with
   `str.isdigit()`/`isalpha()`/`isalnum()` — Unicode — while
   `examples/self_eval.lang`'s guest lexer, which decision 27 already makes
   the arbiter when the two disagree, has only ever had explicit ASCII
   strings. A guest written in Whence cannot enumerate Unicode, so that gap
   could only ever be closed by NARROWING the host. Two independent facts
   said narrowing was also just correct: this file has specified "ASCII
   digits" for `num(text)` since v0.4.1 while the literal grammar accepted
   798 characters, and 128 of those made `int()` raise a bare `ValueError`
   out of `tokenize`. The general form: when the host has a capability the
   guest structurally cannot mirror, the question is not "how do we teach
   the guest" but "was that capability ever specified" — and here it was
   specified AGAINST. Strings and comments are untouched; they hold any
   character, because nothing about them requires the guest to enumerate
   anything.
32. **An error that can name the fix, names it (v0.22, round 354).**
   Decision 2 promises a failure that "can tell you *why*", and every
   version since has read that as *name the symptom precisely*. v0.22 adds
   the other half: where the language can compute what the author should
   have WRITTEN, the error says that too. Two surfaces, one rule.
   (a) A builtin whose argument is the wrong KIND re-checks the arguments
   it was actually given against its declared signature in every other
   order, and if any order fits, appends `(arguments fit fold(fn, acc,
   xs))`. (b) A parse error that recognises a mainstream construct Whence
   deliberately does not have names the Whence spelling instead:
   assignment (`x = 2`), an unbraced branch, a `{a: 1}` record literal, a
   `rescue { }` block, and two adjacent names. Both halves are SILENT
   unless the cure is computed, never guessed — the builtin half says
   nothing when the given order already satisfies the declared kinds
   (which means the miss is about something the kinds do not model), and
   the parser half fires only on token patterns the grammar cannot
   otherwise produce. The evidence for the second half is measured rather
   than assumed: of ten machine-written Whence programs that fail to
   parse, ONE named a cure before v0.22 and NINE do after — and TEN after
   decision 33, which removed the grammar laxity the last one was hiding
   behind rather than adding an eleventh hint.
33. **A line break is the only statement separator, and it is required
   (v0.23, round 356).** Whence has never had a `;` and its lexer has
   called newlines statement separators since its first commit, but the
   parser accepted `let a = 1 let b = 2` as two statements: the separator
   was documented and unenforced. Making it mandatory is the smaller
   grammar, not the larger one — nothing is added, one permission is
   withdrawn — and it is what lets a whole class of mistake be reported
   where the author made it instead of several tokens later, because a
   statement boundary can no longer silently absorb the evidence. Two
   deliberate limits keep it from shadowing better diagnoses. It fires
   only for a token that could actually START a statement, so `x = 2`
   still gets decision 32's assignment clause rather than a separator
   complaint; and the three tokens that both start a statement and
   CONTINUE an expression (`-`, `(`, `[`) are still absorbed by the
   expression grammar first, so `let a = 1 -2` binds `-1` — the automatic-
   semicolon-insertion hazard, confined to three tokens and written down
   rather than discovered.
34. **A position is a fact about the program under analysis; a sentence is
   a choice about how to describe it (v0.24, round 360).** The two
   implementations must agree on the first and are still not required to
   agree on the second — and rule 3 is asserted as a FACT
   (`test_wording_is_still_not_a_guest_contract` requires >=10 cases with
   equal positions and different sentences), so a later round cannot make
   the distinction vacuous by accident. *(Added to this list by round 362:
   round 360 numbered its decision 34 in `## v0.24` and did not add it
   here, which would have made the list's own numbering the next thing to
   rot.)*
35. **A message has NAME slots and VALUE slots (v0.25, round 362).** A
   name slot holds a name — a string — or says the thing is anonymous; a
   value slot renders the offending value, and BOTH implementations must
   be able to render it. `_type_match`'s `__shape` is a name slot: round
   335 rendered a non-string one through `show_payload`, so
   `typed(1, @{__shape: 5, a: "num"}, "L")` answered `expected 5, got num`
   — reading as if `5` were a type — and made the message depend on that
   renderer's CAPS, which `self_eval.lang` cannot reach. An unnamed spec
   is anonymous and reads as `record`, which is what the guest already
   said. Decision 34's split does not apply one level down: a contract
   message's wording IS a contract, because the guest was written to
   reproduce it, and the guest-differential oracle's oldest exemption
   (miss REASONS, round 17) is exactly what hid 256 divergences in it.
   The corollary that cost the most: **delegating a builtin to the host is
   parity only where the host's message does not depend on the SHAPE of an
   argument the guest boxed** — `push`'s v0.22 order hint disappears
   because a guest list holds boxes and a box is a record.
36. **A reason string is a contract, over the WHOLE miss surface (v0.28,
   round 372).** Decision 35 settled that for CONTRACT messages; v0.28
   states it for every miss: a message names the kind that actually
   stopped the computation, not one that plausibly might have, and
   `examples/self_eval.lang` produces the same sentence except where an
   enumerated exemption says it cannot. `==` used to answer `cannot
   compare functions with ==` for `why 1 == 1`, a program containing no
   function, because `deep_eq` returns `None` for four opaque payload
   kinds and `binop` collapsed them into one sentence. The guest's mirror
   defect is structural rather than a typo: a guest list holds boxes, so
   the host worded a delegated miss around a box instead of the value —
   fixed by re-delegating with deep-stripped arguments ON THE MISS PATH
   ONLY, which costs nothing when nothing missed. See § v0.28 for the
   three surviving exemptions, each asserted load-bearing by a test.
37. **The rendering a message is built from is part of the language, and a
   differential must be keyed by the OPERAND (v0.29, round 374).** Two
   halves of one finding. (a) Every miss message renders its operands with
   `show_payload` — one line, bounded — and until v0.29 a Whence program
   could only obtain `full_show`, via `str`. So any program that had to
   build a message the way the interpreter builds one had to
   RE-IMPLEMENT the bounded renderer, and `examples/self_eval.lang` had two
   copies of it that had drifted. `show(v)` is now a builtin, and the guest
   delegates instead of approximating. (b) Decision 36 was verified by a
   corpus keyed by MISS SITE, which bounds the host side and only samples
   the guest side; an 11 326-case cross product of operand SHAPES against
   every operator, index, field, call form and builtin slot found 54
   divergences no exemption covered, every one of them a v0.28 fix applied
   at the site its cover reached with the operand its cover used. A
   coverage criterion drawn from the implementation's structure produces a
   FIX with the same structure. See § v0.29, and the fourth exemption it
   opened.
38. **A query about a history must be answered from THAT history, and
   where the answer needs a fact the language cannot express, the answer
   says so (v0.30, round 378).** `steps`/`at`/`blame` are the language's
   provenance-as-data family, and in `examples/self_eval.lang` they were
   answered by handing the guest's PAYLOAD to the host builtin of the same
   name — which returns the payload's host provenance, i.e. the
   *evaluator's* execution, not the program's. `len(steps(1 + 2))` was 4
   on the host and 284 in the guest, 280 of those being self_eval.lang's
   own line numbers, locals and internal probe misses. The evaluator was
   never missing the data: the `@{v, op, ins}` box graph `why`/`reify`
   already walk IS the guest's history. v0.30 answers the three from it.
   The part that is a design decision rather than a repair is what to do
   about the one fact the guest cannot get: **`walk_steps` dedups shared
   nodes by object identity and Whence has only structural `==`.** Adding
   an identity predicate was rejected — it would make the evaluator's own
   sharing (shared literal nodes, `MergedProv` runs, any future
   hash-consing) observable from Whence source and therefore frozen; a
   language about transparency of DERIVATION should not buy it with
   transparency of ALLOCATION. Deduping structurally was rejected as the
   opposite error (it merges distinct-but-equal steps). So the guest walks
   each shared node once per PATH: its count is an UPPER bound on the
   host's, never a lower one, which also makes the walk exponential in a
   shared history's depth — so it carries a budget and, over it, MISSES
   and names the number rather than returning a short list. A silently
   truncated history is the one failure here that would look like an
   answer. See § v0.30.
39. **A stated reason for not doing something is a claim with a price, and
   so is a test that proves a property by searching for a string (v0.31,
   round 380).** Two of this program's own artifacts failed the same way in
   the same round. (a) v0.30 deferred `diverge`/`contrast` — E4's remainder
   — on the reasoning that `diverge` "decides sameness by `na is nb` and
   memoises on `(id(na), id(nb))`" and `render_contrast` "column-aligns two
   rendered histories", "neither a rule a Whence expression can state".
   Priced separately, `na is nb` turned out to be a pure OPTIMISATION (a
   node compared with itself is structurally identical by definition), the
   memo load-bearing only for MULTIPLICITY (so the guest reports an origin
   once per PATH — the same upper-bound relation decision 38 already
   accepted), and column alignment to be `s + spaces(w - len(s))`. All five
   members of the provenance family now answer from the guest's own
   history and **exemption E4 is retired**. (b) v0.30 proved that "a miss
   node's detail IS its reason" by asserting `"detail=" not in interp.py`.
   `mk_miss`'s signature is `(reason, line, op, detail="", inputs=())` and
   **21 of its 87 call sites pass a detail POSITIONALLY**. The grep was
   true; the property was false; and the guest answered `unbound name
   'nosuch'` where the host answered `nosuch`. The rule this mints is not
   "check your greps": it is that **a proxy is only admissible as evidence
   when something has compared it against the thing it stands for**, which
   is exactly why the same round's budget sizing validated its own
   path-count proxy against the real guest walk before quoting it. See
   § v0.31.
40. **An unobserved miss is the one thing this language cannot explain, so
   the run reports it (v0.32, round 384).** Decision 2 promises a failure
   "can tell you *why*", and it can — to a name, a `check`, an operand, a
   `print`. It cannot to nobody. A miss that is the value of an expression
   statement is discarded: no name, no consumer, and when the run ends
   nothing is left to ask it anything. Whence said nothing at all about
   those until v0.32, and three of the four machine-written field programs
   that run were silently wrong because of it — one of them throwing away,
   unrendered, the exact cure v0.22 had written for its bug thirty rounds
   earlier. `print(x)` is observation, not a drop: the tracked corpus
   reported four drops on the recorder's first run and all four were
   `print(<a miss>)` in an example whose subject IS that miss. The report is
   unconditional; the exit code is not (`--strict-miss`). See § v0.32.
41. **`unbound name 'x'` names the cure from a table with an entry rule, not
   from edit distance (v0.32, round 384).** Decision 32's rule applied to
   the language's most common runtime miss. A name enters `_FOREIGN_NAMES`
   only if a frozen census of the field corpus attests it or a numbered
   decision here rejects the construct it names, and the sentence must say
   what to write in Whence instead. A nearest-builtin rule was built first
   and deleted: the field corpus contains no typo of a builtin, only
   foreign idioms; 54.8 % of example programs bind two names within edit
   distance 2 of each other, because a single-assignment language names a
   SERIES rather than reassigning one variable; 18 of the 666 builtin pairs
   are that close to each other; and the guest would have had to
   re-implement Levenshtein to keep wording the message the same way. A
   hint needing four tuning constants to stop lying is not a hint. See
   § v0.32.
42. **The parser reads decision 41's table, and there is only one table
   (v0.33, round 386).** Decision 32 has had two halves since v0.22 — a
   builtin-argument half in `interp.py` and a parse-error half in
   `parser.py` — and decision 41 gave the first of them a table of foreign
   idioms. The second half could not reach it: `interp.py` imports
   `parser.py`, so a table living in the interpreter is invisible to the
   parser, and a program that does not PARSE never reaches a runtime
   unbound name at all. The result was that Whence knew "Whence has no
   loops; iterate with `map`/`filter`/`fold` or recursion" and answered
   `for d in xs` with "two names in a row … a call is `f(x)` and text must
   be quoted" — advice that is wrong in both of its branches. The table
   moved to `whence/foreign.py`; `interp._FOREIGN_NAMES` is an ALIAS, not
   a copy, because the second copy of a literal is where drift starts.
   Three constraints, each measured rather than assumed: the clause is
   silent about any name the FILE BINDS (`meta.lang` and `self_eval.lang`
   both write `let then = …`, since an interpreter written in Whence names
   an if-node's then-branch `then`); it explains an error only when the
   foreign word is what put two names next to each other, never when it
   merely happens to be one of them (an earlier draft made `safe_divide
   one_hundred, …` report "Whence has no spelled-out numbers", shadowing
   the one message that described the actual mistake); and in `miss`
   position the miss-reason clause replaces the foreign one, because
   "Whence has no null; a missing value is `miss <reason>`" on `miss null`
   is advice to write what the author is already writing. See § v0.33.

## Syntax (statements are newline-separated; `#` comments)
```
let x = 12                        fn add(a, b) { a + b }
check "adds": add(x, 3) == 15     print(why add(x, 3))
let v = num("3O") rescue 0        # rescue: use 0 if miss
let r = @{name: "Ada", age: 36}   # record; r.name, merge(r1, r2), keys(r)
let xs = [1, 2, 3]                # xs[0], len, map, filter, fold, push, range
let y = if x > 5 { "big" } else { "small" }
let f = fn(a) { a * 2 }           # anonymous fn; blocks end with an expression
check "long":                     # newline after ':' / an operator / and / or /
  x > 5 and                       #   rescue continues the line (v0.2)
  x < 20
```
Precedence (low→high): `rescue`, `or`, `and`, `not`, comparisons (non-chaining),
`+ -`, `* / %`, unary (`-`, `why`, `snip`, `miss <string>`), calls/index/field.
`if` requires `else`; blocks/fn bodies must end with an expression. Newlines are
statement separators except inside `( ) [ ] @{ }` and directly after a token
that cannot end a statement. Since v0.23 a newline is the ONLY separator and
it is REQUIRED between two statements — `let a = 1 let b = 2` is a parse
error, not two statements.
Names are `[A-Za-z_][A-Za-z0-9_]*` and numeric literals are ASCII digits
(v0.21); strings and comments hold any character. String escapes are `\n`,
`\t`, `\r`, `\"` and `\\` — any other escape is a lex error.

## Semantics notes
- Numbers are ints/floats; `/` is float division; `+` also concatenates strings
  and lists. Mixed-type arithmetic → miss.
- Element access (`xs[i]`, `r.f`) passes the element's provenance through
  unchanged: access does not launder history.
- `let` and `fn` wrap provenance in a `let <name>` node; calls wrap in a
  `call <name>` node (one per tail loop, see 8); `if` results record both
  the branch and the condition's provenance (so "why this result" includes
  "why this branch was taken"). `fold` (v0.3) adds a `fold <n> items` node
  whose inputs are the final accumulator and the list.
- Binop over misses merges reason lists (deduped, order kept). Builtins with
  a miss argument propagate it *before* looking at the argument — so a `fold`
  seeded with a miss is a miss regardless of the list.
- `print(x)` writes a rendering and *returns x* (pass-through — chainable).
- `str(why x)` renders the tree (depth ≤10, ≤200 nodes) as a string.

## Provenance as data (v0.2)
- **Step record**: `@{op, detail, line, show, depth, inputs, count, value}`
  where `value` is the historic value with that step as its provenance (so
  `why s.value` / `at(s.value, …)` keep working), `inputs` is a count and
  `count` (v0.3) is the number of frames a merged tail-call node stands for.
- `steps(x)` — all steps, root first, depth-first, each shared node once.
  Accepts a value or `why value`. Uncapped; `snip` is the pressure valve.
  `steps(x, name)` (v0.3) keeps only the steps whose label, op or detail
  equals `name` (same matching as `at`).
- `at(x, name)` — breadth-first from the root (most recent history first),
  the first step whose label (`"let a"`, `"note year 1"`, `"call grow"`),
  op (`"call"`) or detail (`"year 1"`) equals `name`. Miss if none.
- `blame(x)` — step records of every origin miss reachable from `x`
  (miss-valued nodes none of whose inputs is a miss). Empty list for a
  healthy value. `at(blame(x)[0].value, "literal")` reaches the bad input.
- `diverge(a, b)` (v0.3) — list of `@{kind, a, b}` records, `a`/`b` being
  step records of the paired steps; innermost origins first. Empty when the
  histories agree step for step. Accepts values or `why` values; works on
  misses (two failures diverge at the inputs that made them differ).
- **Cost:** every step keeps its value, so a history keeps every
  intermediate value alive — but intermediates *share* storage (decision 9):
  20k pushes in a fold retain everything in 28MB / 0.14s (v0.2: 568MB /
  6s). A tail loop retains ~770 bytes per iteration (v0.4; v0.3: ~1.3KB):
  the five nodes that are genuinely new facts about that iteration (`==`,
  `-`, `+`, `arg i`, `arg acc`) plus one pointer in the merged `if`. 1M
  iterations: 9s / 840MB (v0.3: 48s / 1.35GB). `snip` remains the
  pressure valve.
- **Speed (v0.4):** ~5–6µs per tail-loop iteration (v0.3: ~17µs) with the
  fast path; CPython's cyclic GC adds ~50% on long runs because it rescans
  the growing history, so `run.py` raises the gen-0 threshold for the
  duration of a run (`Interpreter(gc_relief=True)`; library default off).
- **Snapshots are lazy (v0.3):** a step's `show` string is rendered on first
  use, not at creation (eager snapshots were 2/3 of evaluation time).

- `contrast(a, b)` (v0.4) — a string: for each origin, the lockstep path
  from the two roots down to it, `a` left, `b` right, origin marked `▶`;
  `"no divergence"` when the histories agree.
- `at`/`steps` name matching (v0.4): a merged mutual-recursion node
  `call even/odd` also answers to `"call even"`, `"call odd"`, `"even"`.

## Records as data / self-hosting (v0.5, round 014)
- `get(r, name)` — dynamic field access with exactly `.field` semantics:
  same pass-through (no new node), same miss wordings for absent fields /
  non-records; a non-string `name` is its own miss. `get(r, "a")` and `r.a`
  are indistinguishable, node for node.
- `put(r, name, v)` — a new record with field `name` set to `v` (add or
  replace); the original is unchanged. Equivalent to `merge(r, @{name: v})`
  with a dynamic key; provenance node `put <name>` with inputs `(r, v)`.
  `v` may be a miss (records hold misses); only `r` and the key propagate.
- `find(fn, xs)` — the first element of `xs` for which `fn` returns `true`,
  passed through like `xs[i]` (access does not launder history). No match /
  empty list is a miss `find: no element matched`; a predicate miss or
  non-bool is a miss like `filter`'s.
- These exist because a metacircular evaluator needs an environment keyed
  by names it only knows at runtime. **Self-hosting round 4**
  (`examples/self_eval.lang`): a full Whence evaluator written in Whence —
  source → tokens → AST → value one level down. The host's mutable
  environments are modeled by store-passing (`eval(node, env, st) →
  @{v, st}`; a closure captures frame IDs, the store is an immutable record
  threaded through evaluation), which reproduces the host's call-time late
  binding exactly: `fn a() { b() }  fn b() { 1 }  a()` is 1, and calling
  `a()` *before* `b`'s definition has executed is an unbound-name miss.
  Guest values are host values, so host operator semantics (strictness,
  propagation, overflow) hold one level down, and a guest failure's blame
  trail reaches through both levels. Differentially tested against the host
  on a 50-program corpus (`tests/test_self_eval.py`); payloads must agree,
  miss *wordings* may differ (arity/callable messages), `==` on records
  containing closures compares structurally in the guest, and a guest
  record with a `__tag` field can spoof a callable (open-record leak).
- **Self-hosting round 6 (round 192)** ran the guest evaluator ON the guest
  lexer/parser's own real source for the first time — not a hand-picked
  corpus snippet, `self_host.lang`'s actual ~680-line file, feeding
  `self_eval.lang`'s `run_src` two full levels of tree-walking
  interpretation deep. This found a real bug the fuzzer had 20+ rounds to
  catch and never did: `self_host.lang`'s hand-copied `suppressed()`
  newline-continuation check only implemented HALF of `whence/lexer.py`'s
  rule (bracket depth), missing the other half — a newline right after a
  token that "cannot end a statement" (an operator, `=`, `:`, `,`, or
  `and`/`or`/`not`/`rescue`) is ALSO a continuation, independent of
  brackets. `self_host.lang`'s own multi-line `check "label":\n  expr`
  style (and `effects.lang`'s, see below) round-trips fine under the HOST
  but was an unconditional `parse_error` under the GUEST — invisible to
  every fuzz run because the fuzzer's printer never emits a bare trailing
  operator/colon/keyword followed by a real newline. Fixed with a
  `last_continues(acc)` helper (checks the last emitted token's `t`/`v`
  against a `continue_ops`/`continue_kws` list) OR'd into `suppressed`,
  mirrored byte-identically in both `self_host.lang` and `self_eval.lang`'s
  shared parser section (`test_parser_section_matches_self_host` pins the
  line range, now 27..561). Confirmed at both levels: the guest parser
  called directly on the full source (`tests/test_self_hosting.py::
  test_guest_parser_parses_its_own_full_source`, pins 154 top-level
  statements) and the guest EVALUATOR interpreting the parser as guest
  closures (`test_guest_evaluator_executes_self_host_library`). As a side
  effect this also closes round 164's old backlog item — `effects.lang`'s
  own `check "...":\n  expr` line was the exact same bug, and now parses
  and evaluates cleanly under the guest (`test_effects_lang_runs_under_the_
  guest_round_164_backlog_closed`). A full run of `self_host.lang`'s ENTIRE
  66-check test section through `run_src` (guest-evaluating the guest's own
  full test suite, not just its library) was attempted and abandoned: RSS
  passed 1.7 GB and was still climbing after 3 minutes on this machine's
  3.8 GB budget — a first real data point on how guest-level tree-walking
  cost compounds on a non-synthetic program, not pursued further this
  round.
- **Self-hosting round 7 (round 200)** turned that single data point into a
  curve and a root cause, safely: each probe runs in a fresh subprocess with
  `resource.setrlimit(RLIMIT_AS, cap)` set before any Whence code runs
  (`bench/self_host_memscale.py`), so a runaway hits a clean, immediate
  Python `MemoryError` inside that one subprocess — enforced by the kernel
  at allocation time, independent of what else is running — instead of
  risking the kernel OOM-killer picking an unrelated victim on a
  memory-tight box shared with live trading services (round 198's stated
  reason for not attempting this live). Growing `self_host.lang`'s own
  66-check test section one checkpoint at a time through `run_src`: 5
  checks 112 MB, 10 → 113 MB, 15 → 126 MB, 20 → 198 MB, 25 → 259 MB, 30 →
  366 MB, 31 → **738 MB** — one added statement (a `parse_whence` call on a
  three-branch if/else program) roughly doubled peak RSS. Root cause,
  confirmed by reading the interpreter, not guessed: the guest store is a
  Whence record threaded through every step (see above), and `put`
  (`whence/interp.py` `b_put`) does `fields = dict(r.payload.fields)` — a
  full shallow copy of the CURRENT store on every single update, no
  structural sharing (unlike lists, v0.6). Worse, every `derived(...)`
  result keeps its `inputs` — including the prior, now-superseded store
  copy — alive forever via the provenance graph (`why`/`steps` must be able
  to trace back through it, by design), so old copies are never collected.
  N sequential `put`s each costing O(current store size) is quadratic
  cumulative cost by construction; a guest program with many top-level
  statements (`self_host.lang`'s test section, not the library, is exactly
  this shape — one `put` per statement onto an ever-growing store) is the
  worst case. This is a quantified explanation for round 192's "1.7 GB and
  still climbing," not a new bug — the store-copying cost was already named
  as `self_eval.lang`'s bottleneck as far back as round 010's summary, just
  never measured. A fix (structural sharing for records, e.g. a persistent
  map) is a real but nontrivial interpreter change with no current
  curriculum driver; flagged as optional future backlog, not attempted this
  round. **Built round 204 — see "v0.16" below**: `Record` is now backed by
  `PMap`, a persistent AVL tree, closing this gap.

## v0.6 (round 020)
- `has(r, name)` — presence, not readability: `true` when the field exists
  even if its *value* is a miss (`get` would pass that miss through),
  `false` only when the name is absent. The O(1) form of
  `contains(keys(r), name)`; a self-hosted evaluator asks it once per
  variable reference. Non-record / non-string-name are misses; argument
  misses propagate. Node `has <name>`, inputs `(r, name)`.
- `contrast([r0, r1, …])` — n-way: each run rendered against run 0, one
  block per *diverging* run (`run 2 vs run 0:` …); agreeing runs are
  skipped; `"no divergence"` when every run agrees or there are <2 runs.
- **Failing `==` checks auto-contrast.** A `check` that fails on a direct
  `==` records `contrast(left, right)` in its report; `run.py` prints it
  under `where the two sides diverge:`. Only `==`: a failing `!=` means
  the sides agree. A miss-valued comparison gets no contrast (the miss
  explanation already blames the origin).
- **String fast path:** `== != < <= > >=` and `+` on two strings skip the
  structural-equality machinery; node shapes are unchanged. `str % str`
  stays a miss (the host's `%` would silently *format*).
- **Calls got cheaper, invisibly:** a `Call` whose callee and arguments are
  all call-free compiles them once and skips its evaluator generator; a
  plain (non-higher-order) builtin call runs with no trampoline frame at
  all. `fast=False` still forces the generator path — the two paths are
  differentially tested.
- **Slimmer nodes:** `count` is a class attribute (1) on ordinary nodes and
  a real slot only on merged `call ×N` / `if ×N` nodes (`MergedProv`); a
  single input is stored unboxed (no 1-element tuple) and re-wrapped on
  read. Tail-loop retention 772 → 636 B/iteration, lossless.

## v0.7 (round 024)
- **Builtin calls compile (F1):** a direct call to a builtin name that is
  never shadowed anywhere in the program — and whose builtin does not
  re-enter guest code (`map`/`filter`/`fold`/`find` are excluded) —
  compiles inline, so the *enclosing* expression compiles too. The
  compiled call still resolves the name at runtime and verifies it is that
  exact builtin; any shadowing (including one introduced by a later
  `exec_stmt` in embedding code) falls back to full dynamic call
  semantics. Node shapes are unchanged.
- **Frameless closure calls (F2):** a non-tail call to a function whose
  whole body compiled (which F1 makes common: bodies that only call plain
  builtins) runs without a trampoline frame — same `call` node, same
  `arg` nodes, same arity/depth misses, same `peak_depth`.
- **Deferred `if` decisions are never dropped:** in v0.4–v0.6, a
  tail-position `if` whose taken branch tail-called a builtin (or a
  non-callable, or a miss) lost its `if` node when the tail loop ended
  after a single frame. The decision is now re-wrapped innermost-first, so
  the history reads `call → if → result` exactly like the compiled path.
  (Found by the v0.7 fast/slow differential; the whole 430-test suite had
  never pinned the lossy shape.)

## v0.8 (round 026)
- **Else-if chains walk inline (F3):** when an `if`'s taken branch is
  itself an `if` whose condition compiled fast — the shape of every
  interpreter's kind dispatch — the driver walks the whole chain in one
  step instead of pushing one generator per level. The walked decisions
  are wrapped innermost-out (or handed to the tail loop innermost-first),
  so histories are node-for-node identical to the nested path. A single
  `if` (no chain) takes the same straight-line path as before.
- **Statements run inline in blocks (F3b):** `let`/`check`/`fn` statements
  inside a block no longer push a per-statement generator; the block's own
  generator executes them directly. Same `let` nodes, same check records.

## v0.9 (round 030)
- **Direct mode: calls run by host recursion under a frame budget.**
  v0.4–v0.8 compiled only *call-free* subtrees; every subtree with a call
  in it — and every non-tail closure call — went through the generator
  trampoline (three generators and ~8 `send`s per `fib` call). Now every
  subtree compiles (`compile_direct`, cached in `node.direct` next to
  `node.fast`), calls included: a call node evaluates its callee and
  arguments and calls `_call_direct`, which is `_call_gen` without the
  generator — same arity / depth / tail-loop-too-long misses byte for
  byte, same `arg` / `call` / merged `call f ×N` / `if ×N` nodes (the
  bookkeeping is shared code), same `depth` / `peak_depth` / `tail_calls`.
  Tail calls still hand a pending `_TailCall` back to the enclosing loop,
  so tail loops stay frameless and merge exactly as before.
- **The budget.** Each top-level statement measures the host headroom:
  `sys.getrecursionlimit() − frames already on the stack − 350` (reserve
  for transient fast-closure recursion, one trampoline fallback and
  rendering). Every direct entry charges the frames it can use before the
  next `_call_direct`: `node.cdepth`, the number of direct-closure frames
  on the deepest path from the node to a call (a one-expression block is
  unwrapped and charges nothing), plus one for `_call_direct` itself. The
  charge is exact — `count`-shaped recursion measures 4.00 host frames per
  guest level and is charged 4. A call whose body does not fit (or is
  taller than `FAST_MAX_DEPTH`) runs on the trampoline through a nested
  driver, and inside it nothing goes direct until the budget is back, so
  host depth is bounded whatever the program does: a 15000-deep `count`
  under the default limit of 1000 runs direct for ~150 levels and
  trampolined for the rest (`direct_fallbacks` counts these); with the
  budget faked to infinity the same program raises RecursionError (a test
  proves the guard is load-bearing). Under `sys.setrecursionlimit(200)`
  the budget is negative and direct mode is simply dormant. Mutual
  recursion switching to a taller body mid tail loop re-charges the
  difference or runs that body on the trampoline. `run.py` raises the
  limit to 6000 (the CLI owns the main thread's 8 MB stack; plain closures
  recurse 30000 deep here); the library never touches the limit.
- **Three-way differential.** `Interpreter(direct=False)` is the v0.8
  evaluator (fast path on, every call on the trampoline); `fast=False`
  implies `direct=False`. The suite pins `render_why` byte-equality, output,
  check records and depth counters across direct / fast-only / slow on a
  corpus of call shapes, and the fuzz oracles gained a `direct` leg.
- **Bug found by the third leg (fast=False vs the rest, pre-existing since
  v0.7):** a multi-frame tail loop whose *final* iteration tail-called a
  builtin (`push(acc, eof)` in self_host.lang's lexer) merged that
  iteration's `if` into the loop's `if ×N` runs on the trampoline but
  wrapped the result with it on the compiled path (F1 inlines the builtin
  call) — one extra `if ×1` input in `fast=False`. v0.7 had reconciled the
  single-frame case only. Decided shape, every mode: a tail call that
  resolves to a builtin / non-callable / miss ends the loop as an ordinary
  call and the decisions of that final iteration wrap its result.
- **Counters:** `direct_hits` (direct entries + direct closure calls),
  `direct_fallbacks` (calls the budget sent to the trampoline),
  `host_budget()` (frames still available; ≤0 = dormant). `fast_hits`
  counts driver-level entries into any compiled closure.
- **Determinism:** direct closures are cached on shared AST nodes, so a
  call node resolves the interpreter acting NOW from the env chain (call
  envs and globals carry it) — and `check` statements inside compiled
  blocks now record on that interpreter too (a latent v0.4 hole).
- **Numbers (idle machine, fresh process, min of 3):** fib(20) 5.83 →
  3.72 µs/call (1.58×), meta.lang 5.16 → 4.17 s (−19 %), tail loop 6.66
  → 5.64 µs/iter, self_eval.lang −13 % (281 budget fallbacks: the guest's
  recursion outruns a 646-frame budget), generator sends in meta.lang
  1.10 M → 807, retention 634 B/iter unchanged.

## v0.10 (round 108)
- **The value-model floor.** The number of provenance nodes a program
  builds is fixed by the semantics (one per operation, argument, binding,
  decision, call: 2.77 M for one meta.lang run), so v0.10 removes the
  Python frames AROUND each node instead of the nodes:
  - `Prov.__init__` is a raw slot store. Its `ins` argument is stored as
    given — a tuple of input nodes, or ONE node unboxed (the v0.6 layout;
    a 1-tuple is accepted and simply not unboxed). Normalisation (lists,
    unboxing) lives in `derived` / `leaf` / `mk_miss` / `merge_miss`; the
    hot paths build `Prov(...)` directly. `MergedProv.__init__` is one
    frame, not a delegation.
  - Every binary operator compiles to its own closure with the numeric
    case inline (exact type test — `bool` excluded — the native operator,
    one node); `==`, `!=`, `+` and the orderings take the string case
    inline too. Every other case (misses, lists, mixed kinds, zero
    divisors, int-meets-float overflow) is decided by `binop`, so a miss
    has exactly one wording wherever it is produced.
  - Field access and list indexing compile to closures that return the
    pass-through element directly (present field of a record; in-range
    integer index of a list); every other case goes to the shared helper.
  - The `if` guard is `c is True` / `c is False`; only a non-boolean pays
    the `_if_bad` frame that builds the miss.
  - A run of ONE merged decision in a tail loop is a plain `if` node whose
    single input is the condition — the shape `MergedProv(count=1)` had,
    minus the second class and two lists. Runs of ≥ 2 decisions remain
    `MergedProv`. 99.99 % of the runs in meta.lang and self_host.lang are
    one decision long (a loop through an else-if chain alternates between
    `if` nodes, and only CONSECUTIVE identical decisions merge). Nothing
    renders differently: `×N` appears for `count > 1` only.
  - `Env(parent, interp)` takes the acting interpreter positionally.
- **Bug found by the reference differential (pre-existing since v0.9):
  comprehensions are frames.** `cdepth` charged one host frame per
  direct closure, but the list literal closure, the call-argument
  evaluation and the builtin-argument evaluation used list
  comprehensions — a real frame each in CPython < 3.12 — so every level
  of `fn nest(n) { if n == 0 { [] } else { [nest(n - 1)] } }` used 5
  frames and was charged 4. Under the default limit (~160 direct levels)
  the 350-frame reserve absorbed the difference; at the CLI's limit of
  6000 (~1400 levels) `run.py` died with a RecursionError traceback on
  `nest(1500)` — the fuzzer's own deep-nesting template, never run at
  that limit by the oracle campaigns. v0.10 evaluates arguments and list
  items with list displays (one and two arguments) or explicit loops:
  no comprehension on the direct path, so the charge is exact by
  construction (measured 4.00 frames per level for the list, argument,
  three-argument and record-in-list shapes; pinned). `nest(3000)` at
  6000 now runs direct for ~1400 levels and trampolines the rest.
- **Reference differential.** `bench/ref_diff.py` runs every example under
  the working tree and under a reference copy of the package (git HEAD by
  default, extracted with `git show`) in every mode and compares output,
  check records, every top-level binding's `render_why`, and (with
  `--counters`) the evaluation counters; `--fuzz SEED -n N` does the
  same over the harness fuzzer's random programs at the CLI's recursion
  limit, reporting an exception under the new tree as a finding and one
  under the reference as a note. v0.9 → v0.10: 39/39 (example, mode)
  pairs identical, counters included; 769 random programs × 3 modes, 0
  differing (the reference raised on 5 direct-mode pairs, the tree on
  none). The three-way differential now also covers meta.lang and
  self_eval.lang (suite +16 s).
- **Numbers (idle machine, fresh process, min of 3, paired against v0.9
  on the same day):** meta.lang 3.35 → 2.49 s (−25.5 %; `direct=False`
  4.03 → 3.30 s, −18 %), fib(20) 4.18 → 2.99 µs/call (1.40×; trampoline
  mode 9.61 → 8.04), tail loop 4.74 → 3.96 µs/iter (−16.5 %),
  self_eval.lang −6.7 %, deep.lang −14 %, retention 634 B/iter unchanged;
  Python calls per meta.lang run 30.5 M → 17.5 M (−43 %).

## v0.11 (round 110)
- **The ceiling, measured before building.** Three experiments priced the
  frame-removal strategy that v0.4–v0.10 followed, before any of them was
  built: (1) fusing a `NameRef` or literal operand into the closure above
  it (no `f_name` / constant frame) saves 10–20 ns per operand — the env
  walk is the cost, the call is not — so the 2.28 M name and 0.78 M
  constant frames of a meta.lang run are worth 2–3 %; (2) a
  hand-transpiled `fib` body (all 15 closure frames of the body folded
  into ONE Python function, why-tree byte-identical) through the real
  `_call_direct` is **1.09×**; (3) `_call_direct` with every piece of
  bookkeeping ablated (no depth / peak / counters / try, cached entry,
  unrolled binding) is **1.14×**. `__slots__` on the interpreter (0.3 %
  of a call), static scope-hop hints (0.33 failed probes per lookup in
  meta.lang → ≤ 1.2 %) and `Env` as a dict subclass (walk slower,
  creation faster, net 0) were measured and declined. What remains is
  the value model: one six-slot node per operation, an `Env` and a dict
  per call, and the call bookkeeping. A transpiler would buy ≤ 10 %; the
  evaluator is within ~15 % of what a CPython closure compiler can do for
  this semantics.
- **What was built: the last of the call path.** A function body's
  direct-call entry `(evaluator, frames charged)` is cached on the body
  node (`Node.entry`, `_body_entry`): the fast closure at cost 1, the
  direct closure at `cdepth` + 1, or `False` when the body is too tall to
  compile (then every call of it falls back to the trampoline — as
  before, one lookup instead of four). One- and two-parameter bindings
  are unrolled (no `zip` iterator); `depth` and the frame budget are read
  once and stored back rather than read-modify-written. Trampoline-only
  interpreters never write the entry. Same misses, same nodes, same
  counters — pinned three-way over 0–4 parameter widths, misses as
  arguments, arity misses at every stage of a tail loop, and loops that
  switch between bodies of different widths and heights.
- **The frame-charge oracle** (`harness/swe/oracles.py::oracle_frames`,
  the sixth oracle of the fuzz campaign). Round 108's bug — a host frame
  per guest level that `cdepth` did not know about — was invisible at the
  default recursion limit because the 350-frame reserve absorbed ~160
  uncounted levels; it surfaced only at the CLI's limit. The oracle runs
  a program under `sys.setprofile`, tracking the host frames actually on
  the stack above `exec_stmt` minus the frames direct mode has charged
  against its budget; the maximum of that excess over the run is the
  transient the reserve exists for. It is bounded by construction
  (fast-closure recursion ≤ `FAST_MAX_DEPTH` levels, one nested drive and
  its helpers): measured over 264 fuzz programs and the examples, the
  examples reach ≤ 19 frames, most programs 5–20, the fuzzer's
  `1 + 1 + …` chains 98 and nested list literals 59 — all at guest depth
  0. An uncharged frame per level reaches 161 within 160 levels at the
  default limit (injected, pinned) and ~1400 at 6000, so the slack of
  140 (`FRAME_SLACK`) separates the two; `swe.oracles --limit` and
  `swe.fuzz --limit` run the campaigns at the CLI's limit.
- **`bench/reserve_probe.py`** finds, per program, the smallest
  `HOST_RESERVE` that still completes without a RecursionError at a given
  limit (binary search, fresh process per probe) over ten deep templates,
  the examples and fuzz programs — the reserve's true requirement,
  measured in the limit's own units (which count C-level recursion
  entries the profile hook does not). Measured: deep recursions with
  short bodies need 0–5 (the charge is exact; recursion through `fold`
  even overcharges and falls back early), a 95-term `+` chain in the
  base case of a non-tail recursion 93–94 (reached through a call, a
  list literal or a record field alike), 55-deep nesting 57 (the parser
  caps nesting at 60), a 39-level else-if chain 41, every example and
  fuzz program ≤ 5. The bound by construction is `FAST_MAX_DEPTH` + a
  nested drive ≈ 110, so **`HOST_RESERVE` is 250** (was 350, a guess):
  2.3× the bound, and 100 more frames of direct budget (+17 % at the
  default limit). `bench/minof.py` is the min-of-N fresh-process bench
  driver.
- **Numbers (idle, fresh process, min of 3, paired the same day, limit
  6000):** fib(20) 3.18 → 2.81 µs/call (−11.6 %; trampoline mode 9.50 →
  9.19), meta.lang 2.325 → 2.275 s (−2.2 %; `direct=False` 3.309 → 3.271),
  tail loop 3.81 → 3.71 µs/iter (−2.6 %), deep.lang 1.095 → 1.066 s,
  self_eval.lang 0.421 → 0.424 s (nothing: builtin-call bound), retention
  634 B/iter unchanged. Reference differential v0.9 → v0.11: 39/39
  (example, mode) pairs identical with counters.

## v0.12 (round 122) — structural types
- **A type annotation is erased at parse time, not evaluated at runtime.**
  `fn f(a: num, b: Point) { … }` desugars, in the parser, to one leading
  `let a = typed(a, "num", "parameter 'a' of f")` per annotated parameter,
  prepended to the body's statement list before it is returned — an
  ordinary `Let`/`Call`/`Str` AST, exactly what a Whence programmer could
  have written by hand. No new AST node, no interpreter change, and an
  untyped function's body is byte-identical to v0.11 (the whole existing
  corpus is the regression gate: 654 tests + `run.py` on every example,
  unchanged). A mismatch is an ordinary `miss` (decision 2): it
  propagates through the rest of the body via the SAME operator/builtin
  propagation every other bad input already uses, `rescue` recovers it,
  `blame` finds it. This is the whole feature's design: no new control
  flow, no new failure mode, no exception to the "errors are values"
  discipline — a type is just another thing a value can fail to be.
- **Tail position is unaffected.** The guard only PREPENDS statements to
  the body; `mark_tails` is called once, after prepending, and only ever
  looks at the block's LAST statement — the same node it would have
  found without any annotation. A recursive tail call through a typed
  parameter still merges into one frame (three-way differential +
  `peak_depth` pin in `tests/test_v12.py`). This was the one alternative
  design ruled out: wrapping the body in `if <types ok> {…} else {miss}`
  would have buried a genuine tail call under an `if`'s `then` branch —
  still tail-safe by `mark_tails`'s own rule (`if` branches stay
  candidates) — but a `-> Type` RETURN annotation has no such safe
  shape (checking a value AFTER the body runs inherently needs the
  result back, which costs tail position, decision 8) — so v0.12 ships
  parameter types only. **Stale-note correction (round 240): this used to
  say "a return annotation is future work, not started" — true when this
  section was written (round 122) but closed the very next version; see
  `## v0.13 (round 128/132) — return type annotations` below, which even
  has its own round-234 stale-note correction for a different paragraph.
  This is the same "prose describing a resolved question as still open"
  bug class rounds 230/234/236 already found and fixed elsewhere in this
  file/repo, just one section closer to the root this time — the very
  bullet that originally posed the question, not a later summary of it.**
- **Primitive tags:** `num str bool list record fn any` — `any` always
  matches (even so, a miss argument still propagates first: "any" is not
  "swallow errors", decision 2). `shapeof(x)` returns the tag Whence
  values report their true payload as, including `"miss"` — the same
  classification `typed` uses, exposed directly (and, in a self-hosted
  evaluator, a replacement for the hand-rolled `is_num`/`is_record`
  helpers `self_eval.lang` has needed since round 14).
- **`shape Name = @{field: type, …}` is sugar for `let Name = @{__shape:
  "Name", field: <spec>, …}`** — an ordinary record, bound by an
  ordinary `let`, so it inherits the parser's ALREADY-EXISTING duplicate-
  name rule for free (a `shape` reaches `stmt_list`'s bound-name check as
  an `A.Let`, indistinguishable from a hand-written one) and is itself a
  first-class value (`Point.__shape`, `matches(r, Point)`). A field's
  type is either a primitive tag (a string literal spec) or a
  PREVIOUSLY-DECLARED shape name (a `NameRef` to its own bound record —
  real value reuse, not a copy, so `shape Line = @{a: Point, b: Point}`
  shares the exact `Point` record both `a` and `b` are checked against).
  Shapes can only reference earlier shapes (the parser resolves a
  signature's spec immediately, single-pass, no forward refs — an
  `unknown type` parse error otherwise), so nested `matches` recursion
  is bounded by declaration order and cannot cycle. **Round 342 (v0.18)
  finished the sentence this bullet opens with:** "it inherits the
  parser's ALREADY-EXISTING duplicate-name rule for free" was true of
  DUPLICATES and false of SCOPE — a shape name was visible to annotations
  file-wide while its binding was block-scoped like any other `let`. Since
  v0.18 a field type (and any other annotation) must name a shape that is
  previously declared AND still in scope; see `## v0.18` below, including
  what that made legal as well as what it made an error.
- **Structural, not nominal: width subtyping.** A record matches a
  `shape` when every declared field is present with a non-miss value of
  the right (recursively checked) type; EXTRA fields are ignored. A
  record built entirely by hand, with no relation to the shape ever
  declared, matches it exactly as one built from it — real duck typing,
  by design, not the round-18 guest `__tag`-spoofing leak (that was a
  closure impersonating a callable via a magic field one level down in
  `self_eval.lang`; here a record honestly IS what its fields say it is,
  so matching structurally is simply correct, not a hole).
- **`typed(value, spec, label)`** — the builtin the guard calls: pass
  through the value UNCHANGED (no new provenance node, like `get`/
  index) when it matches; propagate an already-miss `value`/`spec`/
  `label` (decision 2's "misses propagate before inspection", same
  convention as `has`/`put`); otherwise a fresh miss `"<label> expected
  <spec-name>, got <shapeof value>"` whose `inputs` is `(value,)` — an
  ORIGIN miss (no input of its own is a miss), so `blame(result)` finds
  it directly and names the call that rejected the value. `matches(x,
  spec)` is the same check as a total predicate (never itself a miss,
  even on a miss `x`, like `missed`) for programs that want to branch on
  shape instead of failing on it.
- **Correction (round 335, SWE-loop D): the spec is now validated ALL THE
  WAY DOWN, and a non-string `__shape` no longer leaks a Python repr.**
  `_type_match`'s docstring always claimed "every other field maps to a
  nested spec — a str or … another Record" as an invariant, and it holds
  for a DECLARED shape (`parse_type` rejects `shape Bad = @{x: 5}` at
  parse time). But the width-subtyping bullet above is explicit that a
  hand-built record is a legal spec, and `typed`/`matches` only ever
  checked the TOP level of one — so `matches(@{a: 1}, @{a: 5})` recursed
  into `5`, reached `spec.fields` on an int, and raised `AttributeError`
  straight out of the interpreter: a "never raises" violation in a builtin
  whose own contract is "never itself a miss". Reachable from a parameter
  guard too, not only a literal call: `parse_type` checks only that the
  NAME was declared as a shape, so a `let` or a PARAMETER shadowing it
  makes an arbitrary runtime value the spec (`fn outer(Pt) { fn f(p: Pt)
  { p }  f(@{x: 1}) }`). Fixed with `_spec_ok`, a recursive validator both
  builtins now use in place of their one-level `isinstance` check —
  `matches` still answers `false` for a malformed spec (its documented
  "simply does not match"), `typed` still answers its own `"typed spec
  must be a type name or a shape"` miss, each now meaning what it said.
  Separately, `_type_match` rendered a spec's `__shape` field through
  `%s`: a hand-built `@{__shape: @{q: 1}, …}` put the payload's Python
  repr, heap address and all, into a user-visible miss message, so the
  same program produced a different message on every run and the
  determinism / fast_slow / direct oracles all fired on it. Non-strings
  now render through `show_payload`, like every other value the language
  shows. Both found by the totality sweep round 335 ran when
  `matches`/`shapeof`/`typed` finally joined `harness/swe/fuzz.py`'s
  `BUILTIN_ARITY` — the last three registered builtins the fuzzer could
  not reach (`tests/test_v12.py`, 14 new cases).
- **A parameter's own guard can be shadowed, and it is documented, not
  hidden:** `fn f(a: num) { let a = a  a }` still sees the checked value
  (the user's `let a = a` reads the ALREADY-guarded `a`, since the guard
  runs first and both bindings live in the same call env); `fn f(a: num)
  { let a = 5  a }` discards the check for `a` specifically because that
  rebind never reads the original `a` at all — the same as it would
  discard any other prior binding it does not reference. No special-
  casing needed or added; this is exactly what a leading `let` already
  means.
- **`fn` is parseable as a type tag** despite being a keyword everywhere
  else (`fn apply(f: fn, x: num) { f(x) }`): the annotation parser
  accepts the `fn` KEYWORD token as well as a NAME. **`shape` is a
  CONTEXTUAL keyword, not reserved:** only the exact prefix `NAME NAME
  "="` at the start of a statement (mirroring how `fn NAME` already
  disambiguates a named def from an anonymous `fn(...)` literal)
  triggers shape parsing; no other legal Whence statement starts with
  two bare names, so a program that binds something actually called
  `shape` is unaffected — no lexer change, no reservation.

## v0.13 (round 128/132) — return type annotations
- **`fn f(params) -> Type { body }` checks the function's RETURN value
  against `Type`, using the exact same contract `typed()`/a parameter
  guard already uses** — a primitive tag or a previously-declared `shape`,
  structural width subtyping, `any` always matches. Unlike a v0.12
  parameter guard (sugar: one leading `let` statement, re-evaluated every
  call), a return check cannot be sugar the same way — checking a value
  AFTER the body runs needs the settled result back, which costs tail
  position if done as a body-wrapping `if`. So a return type is NOT an
  AST rewrite: the parser stores the spec expression on `FnDef`/`FnExpr`
  (`ret_type`, an `A.Str` or `A.NameRef`, same shape a param spec is),
  resolved to a runtime `(spec, label)` pair ONCE per `Closure` at
  creation time (`_closure_ret`/`_mk_closure` — a choke point for every
  FnDef/FnExpr construction site: fast, direct, and all three generator-
  mode sites), and checked at the ONE point every call path already
  settles to a final `result` Prov before wrapping it in a `call` node
  (`_check_ret`, called from `_call_gen`'s merged-tail-chain exit,
  `_call_direct`, and the call-free-body fast path `_call_no_calls` —
  THREE sites; the third was missing entirely in an early draft and was
  the round-128 bug the three-way differential caught, see below).
- **An untyped function pays for exactly one identity check per call**
  (`ret_spec is None`) — no new provenance node, no guest-visible frame,
  same "no new control flow" discipline v0.12 used. A mismatch is an
  ordinary origin miss (decision 2), same wording/op/single-input shape
  `typed()` itself produces (`"typed"` op, `detail` = the label), so
  `blame`/`rescue` treat a bad return exactly like a bad parameter. A
  `result` that is ALREADY a miss is never re-wrapped — the function's
  own failure is not painted over with a second "wrong return type" gloss.
- **Tail position is exactly as `mark_tails` already computes it, with one
  subtlety: the check runs against the ORIGINALLY CALLED closure's own
  `ret_spec`, captured before a tail loop may reassign which closure `p`
  points to.** `a` tail-calling a differently-typed (or untyped) `b` must
  still check the merged chain's settled result against `a`'s own
  contract, exactly once, not once per bounce and not against whatever
  closure the chain happens to end in
  (`tests/test_v13.py::test_mutual_tail_call_checks_against_the_caller_not_the_callee`).
  A typed tail-recursive function costs nothing extra per bounce: the
  spec is resolved once at closure creation, and the check itself runs
  once, at exit, using `peak_depth 1` regardless of iteration count
  (20000-deep `count_down` tail loop: one check, `peak_depth == 1`).
  *(Cost caveat, round 336: "nothing extra per bounce" is no longer
  literally true — see the round-336 bullet below. `peak_depth 1` and
  "checked once, at exit" are unchanged.)*
- **Correction (round 335, SWE-loop D): the bullet above is right about
  the CALLER's contract and was silently wrong about the CALLEE's.**
  Capturing `ret_spec` before the tail loop reassigns `p` stops the check
  adopting whatever contract the chain ends in — good — but nothing then
  checked that closure's own contract at all. `fn f() -> num { "s" }`
  missed when called as `let q = f()` and returned the raw `"s"` when any
  other function called it in TAIL position, so whether a declared return
  type was enforced depended on the syntactic position of a call site in
  someone else's body. `test_mutual_tail_call_checks_against_the_caller_
  not_the_callee` only ever covered the mirror case (typed caller,
  UNTYPED callee), which is why ~200 rounds of three-way differentials
  never saw it. In a tail call the callee's result IS the caller's result,
  so every contract along the chain applies to that one settled value:
  `_note_chain_ret` records each DISTINCT `ret_spec` the loop enters and
  `_check_chain_rets` applies them after the originally-called closure's
  own, which still runs first (an already-missed result passes through
  `_check_ret` untouched, so every case that already worked keeps its
  exact wording and ordering, including the test above). The per-bounce
  cost claim is unchanged: a self-recursive typed tail loop bounces
  through the SAME closure, `p.ret_spec is ret_spec` holds, and no list is
  ever allocated (`tests/test_v13.py`, 12 new cases including three
  `assert_three_way`). *(Round 336 reversed the ordering claim in this
  bullet — "the caller's, which still runs first" and "every case that
  already worked keeps its exact wording and ordering" are both stale, as
  is the no-allocation claim for a typed self-recursive loop. Read the
  next bullet, not this one, for the current rule.)*
- **Correction to the correction (round 336, language C): the ORDER round
  335 chose was still tail-position-dependent, and it is now inside-out.**
  Round 335 fixed *whether* a tail-entered closure's contract runs and
  left *which one is blamed* depending on syntactic position: it applied
  the originally-called closure's contract first and the chain's in ENTRY
  order — outermost-first, the exact reverse of the same program with
  every call lifted out of tail position by a `let`. Its own next-steps
  item 4 flagged this as "a semantics decision worth a second opinion from
  language(C)". Three independent references all say innermost-first, and
  the language now follows them:
    1. the lifted program (decision 8's new transparency rule);
    2. non-tail recursion, which has behaved this way since v0.13
       (`test_non_tail_recursion_checks_every_frame_independently`): the
       innermost frame's own check fires first and the miss propagates;
    3. `examples/self_eval.lang`, Whence's own definition of Whence. The
       guest evaluator has NO tail-call merging, so `apply_closure`
       recurses into `eval(c.body, …)` and runs `check_ret` once per real
       frame — inside-out by construction. On five of seven probe chains
       the host blamed a different function than the guest did; the
       guest-differential oracle could not see it because miss WORDINGS
       are an explicit exemption of that oracle (round 17).
  `_check_chain_rets` now walks the recorded chain backwards BEFORE
  `_check_ret` applies the originally-called closure's own contract, and
  each entry carries the line of the TAIL CALL that entered it, so a
  chain miss points at the call that produced the bad value rather than
  at the outermost call site. `_note_chain_ret`'s spec-identity test
  became a pure optimisation rather than a semantic: a recurring spec is
  moved to the end of the list with its label and line refreshed (the
  innermost occurrence is the one that must be blamed), and round 335's
  `rs is ret_spec` skip — which silently handed a chain member's blame to
  the originally-called closure — is gone. Scale of the change:
  **1740 of 2325 tail/lifted chain pairs disagreed before, 0 after**
  (1128 of them in the miss text itself, the rest line-only); the mutual-
  recursion family went 96/150 → 0/150. All three evaluation modes shared
  the bug identically, which is why ~200 rounds of three-way differentials
  never saw it — `test_every_mode_agrees_on_three_hop_chains` passes on
  both the old and the new interpreter, deliberately, as the record of
  what that oracle cannot see. Cost: the untyped fast path
  (`p.ret_spec is None`) is untouched, and a typed self-recursive tail
  loop now allocates one 1-element list per call and refreshes its line
  per bounce instead of allocating nothing. Measured end to end at 40k
  iterations, interleaved across builds, the delta is below this host's
  noise floor — the UNTYPED control, whose code path is byte-identical
  between the two builds, itself varied 5.4% run to run, more than any
  typed or mutual delta.
- **A real crash bug, found by round-128's own exploratory testing (not
  the fuzzer, which does not generate type annotations yet):** a `->
  Shape` naming a shape declared inside ANOTHER function's body parses
  (the parser's `self.shapes` set is not scope-aware — a pre-existing
  v0.12 gap shared by parameter types), but is never bound in the `env`
  chain `_closure_ret` walks at closure-creation time. The naive
  `env.get(name).payload` raised `AttributeError` on the `None` a missing
  lookup returns — a real crash, violating the "never raises" discipline
  every other Whence error path upholds by construction. Parameter types
  don't have this crash because a param guard's spec is an ordinary
  `A.NameRef`, walked by the everyday evaluator, which already turns a
  missing name into a `miss` instead of raising; the return-type path had
  no such protection because it resolves the spec directly in Python, not
  through a Whence expression. Fixed with a `_UnboundRetType` sentinel:
  `_check_ret` turns it into an ordinary `"not in scope"` miss, deterministic
  across repeated calls, and it never leaks to Whence code as a Python
  exception.
  **Stale-note correction (round 342): "the parser's `self.shapes` set is
  not scope-aware", four lines up, is no longer true and is kept for
  history.** v0.18 gave the parser the value namespace's own scope rule
  (decision 28), so the program this bullet is about is now a parse error
  at the annotation, and `_UnboundRetType` is unreachable from source text
  — kept anyway as the defensive floor under `_closure_ret`'s direct
  Python lookup, and exercised directly by
  `test_unbound_ret_type_sentinel_is_still_the_defensive_floor`. See
  `## v0.18` below.
- **Three-way differential (fast / direct / trampoline) is the gate**,
  same as every call-path change since v0.9: byte-identical why-trees and
  checks across all three modes for a passing return, a mismatched
  return, a shape return, typed tail recursion, a mutual tail call, non-
  tail recursion (every frame checked independently, no double-wrapping),
  and the out-of-scope-shape crash case (`tests/test_v13.py`, 8
  `assert_three_way` cases + 39 unit/parser/interpreter cases, 47 total).
- **Stale-note correction (round 234):** this bullet used to say the
  fuzzer's program grammar did not generate `: Type`/`-> Type` annotations
  yet and called it a "standing backlog, not blocking." That was true when
  this section was first written (round 128/132) but was closed shortly
  after and this paragraph was never updated — round 134 (verified round
  144) added `TYPE_TAGS`/`typed_params()`/`maybe_ret_type()` to
  `harness/swe/fuzz.py`, wired into every generated `fn` (30%/param and
  25% chance respectively), so both param and return guards have been
  exercised by every fuzz/oracle campaign run since. The guest side closed
  later still: `harness/swe/guest.py`'s `GuestGen` overrode both hooks to
  a no-op until round 158 taught `self_eval.lang`/`self_host.lang`'s
  shared parser section to tokenize `: TAG`/`-> TAG` and gave the guest
  evaluator its own `typed` builtin + return-type check — `GuestGen` now
  inherits the real (non-no-op) grammar unchanged (see `guest.py`'s own
  `GuestGen` docstring for the two-round arc). What genuinely remains
  out of scope, by construction rather than oversight: `TYPE_TAGS` is
  primitive tags only (`num str bool list record fn any`), so no fuzzed
  program ever names a `shape` as a type spec on either the host or guest
  side (round 144/224's own SPEC notes on `typed`/`matches` guest parity,
  above and below, cover this same limit from the builtin-dispatch side).
  **Stale-note correction (round 338):** this bullet used to continue
  "— `self_eval.lang` still has no `shape` support at all". That was true
  when written and is now false — see "v0.12/v0.13 guest parity (round
  338)" at the end of this file, which added the `shape` statement to the
  shared guest parser and `-> Shape` resolution to the guest evaluator.
  `TYPE_TAGS` being primitives-only still stands, so the fuzzer still
  emits no shape; after round 338 that is a GENERATOR choice, not a guest
  limitation. No new
  example beyond extending `examples/shapes.lang` with a return-typed
  `midpoint`/`broken_midpoint` pair (4 new checks, 12 → 16) — a dedicated
  flagship example was judged unnecessary since the feature composes
  directly with v0.12's existing one and the design point (return checks
  are call-boundary checks like parameter checks) is best shown as an
  addition, not a separate story.

## v0.14 (round 146) — effect system
- **The curriculum's remaining "advanced feature" slot (after v0.12
  structural types and v0.13 return types) is an effect system, not
  AI-native primitives** — decided this round because the language
  already has an observable effect to make interesting (`print`, which
  writes to the host) and because a minimal design falls directly out of
  the v0.12/v0.13 precedent, unlike AI-native primitives, which have no
  settled scope yet. `fn f(params) effects [tag, ...] -> Type { body }` —
  an optional clause after the parameter list, fixed order (effects
  before `-> Type`; the other order is an ordinary out-of-order syntax
  error, "expected '{'"). Anonymous `fn(...) effects [...] { ... }` takes
  the same clause.
- **The whole check is resolved at PARSE time, with zero interpreter
  change** — no new AST field, no `Closure` slot, no runtime cost,
  unlike `: Type`/`-> Type` (v0.12/v0.13), which both check a RUNTIME
  value and therefore have to live in the interpreter. Whether a
  function's own body directly names an effectful builtin is a static
  property of the source text, decidable before the program ever runs —
  the same category of fact that already makes rebinding and "block must
  end in an expression" PARSE errors rather than misses. `_EFFECTFUL_
  BUILTINS = {"print": "io"}` (`parser.py`) is the one place a future
  effectful builtin (randomness, a clock, real I/O) would register its
  tag; nothing else would need to change.
- **Mechanism:** the parser keeps a stack of "the nearest enclosing fn's
  declared effect set" while parsing (`self.effects_stack`, pushed on
  entering any `fn`'s body — `None` for no clause, a `frozenset` for a
  declared one, possibly empty) and checks it at every direct call whose
  callee is literally a builtin name in the effect table
  (`Parser._check_effect_call`, called from `postfix()`'s call-parsing
  site). No clause anywhere in scope (including the module top level,
  which has no enclosing fn at all) means unrestricted — **every program
  written before this feature existed parses identically**, confirmed by
  the full pre-existing suite (779/779) and every `examples/*.lang` file
  running unchanged after the change landed.
- **`effects []` is the interesting case: "this function's own body may
  not directly call an effectful builtin."** Violating it is a
  `ParseError` naming the builtin, the required tag, and the declared
  set (`'print' requires effect 'io', not permitted by the enclosing
  function's 'effects [] (no effects declared)'`). `effects [io]` (or
  any set containing the tag) grants it; an unrelated tag like `effects
  [network]` does NOT grant `"io"` — the check is per-tag, not merely
  "was a clause present" (`test_effects_unrelated_tag_still_blocks_
  print`).
- **Deliberately SHALLOW, not merely incomplete — the same scoping
  discipline v0.13's return-type check already established (one settle
  point, not full call-graph composition):**
  - A declaration vouches ONLY for calls made directly, textually, in
    that function's own body. A nested `fn` defined inside a restricted
    body is a SEPARATE closure with its own (absent, hence unrestricted)
    declaration and may print freely, even lexically inside an `effects
    []` function (`test_nested_undeclared_fn_escapes_outer_purity`,
    `examples/effects.lang`'s `strict_sum`). Calling a DIFFERENT,
    unrestricted function that itself prints is likewise untouched by
    the caller's declaration.
  - Only a literal `name(...)` callee is inspected. `let p = print` then
    `p(1)` is invisible to the check inside an `effects []` function —
    the callee at that call site is the `NameRef` `p`, not `print`
    (`test_indirect_call_via_variable_is_not_checked`).
  - Both gaps are real, tested, and documented rather than hidden; a
    call-graph-aware (transitive) effect system that closes them is
    future work, not this round's scope (see research-state.md's
    language backlog).
- **Zero interpreter change means the three-way differential (fast /
  direct / trampoline) already agrees by construction** — pinned
  explicitly anyway with two `assert_three_way` cases
  (`tests/test_v14.py`), plus the full pre-existing fuzz/oracle/guest/
  ref_diff standing checks (round 146: two fresh fuzz seeds, two oracle
  seeds — one at `--limit 6000` — two guest seeds, `reserve_probe
  --examples -n 30`, `ref_diff` over every example) all ran clean or
  found nothing attributable to this change (`ref_diff` correctly
  reports `examples/effects.lang` as `NEWSYNTAX` against the pre-round
  reference tree, not a diff).
- **New example `examples/effects.lang`** (4 checks): a declared-pure
  `total`, an `effects [io]` `report` that legitimately prints, `effects
  [io] -> num` composing with a return type, and the honest
  `strict_sum` escape-hatch demonstration. No example demonstrates the
  REJECTED case (a `ParseError` aborts the whole file before any `check`
  can run, so a "this should fail" example can't coexist with passing
  checks in one file, unlike a v0.12/v0.13 type mismatch, which is a
  runtime `miss` that keeps the rest of the program running) — the
  rejection path is covered by `tests/test_v14.py` and
  `test_examples.py::test_effects_violation_exits_2` instead.

### v0.14 guest parity (round 164)
- **`examples/self_eval.lang`/`self_host.lang`'s shared parser section now
  recognizes and SKIPS `effects [name, ...]`** (`parse_effects_clause`/
  `skip_effect_names`, inserted between the param list and the optional
  `-> Type`, same fixed order as the host) — closes the PARSING half of
  the guest-parity gap round 162 flagged when it taught the fuzzer to
  generate the clause and had to no-op it for `GuestGen`
  (`harness/swe/guest.py`): before this round the guest choked with
  "unexpected token 'effects'" on any v0.14 program using the feature.
- **The guest does not ENFORCE the declaration.** The host's
  `_check_effect_call` is a parse-time check consulted from
  `self.effects_stack` at every call site the recursive descent visits;
  reproducing it on the guest would mean threading an extra "current
  effects scope" argument through the entire expression grammar (down to
  `parse_postfix_rest`, where a call is actually built) — a materially
  bigger change than return-type erasure was, which only ever touched the
  single point where a function's own param list meets its own body.
  Left as an explicit, documented divergence rather than built partway.
- **Verified safe for the fuzzer without full enforcement**: re-enabled
  `GuestGen.maybe_effects` to inherit the real generator (no longer a
  no-op) after confirming `harness/swe/guest.py`'s `BANNED` line-filter
  already strips every line containing `print` — the ONE effectful
  builtin that exists — from every program this generator emits, on
  both sides of the comparison, regardless of what any `effects [...]`
  clause says. A generated declaration is therefore always vacuously
  satisfied through this generator; there is no live code path by which
  the host's parse-time rejection and the guest's non-enforcement could
  disagree. 300-sample check: 70/300 generated programs now carry an
  `effects` clause (was 0/300 under the round-162 no-op); a 150-program
  guest-differential campaign (seed 900) came back 0 findings.
- **New finding, orthogonal to effects itself**: running
  `examples/effects.lang`'s real, unmodified source through `run_src`
  still reports `parse_error: true` — NOT because of the effects clause
  (isolated single-statement checks of every one of the file's four
  functions, including the `effects [io] -> num` composition and the
  nested nested-fn nested-`print` case, all parse and evaluate correctly
  on the guest), but because of its one stylistically multi-line
  statement, `check "...":\n  expr` (label and expression on separate
  lines). The guest lexer's newline-suppression is deliberately simpler
  than the host's by design (its own header comment: "Newlines are
  suppressed while the top of the stack is `(` `[` or `@{` — NOT inside
  plain `{` blocks") — it has no equivalent of `whence/lexer.py`'s
  `CONTINUES` set (a newline right after `:`/a binary operator/`=`/etc.
  is a continuation on the host, an ordinary statement separator on the
  guest). This was unreachable/untested before this round: `effects.lang`
  is the first real example file with a multi-line `check` that the guest
  has ever had a chance to attempt (every corpus program in
  `tests/test_self_eval.py::CORPUS` is single-line by convention).
  Confirmed by reflowing just that one `check` onto a single line: the
  file then parses and evaluates identically on both sides. Not fixed
  this round — it is a lexer-level design choice, not a two-line parser
  patch, and touches every multi-line-continuation position the host
  supports, not just `check`. Tracked as fresh backlog at the time; closed
  by round 192 (`test_effects_lang_runs_under_the_guest_round_164_
  backlog_closed`, confirmed still closed by round 230's re-check) —
  this paragraph previously read "tracked as fresh backlog" past that
  fix, corrected here (round 264).

## v0.14.1 (round 264) — effect system: nested fns inherit lexically
- **Closes the first of v0.14's two documented "deliberately SHALLOW"
  gaps** (see the two bullets above): "a nested `fn` defined inside a
  restricted body is a separate closure with its own (absent, hence
  unrestricted) declaration" — a clause-less nested fn could print freely
  even lexically inside an `effects []` function, an escape hatch v0.14
  called out and `examples/effects.lang`'s `strict_sum` demonstrated on
  purpose. Closed by making a fn with NO clause of its own **inherit its
  nearest enclosing fn's already-resolved effect scope** instead of
  defaulting to unrestricted — pure lexical scoping, not a call-graph
  analysis.
- **Mechanism:** `Parser._resolve_effects_scope(own_spec)` — `own_spec`
  (the fn's own `parse_effects_clause()` result, `None` if absent) wins
  if not `None`; otherwise the CURRENT top of `self.effects_stack` is
  reused. Both push sites (`fn name(...)` statements and anonymous
  `fn(...) {...}` expressions) call this before pushing, so `_check_
  effect_call` itself needed no change — `effects_stack[-1]` is already
  the fn's fully resolved scope by the time any call inside its body is
  checked. Because inheritance only ever reads an ALREADY-pushed frame,
  a top-level fn (`effects_stack` empty) with no clause still resolves to
  `None` (unrestricted) exactly as before — no behavior change for any
  program that never nests an `effects`-relevant fn.
- **An explicit clause on the nested fn still always overrides the
  inherited scope, in either direction** — narrower, broader, or
  unrelated — the same "one settle point, explicit always wins" rule
  return types (v0.13) already established. This is why
  `test_nested_undeclared_fn_escapes_outer_purity` (an inner fn that
  explicitly declares its OWN `effects [io]` inside an outer `effects
  []`) is unchanged and still passes: it was never testing the
  clause-LESS case this round closes, only that an explicit declaration
  is independent of its lexical parent.
- **`examples/effects.lang`'s `strict_sum` updated to match**: its nested
  `debug_print` (previously clause-less, printing "for free" inside a
  pure outer fn) now declares its own `effects [io]` explicitly — the
  file's own comment rewritten to demonstrate the new default
  (inheritance) alongside the still-available explicit opt-out, instead
  of celebrating the now-closed implicit escape.
- **Still open, unaffected by this round** (the second v0.14 gap):
  passing a builtin as a value (`let p = print`) and calling THAT is
  still invisible to the check — `_check_effect_call` only inspects a
  literal `NameRef` callee, and this is fundamentally a value-flow
  question, not a lexical-scoping one, so it needs a different mechanism
  entirely. Also still open: a fn calling a DIFFERENT, unrestricted
  top-level fn that itself performs the effect — only LEXICAL nesting is
  tracked now, not the dynamic call graph. A full call-graph-aware
  (transitive) effect system closing both remains future work.
  **Partially closed by v0.14.2 (round 266, below)**: the direct-alias
  case (`let p = print` then `p(1)`) specifically is now tracked; passing
  a builtin through a function argument, return value, or a list/record
  field, and the separate call-graph gap, both remain open.
  **Further partially closed by v0.14.3 (round 270, below)**: the
  bare-name-tail return-value case (`fn get() { print }` then `let p =
  get()` or `get()(1)`) is now tracked too; a function ARGUMENT, a
  list/record field, a tail hidden behind an `if`, and the call-graph gap
  all remain open.
  **Further partially closed by v0.14.4 (round 272, below)**: a
  literal-record field case (`let box = @{run: print}` then `box.run(1)`)
  is now tracked too; a function ARGUMENT, a non-literal or call-valued
  record field, a tail hidden behind an `if`, and the call-graph gap all
  remain open.
- **Verification:** `tests/test_v14.py` 20/20 (was 18; one test rewritten
  from `all_ok` to `pytest.raises(ParseError)` since its own assertion
  flipped, two new tests added: a granting-scope inheritance case and a
  two-level inheritance-chains-transitively case).
  `languages/whence/run_tests_fast.sh` 850 passed/38 deselected (was 842
  before landing round 263's own lexer mutation-testing work in a
  separate commit first; +8 = round 263's own +7 lexer tests +1 net from
  this round's test_v14.py changes). Full `pytest tests/` (background,
  no `-m` filter) **888 passed in 819.79s**. `examples/effects.lang`
  re-run directly: all 4 checks pass, output unchanged in spirit (the
  nested "(debug)" prints still happen, now via an explicit clause).
  Guest parity needed NO change and was re-verified, not just assumed:
  `harness/swe/guest.py`'s guest evaluator (`self_eval.lang`) never
  enforced `effects [...]` at all — round 164's own header comment says
  so explicitly ("skip-and-ignore, not enforce") — so this is a HOST-only
  parse-time change; a program the host newly rejects surfaces as the
  already-handled `parse_error` oracle outcome
  (`harness/swe/guest.py::oracle_self_eval` returns early on a host
  `ParseError`, never reaching the host-vs-guest value comparison, so it
  cannot manufacture a false differential mismatch) — cross-checked
  directly against `harness/swe/fuzz.py`'s `ProgramGen`, which DOES
  generate exactly this shape (a clause-less anonymous `fn(...)` 70% of
  the time, nestable inside an `effects [...]`-declared outer fn via
  `expr`/`fnlike`), confirming this isn't a theoretical-only path.

## v0.14.2 (round 266) — effect system: direct builtin aliases are tracked
- **Closes the FIRST HALF of v0.14.1's own "still open" gap**: "passing a
  builtin as a value (`let p = print`) and calling THAT is still invisible
  to the check" (SPEC.md "v0.14.1", above). Closed for the direct-alias
  case only — `let p = print` then `p(1)` is now checked exactly as
  `print(1)` would be — by tracking, at parse time, which currently
  in-scope names are a direct alias of an effectful builtin.
- **Mechanism:** `Parser.alias_scopes` — a stack of dicts, one per lexical
  block scope (pushed/popped by `stmt_list` itself, so every `{...}`,
  including a bare block-as-expression, an `if` arm, and a fn body, gets
  its own frame), name -> tag-or-`None`. A `let NAME = <expr>` statement
  records `alias_scopes[-1][NAME] = tag` where `tag` is whatever
  `_resolve_effectful_alias(expr.name)` returns if `expr` is a bare
  `NameRef` (`None` for any other expression shape). `_resolve_effectful_
  alias(name)` walks the stack innermost-first and returns the FIRST
  frame's value for `name` if any frame has an entry at all — falling back
  to `_EFFECTFUL_BUILTINS` only if NO scope frame mentions `name`.
  `_check_effect_call` now calls this instead of indexing
  `_EFFECTFUL_BUILTINS` directly, so a checked call is "callee resolves to
  an effect tag", not "callee's literal name is `print`".
- **Shadowing is handled correctly, not just aliasing**: recording `None`
  (not skipping the entry) for every plain `let`/`fn`/parameter binding —
  not only ones that happen to alias a builtin — means a local `let p = 5`
  correctly BLOCKS the lookup from falling through to an outer alias `p`,
  rather than misidentifying the shadowed local as the alias. A named
  `fn NAME(...)` statement similarly stakes `None` into the ENCLOSING
  scope's frame for its own name (same slot a `let` would occupy) before
  parsing its params/body, so `fn p() {...}` shadows an outer alias `p`
  too. A fn's OWN parameters get a separate frame, pushed between the
  enclosing scope and the body block's own `stmt_list` frame — mirroring
  the real runtime Env layering (`interp.py`: `_call_gen`'s `call_env`
  holds params, `eval_Block`'s own `inner` is a CHILD of that for the
  body's own `let`s) — so a parameter also correctly shadows an outer
  alias of the same name.
- **Chains transitively**: `let q = p` where `p` is itself a tracked alias
  re-resolves through `_resolve_effectful_alias`, so `q` becomes an alias
  of whatever `p` ultimately aliases, any number of hops deep.
- **Order-dependent, like the rest of this single left-to-right parse
  pass** (the same character `_resolve_effects_scope`'s nested-fn
  inheritance already has): only an alias `let` that appears TEXTUALLY
  BEFORE the call it would cover, in a currently-open scope, is detected.
  A `let` written after the call site it would have covered (e.g. inside
  a closure defined and stored before the alias exists, never invoked
  before the alias binding executes) is invisible — this is a
  single-pass static analysis, not a whole-program fixed point.
- **Still open, unaffected by this round** (the SECOND half of the same
  v0.14.1 gap, plus the pre-existing one): passing the builtin as a
  FUNCTION ARGUMENT, returning it from a call, or storing it in a
  list/record field and calling it back out are all still invisible —
  only a direct `let alias = <name-or-alias>` hop is tracked, not general
  value flow through data structures or other bindings (`for`/pattern
  bindings, if Whence ever gains them). **Partially closed by v0.14.3
  (round 270, below)**: the "returning it from a call" clause specifically
  is now tracked, for the narrow case where the returning fn's own body
  tail-returns a bare name — a function ARGUMENT, a list/record field, and
  a tail hidden behind an `if` all remain invisible. Calling into a DIFFERENT,
  unrestricted top-level function that itself performs the effect is
  ALSO still untouched by the caller's own declaration — only lexical
  nesting and direct aliasing are tracked, not the dynamic call graph. A
  full call-graph-aware (transitive, data-flow-sensitive) effect system
  closing both remains future work. **Further partially closed by v0.14.4
  (round 272, below)**: the "storing it in a record field" clause is now
  tracked too, for the narrow case where the record is a `let`-bound
  LITERAL and the field's own value is a bare name — a function ARGUMENT,
  a non-literal or call-valued record field, and a tail hidden behind an
  `if` all remain invisible.
- **Verification:** `tests/test_v14.py` 28/28 (was 20; one test renamed
  from `test_indirect_call_via_variable_is_not_checked` to `..._is_now_
  checked` since its own assertion flipped from `all_ok` to
  `pytest.raises(ParseError)`, 7 new tests added: grant-still-works,
  two-hop chaining, `let`-shadowing, nested-`fn`-name-shadowing,
  parameter-shadowing, cross-scope visibility into a nested fn, and the
  order-dependence limitation, plus one new three-way differential pin).
  `languages/whence/run_tests_fast.sh` 858 passed/38 deselected (was 850;
  +8 = this round's own net test delta). `examples/effects.lang` extended
  with a `log_total`/`logger` demonstration (an `effects [io]` fn calling
  `print` through a `let logger = print` alias) and re-run directly: all 5
  checks pass (was 4).
- **Guest parity needed no change, for a different and STRONGER reason
  than v0.14.1's**: `print` itself is in `harness/swe/guest.py`'s
  `BANNED` regex — any guest-oracle program that so much as MENTIONS
  `print` anywhere before its own `__result` scrub line is short-circuited
  to a `parse_error`-labeled outcome before the host or guest ever runs it
  (`oracle_self_eval`'s own `BANNED.search` check, ahead of even calling
  `O._parse`), because the guest evaluator does not mirror `print`'s
  host-visible output at all. This is unaffected by, and unrelated to,
  the generic "a host `ParseError` short-circuits before any host-vs-guest
  comparison" mechanism v0.14.1 relied on — `print`-mentioning programs
  never reach that comparison for an entirely separate, pre-existing
  reason. Cross-checked against `harness/swe/fuzz.py`'s `ProgramGen`:
  unlike v0.14.1's nested-clause-less-fn shape (confirmed fuzzable), this
  round's own trigger shape — a bare `print` NameRef assigned by a `let`,
  rather than called directly — does **not** appear anywhere in the
  generator grammar (`print(...)` is always emitted as a literal call
  template, e.g. `"print(%s)"`, never as a bare value); this feature is
  exercised only by `tests/test_v14.py`'s hand-authored cases, not
  cross-validated against the differential fuzz corpus. Documented here
  rather than treated as a gap to close, since fixing it would mean
  teaching the GENERATOR a new expression shape, not the effect checker
  itself, and no other host-only parse-time feature in this codebase has
  ever required generator changes to be considered adequately tested.

## v0.14.3 (round 270) — effect system: RETURN-value flow through a direct call

- **Closes one narrow clause of v0.14.2's own "still open" gap**: "passing
  the builtin ... returning it from a call ... [is] still invisible" —
  closed for the specific shape where the RETURNING function's own body's
  tail statement is a bare name resolving to an effectful alias.
  `fn get_printer() effects [] { print }` doesn't itself perform the "io"
  effect (naming `print` in tail position isn't calling it), but
  `let p = get_printer()` now propagates the fact that `p` holds an
  effectful alias, checked exactly as `let p = print` (v0.14.2) would be.
- **Mechanism**: `Parser.return_alias_scopes` — a SECOND stack, the exact
  same shape as `alias_scopes` (one frame per lexical block, pushed/popped
  at the identical three sites: `stmt_list` itself, and both fn-parameter
  scopes), tracking a different fact per name: "does CALLING this name
  yield an effectful alias" rather than "IS this name one". Populated from
  `stmt_list`'s own new `tail_alias_tag` return value — computed while the
  block's own `alias_scopes` frame is still open, so it can resolve a tail
  statement referencing either a parameter or a body-local `let`, not just
  the fn's own params — stashed onto the real `Block.tail_alias_tag` field
  (`ast_nodes.py`; set at construction, unlike `Call.tail`, which
  `mark_tails` sets in a separate later pass, since `stmt_list` has already
  fully resolved this by the time `block()` constructs the node). A named
  `fn NAME(...)` statement writes `return_alias_scopes[-1][NAME] = None` as
  a placeholder BEFORE parsing its own params/body (shadow-safety and
  self-recursion-safety, mirroring `alias_scopes[-1][NAME] = None`'s
  identical role in v0.14.2), then overwrites it with `body.tail_alias_tag`
  once the body is fully parsed and its own frames popped, back in the
  ENCLOSING scope's frame. `_resolve_effectful_return(name)` walks the
  stack innermost-first, same as `_resolve_effectful_alias`, with no
  `_EFFECTFUL_BUILTINS` fallback (this fact only ever comes from a
  user-written fn body's own tail, never a builtin itself).
- **Three call shapes all read from the same table**: (1) `let p =
  get_printer()` — the `let`-handling code recognizes an `A.Call` expr
  whose own callee is a NameRef with a tracked return fact, and propagates
  it into `p`'s `alias_scopes` entry (an ordinary alias from here on,
  needing no new logic at the `p(...)` call site). (2) `get_printer()(1)` —
  chained, no intermediate `let` — `_check_effect_call` gained a second
  branch: a `Call` callee whose own `fn` is a NameRef resolves through
  `_resolve_effectful_return` directly. (3) `let g = get_printer` (a plain
  RENAME, no call) now carries BOTH of `get_printer`'s facts to `g` — its
  direct-alias status (already true in v0.14.2, was `None` here since a fn
  name is never itself an alias) AND its return fact, so `g()`'s result is
  checked exactly as `get_printer()`'s would be. The same propagation
  applies to a `let`-bound anonymous `fn(...) {...}` — its own
  `body.tail_alias_tag`, already resolved by `block()`, is read directly at
  the `let` site (`expr.__class__ is A.FnExpr`), no separate named-fn
  machinery needed.
- **Shadowing is handled correctly, the same class of bug v0.14.2's own
  design note (§4 of `knowledge/round-266-...md`) warned about**: every
  `let`/named-`fn`/parameter binding writes an explicit entry into BOTH
  stacks (even `None`), not just the ones that happen to carry a fact — an
  inner, differently-behaved `fn get_printer() { 5 }` correctly shadows an
  outer, effectful-returning `get_printer` of the same name, blocking the
  lookup rather than falling through to the stale outer fact.
- **Deliberately narrower than it could be, by design**: only a fn body
  whose tail statement is a BARE NameRef is inspected — a tail that is
  itself an `if` (even one whose every arm tail-returns the same effectful
  name) is not recursed into, unlike `mark_tails`'s fuller structural walk
  of tail position (that one needs no scope context at all, since it only
  ever flips a boolean; this one does, so it can't simply run as a
  after-the-fact pass over the finished AST — it has to observe the
  `alias_scopes`/`return_alias_scopes` frames while they're still open,
  which only `stmt_list` itself can do without threading parser state
  through a second AST walker).
- **Still open, unaffected by this round**: passing a builtin as a FUNCTION
  ARGUMENT, or storing it in a list/record field and reading it back out,
  remain completely invisible — genuine value-flow-through-data-structures
  questions this round does not attempt. The dynamic call graph (calling a
  DIFFERENT, unrestricted function that itself performs the effect) is also
  still untouched. A full call-graph-aware, fully data-flow-sensitive
  effect system closing all of these remains future work — see
  `state/research-state.md`'s language backlog for why the call-graph half
  specifically is sized as multi-round-scale, not a quick follow-up.
- **Verification**: `tests/test_v14.py` 37/37 (was 28; 9 new tests: return
  value via `let` [checked + granted], chained call with no `let` [checked
  + granted], renamed-fn fact propagation, `let`-bound anon fn, the
  same-name shadowing case, the bare-name-tail-only limitation, and one new
  three-way differential pin). `languages/whence/run_tests_fast.sh` 867
  passed/38 deselected (was 858; +9 matches the net new-test delta
  exactly). `examples/effects.lang` extended with a `get_logger`/
  `log_total2` demonstration; `python3 run.py examples/effects.lang` → exit
  0, 6/6 checks pass (was 5/5). `tests/test_examples.py::test_effects` and
  `tests/test_self_hosting.py::test_effects_lang_runs_under_the_guest_
  round_164_backlog_closed` both updated for the new check count (6, was 5)
  and re-verified green — the guest evaluator still does not enforce
  `effects [...]` at all (round 164's own finding, unchanged), so this is
  purely one more ordinary check passing through it, same reasoning as
  round 266's own guest-parity note.
- **Fuzz coverage — same honest gap as v0.14.2, for the same reason**:
  `harness/swe/fuzz.py`'s `ProgramGen` never emits a bare `print` NameRef in
  tail position (or anywhere) — `print(...)` is always one of its literal
  call templates (`"print(%s)"` and variants). This round's own trigger
  shapes (a fn whose tail is a bare effectful name, then calling that fn's
  result) are consequently exercised only by `tests/test_v14.py`'s
  hand-authored cases, not the differential fuzz corpus — not a new gap,
  the same one v0.14.2 already documented and left open for the identical
  reason (fixing it needs a new GENERATOR expression shape, not a checker
  change).

## v0.14.4 (round 272) — effect system: CONTAINER-FIELD value flow through a record literal

- **Closes the CONTAINER-FIELD slice of v0.14.3's own "still open" gap**:
  "storing it in a list/record field and reading it back out" remains
  invisible in general, but is now closed for the specific shape where the
  record is built directly by a `let name = @{...}` LITERAL and the field
  in question was assigned a bare NameRef. `let box = @{run: print}` then
  `box.run(1)` is now checked exactly as `let p = print; p(1)` (v0.14.2)
  would be.
- **Mechanism**: `Parser.field_alias_scopes` — a THIRD stack, the exact
  same shape and push/pop sites as `alias_scopes`/`return_alias_scopes`
  (one frame per lexical block: `stmt_list` itself, and both fn-parameter
  scopes), tracking a third fact per name: "is this name bound to a record
  literal, and if so, which of its fields are themselves effectful
  aliases?" Each frame maps a name to either `None` (not a tracked record
  binding) or a dict `{field: tag-or-None}`, built once, at the `let`, by
  resolving each field VALUE that is a bare `NameRef` through the existing
  `_resolve_effectful_alias`. `_resolve_effectful_field(name, field)`
  mirrors the other two resolvers exactly: innermost-first, first-frame-
  wins walk on `name`, then a plain `.get(field)` within the winning
  frame's dict.
- **`_check_effect_call` gained a third branch**: a callee that is an
  `A.FieldAccess` whose own `.obj` is a NameRef resolves through
  `_resolve_effectful_field` — sitting alongside the existing direct-name
  and chained-call-return branches, all three feeding the same
  `effects_stack`-comparison logic unchanged.
- **Shadowing is handled correctly, the same discipline v0.14.2/v0.14.3
  established**: every `let`/named-`fn`/parameter binding writes an
  explicit entry into ALL THREE stacks (even `None`) — an inner `let box =
  @{run: helper}` (non-effectful) correctly shadows an outer, effectful
  `box` of the same name; a parameter named `box` shadows an outer
  record-tracked `box` the same way a parameter already shadows an outer
  direct/return alias.
- **Deliberately narrower than it could be, by design, same mold as
  v0.14.3**: only a record built directly by a `let`-LITERAL is tracked —
  one returned from a call (even one whose own body tail-returns a literal
  record with an effectful field) is invisible; a record literal reached
  by a chain of hops (merged, copied, mutated) is likewise invisible. Only
  a BARE-NameRef field value is inspected within a tracked literal — a
  field whose value is itself a call (even one returning `print`) resolves
  to `None`, the same "one hop, no recursion" limit v0.14.3 applied to a
  fn's tail statement.
- **Still open, unaffected by this round**: passing a builtin as a
  FUNCTION ARGUMENT remains completely invisible — the one shape of
  v0.14.3's own three-way "still open" list (argument / return / container
  field) this round did not touch, correctly left open per
  `state/research-state.md`'s own reasoning for why it doesn't fit the
  same single-pass mold (a fn body is parsed once, independent of its call
  sites; the fact would need per-call-site specialization or an unsound
  over-approximation). The dynamic call graph is also still untouched —
  see `state/research-state.md`'s language backlog for why it's sized as
  multi-round-scale, not a quick follow-up.
- **Verification**: `tests/test_v14.py` 45/45 (was 37; 8 new tests: field
  call via record literal [checked + granted], a non-effectful field is
  not flagged, inner-record-of-same-name shadowing, param-name shadowing
  [with a real record passed at runtime], a non-literal binding is not
  tracked, a call-valued field is not tracked, one new three-way
  differential pin). `languages/whence/run_tests_fast.sh` 875 passed/38
  deselected (was 867; +8 matches the net new-test delta exactly, no other
  file's count moved).
- **Guest parity**: same reasoning as v0.14.2/v0.14.3, for the same
  underlying cause — `print` is in `harness/swe/guest.py`'s `BANNED`
  regex, so any guest-oracle fuzz program mentioning it anywhere is
  short-circuited to `parse_error` before either interpreter runs it; not
  something this round needed to re-verify.
- **Fuzz coverage — same honest gap as v0.14.2/v0.14.3, for the same
  reason**: `harness/swe/fuzz.py`'s `ProgramGen` never emits a record
  literal whose field value is a bare `print` NameRef — this round's own
  trigger shape is consequently exercised only by `tests/test_v14.py`'s
  hand-authored cases, not the differential fuzz corpus. Fixing it needs a
  new GENERATOR expression shape, not a checker change — named here so a
  future round doesn't rediscover it as a mystery.

## v0.14.5 (round 276) — effect system: IF/ELSE-tail value flow through a direct call

- **Closes the "if" half of v0.14.3's own documented gap**: a fn body
  whose TAIL STATEMENT is an `if`/`else` (any `else if` chain length),
  where EVERY arm resolves to the exact same effectful alias, is now
  tracked as a "return fact" the same way a bare-NameRef tail already was
  — `let get_printer = fn(cond) { if cond { print } else { print } }`
  then `let p = get_printer(true); p(1)` is now checked exactly as
  `let p = print; p(1)` (v0.14.2) would be. `test_return_tag_only_sees_a_
  bare_name_tail` (the test that pinned this as an honest, open gap since
  round 270) is replaced by
  `test_return_tag_sees_an_if_else_tail_when_both_arms_agree` and five
  companions covering the granted case, an `else if` chain, and two
  "one arm disagrees, stays untracked" cases.
- **Mechanism, and why it needed no new stack**: `Parser._if_tail_alias_
  tag(if_node)` is a purely STRUCTURAL, post-hoc walk — `if_node.then` is
  always an already-parsed `A.Block` (`block()` always returns one), and
  `if_node.otherwise` is either another already-parsed `A.Block` (a plain
  `else { ... }`) or an already-parsed `A.If` (an `else if ...` chain,
  recursed into). Each such child block ALREADY resolved its own
  `tail_alias_tag` correctly, via `stmt_list`, while ITS OWN `alias_
  scopes` frame was open (the exact same code path v0.14.3 uses for a
  bare-NameRef tail) — by the time the ENCLOSING `stmt_list` looks at its
  own tail (now possibly an `A.If`), those child facts are just plain
  already-computed field reads, no scope context needed, the same "no
  scope context needed" shape `mark_tails`'s own boolean structural walk
  already has. This is why the previous three rounds' "can't simply run
  after the fact" limitation (`stmt_list`'s own docstring, pre-v0.14.5)
  didn't actually block this specific shape once looked at carefully: the
  blocker was re-resolving a BARE NAME after its scope closed, not
  reading an ALREADY-RESOLVED per-block field.
- **Sound, not approximate, by construction**: `_if_tail_alias_tag`
  requires every arm's tag to be identical, not merely non-None — one
  arm resolving to a different tag, or to `None` (a plain value, or an
  untracked callable), makes the whole `if` resolve to `None`
  (`test_return_tag_if_else_tail_needs_every_arm_to_agree`,
  `test_return_tag_else_if_chain_one_mismatched_arm_is_not_tracked`). An
  "any arm matches" rule would be UNSOUND: a caller in an `effects [io]`
  scope could then reach a branch performing a real, undeclared effect
  without ever being flagged — exactly the kind of false-negative-that-
  looks-like-a-false-positive-fix this feature family has avoided at
  every step (v0.14.2's shadowing discipline, v0.14.4's exact-field-match
  requirement).
- **Still deliberately narrow**: the recursion only ever starts from the
  enclosing block's own TAIL statement — an `if` bound to a `let` first
  and referenced afterward is not inspected
  (`test_return_tag_only_sees_a_tail_if_else_not_a_deeper_nested_one`),
  matching the "one hop from the tail, no general data-flow" discipline
  v0.14.3/v0.14.4 already established. The two gaps v0.14.4 left fully
  open — passing a builtin as a FUNCTION ARGUMENT, and the dynamic call
  graph — are both still completely untouched by this round; neither fits
  the same single-pass, no-interprocedural-analysis mold this whole
  feature family relies on (see `state/research-state.md`'s language
  backlog for why both are sized as multi-round-scale work, not a quick
  follow-up).
- **Verification**: `tests/test_v14.py` 51/51 (was 45; net +6: one old
  test documenting the now-closed gap replaced by six new ones — both-
  arms-agree [checked + granted], an `else if` chain [checked + one-arm-
  mismatch-stays-untracked], one new three-way differential pin, and the
  "not from a non-tail position" boundary case).
  `languages/whence/run_tests_fast.sh` 880 passed/38 deselected (was 875;
  +5 is net-new across the whole suite, matching `test_v14.py`'s own net
  delta exactly — no other file's count moved). Full unfiltered
  `pytest tests/` also run this round (parser.py's `stmt_list` is on
  every block-parse path, not just effects-declared code) — no
  regressions.
- **Guest parity**: same reasoning as v0.14.2/v0.14.3/v0.14.4, for the
  same underlying cause — `print` is in `harness/swe/guest.py`'s
  `BANNED` regex, so any guest-oracle fuzz program mentioning it anywhere
  is short-circuited to `parse_error` before either interpreter runs it;
  not something this round needed to re-verify.
- **Fuzz coverage — same honest gap as v0.14.2/v0.14.3/v0.14.4, for the
  same reason**: `harness/swe/fuzz.py`'s `ProgramGen` never emits a fn
  body whose tail is an `if`/`else` with a bare `print` NameRef in every
  arm — this round's own trigger shape is exercised only by
  `tests/test_v14.py`'s hand-authored cases, not the differential fuzz
  corpus. Fixing it needs a new GENERATOR expression shape, not a checker
  change — named here so a future round doesn't rediscover it as a
  mystery (the fourth round in a row to note this same class of gap for
  its own new shape). **Closed by round 278/279's landed diff** (see
  round 278's own entry in `state/research-state.md`) — `ProgramGen` now
  covers this shape along with v0.14.3/v0.14.4's.

## v0.14.6 (round 282) — effect system: RETURN-value flow through a field call

- **Closes the specific slice of v0.14.4's own documented gap named but not
  touched**: "a field whose value is itself a call/alias chain is
  invisible" — closed here for the case where the field's bare-NameRef
  value is itself a return-carrier (a fn tracked, per v0.14.3, to
  tail-return an effectful alias). `let box = @{run: get_printer}` then
  `box.run()(1)` — TWO applications, the FIRST (`box.run()`) itself
  invoking whatever `get_printer` was tracked to return — is now checked
  exactly as `get_printer()(1)` (v0.14.3) would be. The mirror-image
  extension is exactly what its name suggests: v0.14.3 added a RETURN
  fact for bare names, v0.14.4 added a FIELD fact for direct aliases,
  this round adds the missing fourth combination, a FIELD fact for return
  aliases.
- **Mechanism**: `Parser.field_return_alias_scopes` — a FOURTH stack, the
  exact same shape and three push/pop sites as the other three
  (`stmt_list`, and both fn-parameter scopes). Built at the same `let
  name = @{...}` LITERAL site `field_alias_scopes` already inspects, from
  the SAME bare-NameRef field values, just resolved through
  `_resolve_effectful_return` instead of `_resolve_effectful_alias` — the
  two dicts are independent (a field can be a direct alias, a
  return-carrier, both, or neither;
  `test_field_return_chain_and_field_direct_alias_are_independent` pins
  this). `_resolve_effectful_field_return(name, field)` mirrors the other
  three resolvers exactly: innermost-first, first-frame-wins walk on
  `name`, then a plain `.get(field)` within the winning frame's dict.
- **`_check_effect_call` gained a fourth branch**: a callee that is a
  `Call` whose own `.fn` is a `FieldAccess` on a NameRef resolves through
  `_resolve_effectful_field_return` — sitting alongside the existing
  direct-name, chained-call-return, and direct-field branches, all four
  feeding the same `effects_stack`-comparison logic unchanged. The FIRST
  application (`box.run()` on its own) is still checked, separately and
  independently, by the pre-existing direct-field branch (v0.14.4) —
  `box.run` itself is not tracked as effectful here, only calling its
  result is.
- **Shadowing is handled correctly, the same discipline v0.14.2/v0.14.3/
  v0.14.4/v0.14.5 established**: every `let`/named-`fn`/parameter binding
  writes an explicit entry into ALL FOUR stacks (even `None`)
  (`test_inner_record_of_same_name_shadows_outer_field_return_alias`).
- **Still deliberately narrow, same mold as v0.14.4**: only a record
  built directly by a `let`-LITERAL is tracked
  (`test_field_return_chain_of_a_non_literal_binding_is_not_tracked`); a
  field value that resolves to `None` in `return_alias_scopes` (an
  ordinary, non-return-tracked fn) leaves the field-return fact at `None`
  too (`test_field_return_chain_field_value_that_is_not_a_return_carrier`).
  Passing a builtin as a FUNCTION ARGUMENT and the dynamic call graph
  remain completely untouched, unchanged from v0.14.4/v0.14.5's own
  "still open" notes — this round is a fourth combination of the SAME
  four building blocks (direct/return x bare-name/field), not a step
  toward either of those two genuinely multi-round-scale items.
- **Verification**: `tests/test_v14.py` 58/58 (was 51; 7 new tests: the
  chained-field-call check itself [checked + granted], independence from
  the direct-alias field dict, a non-return-carrier field value is not
  tracked, the non-literal-binding boundary, inner-record shadowing, one
  new three-way differential pin). `languages/whence/run_tests_fast.sh`
  888 passed/38 deselected (was 881 going into this round — round 278's
  fuzz-coverage diff, landed by round 279, had already moved the fast-tier
  count from 880 to 881 with zero `test_v14.py` tests of its own; +7 this
  round matches `test_v14.py`'s own net delta exactly). Full unfiltered
  `pytest tests/` also run this round (`parser.stmt_list`/`statement` sit
  on every block-parse path, not just effects-declared code) — see
  `knowledge/round-282-whence-v0146-effect-field-return-chain.md` for the
  exact count and any regressions found.
- **Guest parity**: same reasoning as v0.14.2/v0.14.3/v0.14.4/v0.14.5, for
  the same underlying cause — `print` is in `harness/swe/guest.py`'s
  `BANNED` regex, so any guest-oracle fuzz program mentioning it anywhere
  is short-circuited to `parse_error` before either interpreter runs it;
  not something this round needed to re-verify.
- **Fuzz coverage — same honest gap as v0.14.2/v0.14.3/v0.14.4/v0.14.5,
  for the same reason**: `harness/swe/fuzz.py`'s `ProgramGen` never emits
  a record literal whose field value is a bare-NameRef return-carrier —
  this round's own trigger shape is exercised only by
  `tests/test_v14.py`'s hand-authored cases, not the differential fuzz
  corpus. Named here so a future round doesn't rediscover it as a
  mystery, same as v0.14.2/v0.14.3/v0.14.4/v0.14.5 each did for their own
  new shape.

## v0.14.7 (round 288) — effect system: CONTAINER-FIELD value flow through a NESTED record literal

- **Closes the specific slice of v0.14.4's own documented gap named but not
  touched**: "a field whose value is itself a ... nested-record[/shape] is
  invisible" — closed here for the case where the OUTER field's value is
  itself another record literal, one level deeper than v0.14.4's own
  single-hop case. `let outer = @{box: @{run: print}}` then
  `outer.box.run(1)` — a TWO-FIELD access chain reaching all the way down
  to a bare-NameRef effectful alias — is now checked exactly as `box.run
  (1)` (v0.14.4) would be for a `box` bound directly by the enclosing
  `let`.
- **Mechanism**: `Parser.nested_field_alias_scopes` — a FIFTH stack, the
  exact same shape and three push/pop sites as the other four
  (`stmt_list`, and both fn-parameter scopes). Built at the same `let name
  = @{...}` LITERAL site `field_alias_scopes`/`field_return_alias_scopes`
  already inspect, but keyed only on fields whose OWN value is ANOTHER
  `A.RecordLit` — for each such field, the inner literal's own
  bare-NameRef fields are resolved through `_resolve_effectful_alias` the
  exact same way a top-level literal's fields already are, producing a
  dict-of-dicts: `{outer_field: {inner_field: tag-or-None}}`.
  `_resolve_effectful_field_nested(name, outer_field, inner_field)`
  mirrors the other four resolvers' innermost-first, first-frame-wins walk
  on `name`, then two chained `.get`s (each individually guarded against a
  missing or `None` intermediate result, the same way
  `_resolve_effectful_field`/`_resolve_effectful_field_return` guard their
  own single `.get`).
- **`_check_effect_call` gained a fifth branch**: a callee that is an
  `A.FieldAccess` whose own `.obj` is ITSELF an `A.FieldAccess` (rather
  than a bare NameRef, the shape v0.14.4's branch already covers) whose
  own `.obj` is a NameRef — i.e. the `outer.box.run` shape — resolves
  through `_resolve_effectful_field_nested`, sitting alongside the
  existing four branches, all five feeding the same `effects_stack`-
  comparison logic unchanged. This is a genuinely NEW branch, not a
  generalization of the existing field branch, because the existing
  branch's guard (`callee.obj.__class__ is A.NameRef`) is a class check —
  mutually exclusive with the new branch's guard by construction, so
  there is no ordering hazard between the two.
- **Shadowing is handled correctly, the same discipline v0.14.2/v0.14.3/
  v0.14.4/v0.14.5/v0.14.6 established**: every `let`/named-`fn`/parameter
  binding writes an explicit entry into ALL FIVE stacks (even `None`)
  (`test_inner_record_of_same_name_shadows_outer_nested_field_alias`,
  `test_param_named_like_outer_nested_field_alias_shadows_it`).
- **Still deliberately narrow, same mold as v0.14.4/v0.14.6, and does NOT
  generalize to arbitrary depth**: only an OUTER record built directly by
  a `let`-LITERAL is tracked
  (`test_nested_field_of_a_non_literal_outer_binding_is_not_tracked`); the
  nesting stops at exactly ONE additional hop — a THIRD level
  (`a.b.c.run(...)`) is not tracked by this stack at all, the callee shape
  simply does not match the new branch's guard (`callee.obj.obj.__class__
  is A.NameRef` requires the chain to bottom out in a bare name exactly
  two `.field` hops up). A middle field whose value was never itself a
  record literal correctly leaves the chain untracked
  (`test_nested_field_where_middle_field_is_not_itself_a_record_literal`);
  an inner field whose value is itself a call is also untracked, the same
  "bare NameRef only" rule every level of this family applies
  (`test_nested_field_value_that_is_itself_a_call_is_not_tracked`).
  Passing a builtin as a FUNCTION ARGUMENT and the dynamic call graph
  remain completely untouched, unchanged from v0.14.4/v0.14.5/v0.14.6's
  own "still open" notes — this round is a deeper nesting of an EXISTING
  building block (container fields), not a step toward either of those
  two genuinely multi-round-scale items.
- **Verification**: `tests/test_v14.py` 67/67 (was 58; 9 new tests: the
  nested-field call itself [checked + granted], a non-effectful nested
  field is not flagged, inner-record shadowing at the outer name, param-
  name shadowing [with a real nested record passed at runtime], the
  non-literal-outer-binding boundary, the middle-field-not-a-literal
  boundary, a call-valued inner field is not tracked, one new three-way
  differential pin). `languages/whence/run_tests_fast.sh` 897 passed/38
  deselected (was 888; +9 matches `test_v14.py`'s own net delta exactly,
  no other file's count moved). Full unfiltered `pytest tests/` also run
  this round (`parser.stmt_list`/`statement` sit on every block-parse
  path, not just effects-declared code): **935 passed in 382.40s**, zero
  regressions.
- **Guest parity**: same reasoning as v0.14.2 through v0.14.6, for the
  same underlying cause — `print` is in `harness/swe/guest.py`'s `BANNED`
  regex, so any guest-oracle fuzz program mentioning it anywhere is
  short-circuited to `parse_error` before either interpreter runs it; not
  something this round needed to re-verify.
- **Fuzz coverage — same honest gap as v0.14.2 through v0.14.6, for the
  same reason**: `harness/swe/fuzz.py`'s `ProgramGen` never emits a record
  literal whose field value is itself ANOTHER record literal at all (let
  alone one with a bare-NameRef `print` field nested inside it) — this
  round's own trigger shape is exercised only by `tests/test_v14.py`'s
  hand-authored cases, not the differential fuzz corpus. Fixing it needs a
  new GENERATOR expression shape (a nested `@{...}` as a field value), not
  a checker change — named here so a future round doesn't rediscover it as
  a mystery, same as every prior round in this family. `harness/swe/
  alias_effects.py`'s `ExtendedEffectGen` (round 281/287's independent
  parse-time-VERDICT oracle) also does not yet cover this shape — a
  natural next SWE-loop(D) round, same size/shape as round 287's own
  v0.14.6 extension.

## v0.14.8 (round 294) — effect system: the second effectful builtin, `rand`
- **Every alias-tracking round from v0.14.2 through v0.14.7 exercised
  `_EFFECTFUL_BUILTINS` (`parser.py`) with exactly ONE real entry**
  (`print`/"io"); the "per-tag, not merely was-a-clause-present" property
  (`test_effects_unrelated_tag_still_blocks_print`) was only ever pinned
  against a hypothetical, unused tag name ("network"), never a second REAL
  capability. Round 293's own next-steps explicitly named the choice this
  round faced: the two genuinely multi-round-scale alias-tracking gaps
  (builtin-as-argument, dynamic call graph) are "unchanged in scope-
  assessment since round 270, still correctly not attempted piecemeal", so
  any further extension to the effect-alias family should be "a genuinely
  new Whence language feature (v0.14.8+)... unless one turns up during
  normal spec review". A normal spec review of `parser.py`'s own v0.14
  design comment turned exactly that up: "`_EFFECTFUL_BUILTINS = {"print":
  "io"}` is the one place a future effectful builtin (randomness, a clock,
  real I/O) would register its tag; nothing else would need to change" —
  an anticipated extension point, sitting unclaimed since round 146.
- **`rand()` (arity 0) draws a float in `[0.0, 1.0)`** from the
  `Interpreter`'s own `random.Random` instance, tagged `"random"` (distinct
  from `print`'s `"io"`) in `_EFFECTFUL_BUILTINS = {"print": "io", "rand":
  "random"}`. Built as a `leaf` node (no input provenance, exactly like a
  literal) — `whence/interp.py`'s `b_rand`.
- **The one real design decision this round makes, and the reason it took
  real thought rather than being a one-line addition**: an actually-
  nondeterministic builtin is fundamentally at odds with THREE existing,
  load-bearing pieces of this project's own testing methodology — the
  three-way differential (`assert_three_way`, three SEPARATE `Interpreter`
  instances for direct/fast/slow that must agree byte-for-byte on
  `render_why`), the guest/host oracle campaigns, and `bench/ref_diff.py`'s
  reference comparison — all of which assume a Whence PROGRAM's behavior
  is a pure function of its source text. **Resolution: `rand()` is
  reproducible, not unpredictable.** `Interpreter.__init__` gained a
  `seed=0` parameter; `self._rng = random.Random(seed)` is a per-instance
  stream, not process-global entropy. Two fresh `Interpreter()` instances
  (the default seed, 0, unless overridden) draw the IDENTICAL sequence
  (`test_rand_is_deterministic_for_the_default_seed`), so the three-way
  differential's three independently-constructed interpreters agree on
  `rand()`'s value exactly as they already agree on everything else
  (`test_three_way_rand_matches_across_direct_fast_slow`) — no special-
  casing needed anywhere in the differential harness itself. This is a
  genuine departure from mainstream languages (most seed `random()` from OS
  entropy by default, favoring unpredictability); Whence favors
  reproducibility instead, the same value judgment sandboxed/deterministic-
  replay execution environments make, and the only value judgment under
  which "randomness" and "the entire test suite assumes determinism" can
  coexist without a special case. `run.py` gained a `--seed N` CLI flag
  (default 0) so a real user CAN vary the stream deliberately; the REPL and
  every existing embedder that doesn't pass `seed=` keep the reproducible
  default unchanged.
- **Confirms the v0.14 design comment's own claim literally true**: adding
  the second entry to `_EFFECTFUL_BUILTINS` needed ZERO other code changes
  — `_check_effect_call` and every `_resolve_effectful_alias`/`_resolve_
  effectful_return`/`_resolve_effectful_field`/`_resolve_effectful_field_
  return`/`_resolve_effectful_field_nested` helper (v0.14.2 through
  v0.14.7) already operate purely on the tag a name resolves to, generic
  since the day each was written. `test_aliased_rand_is_checked_same_as_
  aliased_print` exercises this live: `let r = rand; effects [] { r() }`
  is rejected, `effects [random] { let r = rand; r() }` is granted, through
  the SAME `_resolve_effectful_alias` v0.14.2 wrote for `print`.
- **Per-tag distinctness, now proven with two real capabilities, not one
  real + one hypothetical**: `effects [io]` does not grant `"random"` (so
  `rand()` is still rejected), and `effects [random]` does not grant
  `"io"` back (so `print(...)` is still rejected) — `test_effects_random_
  tag_is_independent_of_io_tag`, the two-real-tag mirror of `test_effects_
  unrelated_tag_still_blocks_print`. `effects [io, random]` grants both
  (`test_effects_io_and_random_together_allow_both`).
- **`examples/effects.lang` gained two checks** (7 → 9) demonstrating the
  unrestricted top-level case and `effects [random]` granting the new tag
  — no rejected-case example, the same reason v0.14's own file gives none
  (a `ParseError` aborts the whole file before any `check` runs; the
  rejection paths are pinned by `tests/test_v14.py` instead).
- **Verification**: `tests/test_v14.py` 78/78 (was 67; 11 new tests: return-
  type/arity/determinism/seed-argument for `rand` itself, the empty-scope
  rejection, the granting case, the two-real-tag independence check in
  BOTH directions, the io+random-together case, the aliased-`rand` reuse
  check, one new three-way differential pin). `languages/whence/
  run_tests_fast.sh` 908 passed/38 deselected (was 897; +11 matches
  exactly, no other file's count moved). `bash harness/run_tests_fast.sh`
  (the unrelated SWE-loop(D) track's own suite, run as a cross-track
  regression check since this round touches `parser.py`/`interp.py`
  neither alias_effects.py nor fuzz.py inspect directly) — **403 passed,
  196 deselected, byte-identical to round 293's own baseline**.
- **Guest parity — NOT done this round, by design, matching every prior
  v0.14.x feature's own arc** (v0.14 itself landed round 146, guest parity
  round 164; v0.14.1 round 264 still has no guest-side inheritance change
  needed since the guest never enforced `effects [...]` at all): `self_
  eval.lang`'s own `builtin_names` list has no entry for `rand` yet, so a
  guest program calling it fails at NAME RESOLUTION, the same gap class
  rounds 206 (`steps`)/218 (`at`/`blame`/`diverge`/`contrast`)/224
  (`matches`/`shapeof`) each found and fixed for their own builtin.
  `tests/test_self_hosting.py::test_effects_lang_runs_under_the_guest_
  round_164_backlog_closed` updated to expect exactly `rand`'s own two new
  checks failing under the guest (an unbound-name miss propagates through
  both), every pre-existing check unaffected — the file still parses
  cleanly (a bare `rand()` call is an ordinary `Call` node to the guest
  parser, no different from any other name).
- **Fuzz/oracle coverage — also NOT done this round, same reasoning**:
  `harness/swe/fuzz.py`'s `ProgramGen` and `harness/swe/alias_effects.py`'s
  `ExtendedEffectGen` both only know about `print`; teaching either
  generator that `rand` is a second effectful builtin (and, for the fuzzer,
  that `harness/swe/guest.py`'s `BANNED` line-filter needs a second entry so
  guest-differential campaigns keep vacuously satisfying declarations the
  same way they do for `print`) is future SWE-loop(D) work, not this
  round's (language(C)'s) own scope — the same track split every prior
  v0.14.x feature has followed.

### `rand` guest parity (round 296)
- **Closes the gap the section above named**: `examples/self_eval.lang`'s
  `builtin_names` gained a `"rand"` entry (after `"print"`, its fellow
  effectful builtin) and its `arities` record gained `rand: 0` — the
  guest's first-ever arity-0 builtin. `apply_builtin`'s own arity check
  (`if ar == -1 {...} else {len(args) == ar}`) already handles 0 with no
  change; a 0-arg call's `args` list is simply `[]`.
  `apply_host_builtin(name, args)` dispatches `"rand"` to the real host
  `rand()` builtin directly (`else if name == "rand" { rand() }`, next to
  `"print"`'s own branch) rather than reimplementing a draw in guest code.
- **Why calling the real builtin gives correct VALUE parity, not just
  correct SHAPE**: `self_eval.lang` is itself Whence source, executed by
  an outer `Interpreter`. When it calls `rand()` to service a guest
  program's own `rand()` call, that draws from the SAME outer
  interpreter's seeded `_rng` a fully direct (non-guest) evaluation of the
  identical program would use — since `self_eval.lang`'s own code never
  calls `rand()` except in this one dispatch branch, each guest-level
  `rand()` call consumes exactly one draw, in the same order the guest
  program makes them, so guest and direct-host evaluation agree exactly
  given the same seed. No special-casing needed anywhere in the guest
  evaluator, the same "operate purely on values, oblivious to where they
  came from" property that let the parser-side `_EFFECTFUL_BUILTINS`
  extension (above) need zero other code changes.
- **Node shape parity is automatic, not hand-mirrored**: `rand`'s host
  node (`interp.py`'s `b_rand`) is `leaf("rand", "", line, value)` — op
  `"rand"`, empty detail, no inputs. `apply_builtin`'s existing catch-all
  branch (the `else` after every named special case) already produces
  exactly that shape for any builtin absent from `propagating`/the
  node-shape-override list: `o = name` (not `"builtin"`, since `rand` is
  correctly NOT added to `propagating` — arity 0 means there is nothing to
  propagate from) and `ins2 = args` (`[]`). No new special-case branch was
  needed in `apply_builtin` itself, only in `apply_host_builtin`'s
  dispatch table.
- **`tests/test_self_hosting.py::test_effects_lang_runs_under_the_guest_
  round_164_backlog_closed`** updated: `examples/effects.lang`'s all 9
  checks (including both of `rand`'s own) now pass under the guest, where
  round 294 pinned exactly those 2 as the expected failures. Verified
  directly with `python3 run.py examples/effects.lang` (host) and via the
  guest harness (`Interpreter().run(eval_lib + run_src(effects_src))`) —
  both report `checks: 9 passed, 0 failed`.
- **Verification**: `pytest tests/test_self_hosting.py -q` → **15 passed**
  (no count change — this fixed an existing test's assertion, added none).
  `bash run_tests_fast.sh` → **908 passed, 38 deselected**, byte-identical
  to round 294's own post-`rand`-landing baseline (this round touches only
  `examples/self_eval.lang` and one test file, no interpreter code).
  Unfiltered `pytest tests/` → **946 passed**. `bench/ref_diff.py
  --counters examples/*.lang` (working tree `whence/` package vs git HEAD)
  → every file, including `effects.lang` (`bindings=12 checks=9 out=11`),
  `SAME` across direct/fast/slow — expected, since this round's diff is
  entirely inside `self_eval.lang`, never `whence/*.py`, so the reference
  differential (which only compares the Python package) has nothing to
  disagree about; run anyway as the standing cross-check this project's
  language(C) rounds always include. Cross-track regression check: `bash
  harness/run_tests_fast.sh` → **403 passed, 199 deselected** (round 295's
  own `GuestHarness`/`harness_for` `max_depth` fix, reconciled the same
  round this work landed, moved the deselected count from 196; unaffected
  by this round's own change).
- **Still open, unchanged in scope from the section above**: fuzz coverage
  (`harness/swe/fuzz.py`'s `ProgramGen`, + a `BANNED` second entry in
  `harness/swe/guest.py`) and `ExtendedEffectGen` oracle coverage for
  `rand` — SWE-loop(D)'s own next round, same shape as the v0.14.2-
  v0.14.7 arc but for a genuinely new builtin. **Closed by round 299**
  (`harness/swe/fuzz.py`, `harness/swe/alias_effects.py`,
  `harness/swe/guest.py`) — see that round's own `research-state.md` entry.

## v0.14.9 (round 300) — effect system: the NAMED-fn slice of value flow through a function ARGUMENT
- **The two remaining effect-system gaps, unchanged in scope-assessment
  since round 270** (SPEC.md's own v0.14/v0.14.4/v0.14.7/`tests/
  test_v14.py`'s module docstring, repeatedly reaffirmed through round
  298's `research-state.md` next-steps): (a) value flow through a function
  ARGUMENT, (b) the dynamic call graph (calling a different, unrestricted
  top-level fn that itself performs the effect). Both were explicitly
  flagged as needing a real design decision — "per-call-site
  specialization or an unsound over-approximation... not just more
  lexical-scope bookkeeping" (round 270's own words) — before any future
  round should attempt more than a design sketch. This round picks (a)
  apart rather than attempting it whole: within it, a NAMED fn (`fn
  NAME(...) {...}`) calling one of its OWN parameters directly is a
  narrower, cleanly-scoped sub-problem than the general case (an anonymous
  `fn(...) {...}` bound by `let`, or a param merely stored/returned/passed
  further along), and is exactly the "one hop past the existing frontier"
  shape every prior v0.14.x round has used to make forward progress
  without attempting the full, genuinely multi-round-scale feature in one
  sitting.
- **Design**: unlike every sibling `_resolve_effectful_*` (each answers
  "does THIS NAME carry an effect fact", decidable once, at its own
  binding site), whether `fn apply(f) effects [io] { f(1) }` is sound to
  call as `apply(print)` depends on the SPECIFIC ARGUMENT at each call
  site — `apply`'s own body, parsed exactly once, independent of any call
  site, never learns what `f` actually is. The check therefore cannot live
  where every other v0.14.x check lives (inside the callee's own body
  parsing); it has to run at each CALL SITE instead, against a fact
  recorded ONCE, when `apply` itself was defined: which of its own params
  it calls directly, and under what `effects [...]` scope. New machinery,
  `whence/parser.py`:
  - **`Parser.param_call_scopes`**: a SIXTH stack, same per-block-frame
    shape and push/pop sites as the other five (`alias_scopes` and
    friends). Maps a NAMED fn's name to `None` (calls none of its own
    params directly) or `(effects_scope, params_tuple,
    frozenset_of_directly_called_param_names)`, recorded once its body
    finishes parsing — the exact same place `return_alias_scopes[-1][name]
    = body.tail_alias_tag` already records the v0.14.3 return fact.
  - **`Parser.current_fn_params_frame_stack` / `direct_param_calls_stack`**:
    transient (NOT scope-shaped) bookkeeping, live only while a single
    fn's own body is being parsed, accumulating which of ITS OWN params
    are seen as a direct call target (`f(...)`) anywhere in the body, at
    any nesting depth. Correctness of SHADOWING (a nested block's own
    `let`/`fn`/param of the same name must NOT be misattributed to the
    outer fn's own parameter) comes from an IDENTITY comparison: the exact
    dict object pushed for the fn's own params frame is captured once and
    compared, by `is`, against whatever frame an innermost-first walk of
    `alias_scopes` actually resolves the callee name through
    (`_innermost_frame_containing`) — if a closer frame wins, it is not
    this fn's own parameter, full stop.
  - **`Parser._check_call_site_param_effects`**: runs at every call
    expression (`postfix()`, alongside `_check_effect_call`), looks up the
    callee's recorded param-call fact (`_resolve_param_call_fact`, the
    same innermost-first walk every sibling resolver uses), and for each
    argument landing in a directly-called parameter slot, checks it —
    against the CALLEE's own recorded effects scope, not the caller's
    (the callee's body, not the call site, is what actually performs the
    effect).
- **Deliberately narrow, the same discipline every v0.14.x round before
  it used**: only a NAMED fn is tracked (an anonymous `fn(...) {...}`
  bound by `let` has no name yet at the point its own param-call fact
  would need to be recorded under — would need a new `A.FnExpr` AST field
  to carry the fact forward, the same way `body.tail_alias_tag` already
  rides on `A.Block`, deliberately out of scope this round); only a
  parameter called DIRECTLY (`f(...)`) is tracked, not one merely stored,
  returned, or passed on to a THIRD function; only a bare-NameRef argument
  at the call site is inspected, the same "bare-NameRef only" boundary
  every sibling resolver already has; forward-referenced or mutually-
  recursive fns are invisible, same single left-to-right parse pass as
  everything else in this family.
- **Zero interpreter changes, zero new AST nodes** — entirely parse-time,
  same as every v0.14.x feature before it.
- **Verification**: `tests/test_v14.py` 78 → **92 passed** (14 new:
  the basic grant/reject pair, the no-clause-unrestricted case, the
  `random` tag mirror, a non-effectful argument, "stored not called" is
  not a false positive, only the directly-called param position is
  checked (not a sibling param), a non-NameRef argument is invisible, the
  anonymous-`let`-bound-fn boundary, inner-fn-same-param-name shadowing in
  both directions, the callee's-own-scope-not-the-caller's distinction,
  a too-few-args guard, a plain rename carries the fact forward, and a
  parameter shadowing an earlier-tracked fn name). `run_tests_fast.sh`:
  **908 passed, 38 deselected**, byte-identical to round 296's own
  baseline (this round adds new tests but no new runtime-reachable code
  path any pre-existing fast-tier test would exercise). Full unfiltered
  `pytest tests/` run in the background per the round-227 convention.
  Cross-track regression: `bash harness/run_tests_fast.sh` unaffected
  (this round touches only `languages/whence/`, confirmed via `git status`
  before starting).
- **Still open, unchanged from every prior round's own assessment**: an
  argument reaching an effectful builtin through a SECOND function call
  before landing in a directly-called param; a builtin flowing into a
  param that is stored/returned rather than called directly; the
  anonymous-fn-bound-by-`let` slice of even the NAMED-fn shape this round
  closes; and the dynamic call graph (b), completely untouched. Fuzz
  coverage (`harness/swe/fuzz.py`) and oracle coverage
  (`harness/swe/alias_effects.py`) for this new shape are open, the same
  "ship the checker, name the fuzz gap, close it in a later dedicated
  round" rhythm every v0.14.x feature has followed.

## v0.14.10 (round 302) — effect system: the anonymous-fn-bound-by-`let` slice of value flow through a function ARGUMENT
- **Closes v0.14.9's own explicitly-named remaining slice** ("only a NAMED
  fn is tracked... would need a new `A.FnExpr` AST field to carry the fact
  forward, the same way `body.tail_alias_tag` already rides on `A.Block`,
  deliberately out of scope this round" — v0.14.9's own words, unchanged
  through round 301's next-steps): `let g = fn(f) effects [io] { f(1) }`
  then `g(print)` is now checked, exactly as if `g` were a NAMED fn.
- **Design**: `Parser.primary()`'s `fn(...) {...}` branch already pushes
  and pops the same `current_fn_params_frame_stack`/`direct_param_calls_
  stack` bookkeeping the NAMED-fn branch uses (needed regardless, for
  shadowing/tracking consistency of anything declared INSIDE the anonymous
  fn's own body) — but through v0.14.9, the popped `called_params` set at
  that site was simply discarded, because there was no NAME yet to key
  `Parser.param_call_scopes` by while the anonymous fn's own params/body
  were being parsed. v0.14.10 does exactly what v0.14.9's own text
  predicted: a new `A.FnExpr` field, `param_call_fact` — `None`, or
  `(effects_scope, params_tuple, frozenset_of_directly_called_param_
  names)`, the identical shape `param_call_scopes` already stores for a
  NAMED fn — set once, right before the `A.FnExpr` node is constructed,
  the same way `A.Block.tail_alias_tag` is already set once `stmt_list`
  finishes resolving a block's own tail (v0.14.3). `statement()`'s own
  `let` handling (the `expr.__class__ is A.FnExpr` branch) then does the
  one thing v0.14.9 left as a placeholder: `self.param_call_scopes[-1][name]
  = expr.param_call_fact` instead of unconditionally `None` — the first
  point anywhere a NAME exists to key the fact by. `_check_call_site_param_
  effects` and `_resolve_param_call_fact` themselves needed **zero
  changes** — both already resolve through `param_call_scopes` generically,
  via the same innermost-first scope-stack walk every sibling resolver in
  this family uses, indifferent to whether a given frame's fact originated
  from a NAMED fn's own definition or a `let`-bound anonymous one.
- **`A.FnExpr` gains a new field, `param_call_fact`** — the ONLY AST
  change this round makes (still zero interpreter changes, zero new node
  TYPES): `whence/interp.py`'s `eval_FnExpr` reads `node.params`/
  `node.body`/`node.ret_type` by name already, so the new field is inert
  to it, and `A.FnExpr` has exactly one construction site in the codebase
  (`primary()`'s own `fn(...) {...}` branch), so updating its call needed
  no downstream ripple.
- **Deliberately still narrow**, unchanged from v0.14.9's own remaining
  boundaries: only a parameter called DIRECTLY (`f(...)`) is tracked, not
  one merely stored, returned, or passed to a THIRD function; only a
  bare-NameRef argument at the call site is inspected; forward-referenced
  or mutually-recursive fns are invisible; a fn expression used any way
  OTHER than `let NAME = fn(...) {...}` — called immediately without ever
  being bound to a name, passed straight through as someone else's
  argument, stored directly in a container/record field without an
  intervening `let` — still has no name to key `param_call_scopes` by and
  remains untracked. This is not a new gap: it is the same "nothing to
  check without SOME name" boundary this whole family has always had (a
  bare builtin passed inline, `total(fn(x){x})`, was never checkable
  either, for the identical reason).
- **Verification**: `tests/test_v14.py` 92 → **95 passed** (3 new: the
  basic grant/reject pair for a `let`-bound anonymous fn — inverting what
  had been `test_anon_fn_bound_by_let_param_call_is_not_tracked` into
  `test_anon_fn_bound_by_let_param_call_is_now_checked` — plus the
  no-clause-unrestricted case, the fact carrying forward through a plain
  rename, and shadowing by a same-named parameter).
  `examples/effects.lang` gained one new demo (`apply_logger_anon`, the
  `let`-bound mirror of v0.14.9's `apply_logger`): checks 10 → **11
  passed, 0 failed**. `tests/test_examples.py::test_effects` and `tests/
  test_self_hosting.py`'s guest-parity pin both updated to 11 checks — the
  guest needed **zero code change**, confirming the same "purely a host
  parse-time field, invisible to the guest evaluator" property v0.14.9
  already established (`self_eval.lang` builds its own record-shaped AST
  nodes entirely independently of the host's `whence/ast_nodes.py`, so a
  new host-only field on `A.FnExpr` is simply never visible to it).
  `run_tests_fast.sh`: 922 → **925 passed, 38 deselected** (+3 exact).
- **Still open, unchanged from v0.14.9's own remaining assessment**: an
  argument reaching an effectful builtin through a SECOND function call
  before landing in a directly-called param; a builtin flowing into a
  param that is stored/returned rather than called directly; the dynamic
  call graph (calling a different, unrestricted top-level fn that itself
  performs the effect), completely untouched. Fuzz coverage
  (`harness/swe/fuzz.py`) and oracle coverage
  (`harness/swe/alias_effects.py`) for the v0.14.9/v0.14.10
  argument-flow shape overall remain open, the same "ship the checker,
  name the fuzz gap, close it in a later dedicated round" rhythm every
  v0.14.x feature has followed. **Closed by round 305 (landed by round
  306) — see below.**

## v0.14.11 (round 306) — effect system: a param renamed inside its own fn body, then called through the rename

- **Closes HALF of v0.14.9's own explicitly-named remaining gap** ("a
  builtin flowing into a param that is stored... rather than called
  directly", unchanged through v0.14.10's own next-steps): `fn apply(f)
  effects [io] { let g = f\n g(1) }` then `apply(print)` is now checked
  exactly as `f(1)` itself already was — including through any number of
  further rename hops within the SAME open fn body (`let h = g` then
  `h(1)` too). The OTHER half of that gap — a param RETURNED to a
  caller, who then holds and calls the alias itself, rather than the
  fn's own body calling it — is a genuinely different, still fully open
  value-flow-ACROSS-A-RETURN-BOUNDARY mechanism (see the negative case in
  `tests/test_v14.py`'s `test_param_returned_then_called_by_caller_is_
  still_not_checked`).
- **Design**: a new, SEVENTH scope-stack, `Parser.param_alias_scopes`,
  pushed/popped at the identical three sites `param_call_scopes` already
  is (`stmt_list`'s per-block frame, plus the params-frame push at each
  of the two fn-definition sites). Each frame maps a name to either
  `None` or the ORIGINAL PARAM NAME (a key of `current_fn_params_frame_
  stack[-1]`) it is currently a pure `let`-rename of — set by a new
  branch in `statement()`'s own `let` handling (the existing `expr.
  __class__ is A.NameRef` rename branch): if the RHS resolves, by
  identity, to the currently-open fn's own params frame, record the RHS
  name directly; otherwise recurse through the new `_resolve_param_alias`
  resolver, so a rename-of-a-rename chains automatically. A new fallback
  in `_check_effect_call`'s own existing v0.14.9 tracking step — reached
  only when the EXISTING identity check (the base case, `f(1)` itself)
  finds no match — calls `_resolve_param_alias(callee.name)` and, if it
  resolves, records the ORIGINAL param name (not the rename) into
  `direct_param_calls_stack`, so `_check_call_site_param_effects`'s later
  per-call-site check sees no difference between calling `f` directly and
  calling it through any number of renames. **Zero AST changes** — unlike
  v0.14.10's own `A.FnExpr.param_call_fact` field, this is pure parser
  scope-stack bookkeeping, exactly like v0.14.9's own original mechanism.
- **The one genuine correctness subtlety this design had to get right**:
  `_resolve_param_alias` must never cross a FN-BODY boundary — a rename
  recorded in an ENCLOSING fn's own scope must not leak into a DIFFERENT,
  inner fn's own param-call fact, even via a coincidental name collision
  (`fn outer(p) { let g = p\n fn inner(g) effects [io] { g(1) } }` must
  check `inner`'s call against `inner`'s OWN param `g`, and must NOT
  spuriously attribute it to `outer`'s unrelated `p`, which isn't even
  one of `inner`'s own params). Fixed by locating `current_fn_params_
  frame_stack[-1]`'s own identity inside `alias_scopes` and bounding the
  `param_alias_scopes` walk to that index and everything pushed after it
  — pinned by `test_param_rename_in_enclosing_fn_not_misattributed_to_
  inner_fn`.
- **Deliberately still narrow**, same family discipline: only a rename
  WITHIN THE SAME OPEN FN BODY is tracked (a rename inside a nested
  block still counts, since `param_alias_scopes` is pushed/popped at the
  same per-block granularity as every sibling stack); a RETURNED param is
  still invisible (see above); an argument reaching an effectful builtin
  through a SECOND function call, and the dynamic call graph (calling a
  different, unrestricted top-level fn that itself performs the effect),
  remain completely untouched, unchanged in scope from every prior
  v0.14.x round's own assessment.
- **Verification**: `tests/test_v14.py` 95 → **100 passed** (5 new: the
  basic grant/reject pair, a two-hop rename chain, a nested-block
  shadowing case, the cross-fn-boundary misattribution guard, and the
  explicit negative case pinning the still-open "returned" half).
  `examples/effects.lang` gained one new demo (`apply_logger_renamed`):
  checks 11 → **12 passed, 0 failed**. `tests/test_examples.py::
  test_effects` and `tests/test_self_hosting.py`'s guest-parity pin both
  updated to 12 checks — the guest needed **zero code change**, the same
  "purely a host parse-time mechanism, invisible to the guest evaluator"
  property v0.14.9/v0.14.10 already established, this time even more
  directly since there is no new AST field at all to be inert to.
  `run_tests_fast.sh`: 925 → **930 passed, 38 deselected** (+5 exact).
  `pytest tests/test_examples.py tests/test_self_hosting.py`: 34 passed.
- **Still open**: everything named above under "deliberately still
  narrow"; fuzz coverage (`harness/swe/fuzz.py`) and oracle coverage
  (`harness/swe/alias_effects.py`) for this round's own new rename-chain
  shape specifically (round 305's fuzz/oracle work, landed alongside this
  round, covers only the v0.14.9/v0.14.10 direct-call shapes, not this
  round's rename extension) — the natural next SWE-loop(D) round, same
  "ship the checker, name the fuzz gap, close it later" rhythm.

## v0.14.12 (round 308) — effect system: a param RETURNED directly across a return boundary

- **Closes the OTHER half of v0.14.9's own explicitly-named "stored/
  returned" gap** — the half v0.14.11 (round 306) deliberately left fully
  open and pinned with a negative test: `fn apply(f) { f }` never calls its
  own param `f` at all, it just hands it back unchanged, so the CALLER ends
  up holding the alias itself. `let g = apply(print)\n g(1)` is now
  checked, exactly as `let g = print\n g(1)` already was — and so is the
  no-`let` chained form `apply(print)(1)`. `apply` itself needs **no
  `effects [...]` clause** — it never performs the effect, only returns a
  value that happens to carry one, the same reasoning `fn get_printer()
  effects []` already established for v0.14.3's own fixed return-value
  tracking. The check still fires exactly where it always has, at the
  CALLER's own `g(1)`, against the CALLER's own declared scope.
- **Design**: an EIGHTH scope-stack, `Parser.return_param_scopes`, pushed/
  popped at the identical sites `return_alias_scopes` already is
  (`stmt_list`'s per-block frame, plus the params-frame push at each of the
  two fn-definition sites). Each frame maps a name to `None` or
  `(params_tuple, tail_param_name)` — deliberately NOT the fn's own effects
  scope (unlike `param_call_scopes`), since `apply`'s own declaration is
  irrelevant to this check. Two new pieces make the fact argument-
  dependent, unlike every other fact in this family:
  - `A.Block` gained a THIRD field, `tail_param_name`, computed by
    `stmt_list` at the exact same point `tail_alias_tag` already is: for a
    bare-`NameRef` tail, does it name the currently-open fn's own param —
    directly (`_innermost_frame_containing`, the same identity check
    `_check_effect_call`'s own v0.14.9 block uses) or via a same-body
    rename chain (`_resolve_param_alias`, reused as-is from v0.14.11)? New
    helper `_tail_return_param_name` does exactly this, called from
    `stmt_list` right next to the existing `tail_tag` computation.
  - New resolver `_resolve_return_param_passthrough(fn_name, args)`
    combines a fn's own recorded fact (`_resolve_return_param_fact`, the
    `return_param_scopes` mirror of `_resolve_effectful_return`) with the
    ACTUAL arguments at a specific call site: finds the returned param's
    own position in the fn's param list, checks whether the argument AT
    that position is a bare NameRef resolving to an effectful alias, and
    if so returns that tag. Shared by the two places that need it —
    `statement()`'s own `let NAME = Call(...)` branch (as a fallback when
    `_resolve_effectful_return` itself misses, i.e. the callee never
    tail-returns a builtin directly, only one of its own params) and
    `_check_effect_call`'s own chained-call branch (`apply(print)(1)`,
    no intermediate `let`) — the same "one new resolver, two call sites"
    shape v0.14.3's own `_resolve_effectful_return` already established.
  - Once `g`'s own tag is recorded in the ordinary `alias_scopes` this way,
    `g(1)` itself needs **zero new dispatch code** — it is checked by
    `_check_effect_call`'s existing, unmodified bare-`NameRef` branch, the
    same one every other alias in this family already goes through.
- **Deliberately still narrow**, same family discipline: only a bare-
  NameRef tail is tracked — unlike `tail_alias_tag` (widened to if/else
  tails by v0.14.5), `tail_param_name` is NOT (`test_param_returned_via_
  if_else_tail_is_still_not_checked`); an argument flowing through a
  SECOND function call before reaching the return remains invisible
  (`test_param_passed_through_a_second_function_before_return_is_still_
  not_checked`, `identity(f)` inlined into `apply`'s own tail is a `Call`,
  not a bare `NameRef`); and the dynamic call graph (calling a different,
  unrestricted top-level fn that itself performs the effect) remains
  completely untouched.
- **Verification**: `tests/test_v14.py` 100 → **105 passed** (the prior
  round's own negative test, `test_param_returned_then_called_by_caller_
  is_still_not_checked`, is now REPLACED — not merely updated — by 6 new
  tests: the direct grant/deny pair, the no-`let` chained form, a rename-
  then-return variant, a multi-param positional-correctness check, and the
  two still-open negative cases named above). `examples/effects.lang`
  gained one new demo (`pass_through`/`log_total4`): checks 12 → **13
  passed, 0 failed**. `tests/test_examples.py::test_effects` and
  `tests/test_self_hosting.py`'s guest-parity pin both updated to 13
  checks — the guest needed **zero code change**, the third round in a row
  (v0.14.9/10/11/12) this exact family has been purely host parse-time
  bookkeeping invisible to the guest evaluator. `run_tests_fast.sh`: 930 →
  **935 passed, 38 deselected** (+5 exact). Full `pytest tests/`: 968 →
  **973 passed, 0 failed** (+5 exact, matching `test_v14.py`'s own net
  test-count change one-for-one — no other file's test count moved).
- **Still open**: everything named above under "deliberately still
  narrow"; fuzz coverage (`harness/swe/fuzz.py`) and oracle coverage
  (`harness/swe/alias_effects.py`) for this round's own new return-
  boundary shape specifically (still uncovered by round 305's fuzz/oracle
  work, which only reaches the v0.14.9/v0.14.10 direct-call shapes) — the
  natural next SWE-loop(D) round, following the exact same rhythm round
  305 itself set for v0.14.11.

## v0.14.13 (round 312) — effect system: an argument forwarded through a SECOND function call, then called directly

- **Closes the FIRST of the two gaps named across four consecutive
  language(C) rounds (302, 306, 308, 311) as needing "a real design
  sketch, not another small pre-scoped slice"**: an argument reaching an
  effectful builtin through a SECOND function call, before landing in a
  directly-called param. `fn inner(g) effects [io] { g(1) }` then `fn
  outer(f) effects [] { inner(f) }`: `outer`'s own body never calls `f`
  directly (or through a same-body rename/return — v0.14.9/11/12's own
  mechanisms), it FORWARDS `f` as `inner`'s own argument, and it is
  `inner`'s body, not `outer`'s, that actually calls it. `outer(print)`
  was invisible to every prior check, even though calling `outer` actually
  performs io.
- **The design insight that makes this tractable without a whole new
  fixed-point/interprocedural analysis**: `Parser.param_call_scopes`
  already records, for EVERY named fn (or `let`-bound anonymous one),
  "which of my own params does my body call directly" (v0.14.9) — a fact
  fully resolved by the time that fn's OWN body finishes parsing, strictly
  BEFORE any caller of it can be parsed (single left-to-right pass,
  forward refs already invisible everywhere else in this family). So when
  `outer`'s body itself calls `inner(f)`, checking whether `f` (or a
  same-body rename of it) lands in one of `inner`'s own DIRECTLY-called
  param positions is enough: if it does, `outer` ITSELF now also counts as
  "calling `f` directly" for the purposes of `outer`'s OWN `param_call_
  scopes` entry — recorded into the exact same `direct_param_calls_
  stack[-1]` v0.14.9's leading block already populates. `_check_call_
  site_param_effects` needed **zero changes**: it already walks
  `_resolve_param_call_fact("outer")` generically, indifferent to whether
  `f`'s membership in `outer`'s own `called_params` came from a direct
  call, a same-body rename, or (now) a one-level-removed forward.
- **This composes to ARBITRARY depth for free** — the same "record once,
  read at every later call site" discipline `param_call_scopes` already
  relies on for everything else in this family: if `innermost(h) effects
  [io] { h(1) }`, `inner(g) effects [io] { innermost(g) }`, `outer(f)
  effects [io] { inner(f) }` are declared in that (bottom-up) textual
  order, `inner`'s own `param_call_scopes` entry already reflects the
  forward through `innermost` by the time `outer`'s body is parsed, so
  `outer`'s own forward-through-`inner` check transitively picks it up
  too — no explicit recursion needed, single-pass composition does it
  automatically (`test_param_forwarding_composes_transitively_through_
  three_hops`). Declaration order still matters exactly as much as it
  already does everywhere else: a forward reference, or a genuinely
  (mutually) recursive chain, is invisible, unchanged in scope from every
  prior v0.14.x round.
- **Design**: a new method, `_check_param_forwarding(callee, args, tok)`,
  called from `postfix()` alongside `_check_effect_call`/`_check_call_
  site_param_effects` at every call expression. For a callee with a
  recorded `param_call_fact`, it walks each of the target fn's own
  DIRECTLY-called param positions; if the argument AT that position
  resolves (identity, or a same-body rename chain) to one of the
  CURRENTLY open fn's own params, that param is added to the CURRENT fn's
  own `direct_param_calls_stack[-1]` — the exact same set v0.14.9's
  leading block populates for a truly direct call, v0.14.11's for a
  same-body rename. **Zero new scope-stack**, unlike every prior addition
  in this family (v0.14.4/6/7/9/11/12 each added a new stack) — this is
  pure composition of a fact this family already computes.
  `_resolve_current_fn_param(name)` is a new shared helper, factored out
  of the identical "innermost-first frame-identity check, else fall back
  to `_resolve_param_alias`" logic that was duplicated between `_check_
  effect_call`'s own leading v0.14.9 block and `_tail_return_param_name`
  (v0.14.12) — this round's own new forwarding check is a third caller,
  applied to a call's ARGUMENTS instead of its callee or a block's tail.
- **Deliberately still narrow**, the same "one hop, bare NameRef only"
  discipline as every sibling check: only a call whose callee is a bare
  NameRef with a recorded `param_call_fact` is inspected; only an
  ARGUMENT that is itself a bare NameRef (or a same-body rename chain of
  one) is checked (`test_param_forwarding_via_non_nameref_argument_
  still_not_checked`); a param that is FORWARDED then RETURNED (or
  renamed, or forwarded a second time) by the callee, not called, remains
  invisible — v0.14.12's `return_param_scopes` and this mechanism are
  still two genuinely separate mechanisms, not unified
  (`test_param_forwarding_does_not_disturb_returned_param_mechanism`).
  Shadowing is correct (`test_param_forwarding_shadowed_name_is_not_
  misattributed`), and only the correct positional argument is matched
  (`test_param_forwarding_only_correct_position_is_matched`).
- **The dynamic call graph — the OTHER named gap, and now the ONLY one
  left — is a fundamentally different, larger problem, not touched by
  this round.** This is worth stating precisely, since it is easy to
  conflate with the gap just closed: `_check_param_forwarding` composes a
  DATA-FLOW fact (which of my params reach a directly-called sink) across
  one function-call hop, transitively, for free — but every fact in this
  entire v0.14.x family, from v0.14 (round 146) onward, has been
  DELIBERATELY shallow in exactly one further sense, stated in v0.14's own
  original design comment above and never revisited since: **a `effects
  [...]` declaration vouches ONLY for that function's own textual body —
  calling a DIFFERENT, unrestricted function that itself performs an
  effect DIRECTLY (no param, no forwarding, no aliasing of any kind
  involved) is untouched by the caller's own declaration.** `fn helper()
  effects [io] { print(1) }` then `fn outer() effects [] { helper() }` —
  `outer`'s own body never mentions `print`, `f`, or ANY tracked alias at
  all; it just calls `helper`, an ordinary, unrestricted call this
  parser's `_check_effect_call` has never inspected the CALLEE's own
  effects scope for (only whether the callee itself IS, or resolves to,
  an effectful alias). Running `outer()` does perform io (via `helper`),
  yet `outer`'s own `effects []` never gets checked against it.
  - **Why this is NOT the same shape as v0.14.13's own forwarding
    fix, and could not be closed the same way**: `_check_param_
    forwarding`'s whole design rests on `param_call_scopes` recording a
    fact ABOUT A SPECIFIC PARAMETER — "if you call me with an effectful
    value in this slot, that effect fires." `helper()` above takes NO
    parameters at all; its effect is UNCONDITIONAL, baked into its own
    body, not data-dependent on anything the caller supplies. There is no
    per-parameter fact to compose here — the only fact that could possibly
    make `outer() effects []` reject `helper()` is "does `helper`'s own
    resolved effects scope contain an effect `outer`'s own declared scope
    does not" — a comparison between TWO FUNCTIONS' OWN DECLARED SCOPES,
    not between a scope and a specific argument's tracked tag. Every other
    check in this family (`_check_effect_call`, `_check_call_site_param_
    effects`, `_check_param_forwarding`) ultimately bottoms out at
    "compare ONE effect tag against ONE scope"; this would be the family's
    first check comparing scope-against-scope.
  - **What a real design would need, sketched honestly (not implemented,
    not this round's scope)**: two structurally different approaches exist.
    1. **Declared-superset propagation** (closer to this family's existing
       "declared, not inferred" philosophy): at the point a NAMED fn's own
       `effects [...]` clause is resolved, additionally require its scope
       to be a superset of every OTHER named fn it calls DIRECTLY (not
       through a param — an ordinary `helper()` call where `helper` is a
       plain NameRef resolving to a fn definition with ITS OWN already-
       resolved scope). Bottom-up declaration order (the same constraint
       already binding every fact in this family) makes a single left-
       to-right pass sufficient for a strict call DAG — by the time
       `outer`'s own clause is resolved, `helper`'s is already known.
       Recursive or mutually-recursive fns break this (`helper` calling
       `outer` calling `helper`) and would need real fixed-point
       iteration over the call graph — a genuinely bigger algorithmic
       class than anything else in v0.14.x, all of which is single-pass.
    2. **Full effect inference** (NOT declared, INFERRED bottom-up per fn,
       closer to Hindley-Milner-style type inference than anything in
       this family): drop the requirement that a fn's `effects [...]`
       clause be validated against its OWN body at all, and instead
       compute the TIGHTEST possible effect set for every fn automatically
       from its transitive call graph, using the explicit clause (where
       present) only as a additional assertion checked against the
       inferred result. This is a substantially larger feature — a
       different point in the design space from "effects are declared,
       checked against local facts" to "effects are computed" — and would
       likely warrant its own top-level version bump (`v0.15`-class), not
       a `v0.14.x` point release, given how much of this family's own
       design (declared scope as ground truth, no inference) it would
       have to revisit.
    Recommendation for whichever future round takes this on: approach (1)
    is the natural next step if the goal stays "extend this existing
    family," since it reuses the same single-pass, declaration-order
    discipline every other v0.14.x fact already assumes, and only needs
    ONE new comparison (scope-vs-scope at a plain call site) plus an
    explicit call-graph-cycle detector (to correctly refuse — not
    silently approve, not crash — a recursive/mutual pair, the one case
    single-pass composition cannot resolve). Approach (2) is a genuinely
    separate, much larger research question and should not be scoped
    into a single round without first being explicitly chosen over (1).
- **Verification**: `tests/test_v14.py` 105 → **113 passed** (8 new: the
  direct grant/deny pair, a 3-hop transitive-composition pair, a
  let-bound-anonymous-fn-target case, a rename-before-forward case, a
  shadow-safety case, a positional-correctness case, a non-NameRef-
  argument negative case, and a restated regression pin for the
  still-open return-boundary-via-second-call gap).
  `examples/effects.lang`: 13 → **14 checks passed**, new
  `apply_logger_via` demo (forwards `f` into `apply_logger`'s own
  directly-called argument). `tests/test_examples.py::test_effects`/
  `tests/test_self_hosting.py`'s guest-parity pin both updated to 14 —
  **zero guest code change**, the fifth round in a row (v0.14.9/10/11/
  12/13) this family has been purely host parse-time bookkeeping (no new
  AST field at all this round, unlike v0.14.10's `A.FnExpr.param_call_
  fact` or v0.14.12's `A.Block.tail_param_name`). `run_tests_fast.sh`:
  935 → **943 passed, 38 deselected** (+8 exact). Full `pytest tests/`:
  973 → **981 passed, 0 failed** (+8 exact, matching `test_v14.py`'s own
  net test-count change one-for-one). `bench/ref_diff.py --counters
  examples/*.lang`: 0 differing pairs, `effects.lang` reads `checks=14`
  identically across direct/fast/slow. Cross-track: `bash harness/
  run_tests_fast.sh` unchanged from round 311's own post-landing
  baseline.
- **Still open**: the dynamic call graph (sketched above, deliberately
  NOT attempted this round — a fundamentally different, larger feature
  than every fact-composition slice that came before it, needing its own
  future round with the approach choice made explicit); fuzz coverage
  (`harness/swe/fuzz.py`) and oracle coverage (`harness/swe/alias_
  effects.py`) for this round's own new forwarding shape — the natural
  next SWE-loop(D) round, following the exact rhythm round 311 itself set
  for v0.14.11/v0.14.12.

## v0.14.14 (round 314) — the dynamic call graph gap: investigated, NOT
## a bug, this section's own predecessor's "approach 1" is unshippable

- **This round set out to close the dynamic call graph gap using
  "approach 1" from v0.14.13's own design sketch above (declared-superset
  propagation): at every plain call site `helper(...)`, require the
  CURRENTLY enclosing fn's own resolved `effects [...]` scope to be a
  superset of `helper`'s own resolved scope. Implemented it in full**
  (a ninth scope-stack, `Parser.fn_effects_scopes`, mirroring `param_call_
  scopes`'s own push/pop/placeholder discipline exactly; a new resolver
  `_resolve_fn_effects_scope`; a new check `_check_call_graph_effects`,
  wired into `postfix()` alongside the other three call-site checks; a new
  `A.FnExpr.fn_effects_scope` field for the anonymous-fn case) — **and
  then reverted all of it**, after `tests/test_v14.py` fell from 113 to
  105 passed (8 failures), because the failures are not bugs in the new
  code; they are the new code correctly implementing a rule the rest of
  this family has never held and has actively, deliberately tested
  AGAINST since the effect system's own first round.
- **The founding evidence, from v0.14 itself (round 146, the very top of
  this file's own effect-system section, unchanged in eleven point
  releases since)**: "A declaration vouches ONLY for calls made directly,
  textually, in that function's own body. A nested `fn` defined inside a
  restricted body is a SEPARATE closure with its own (absent, hence
  unrestricted) declaration and may print freely, even lexically inside
  an `effects []` function (`test_nested_undeclared_fn_escapes_outer_
  purity` ...). Calling a DIFFERENT, unrestricted function that itself
  prints is likewise untouched by the caller's declaration." This is not
  a scoping accident later rounds forgot to widen — it is the ORIGINAL,
  DELIBERATE, EXPLICITLY-NAMED design boundary of the entire feature,
  pinned by a test whose own name (`test_nested_undeclared_fn_escapes_
  outer_purity`) says exactly what it guards, cited by name in round
  146's own SPEC text. Round 312's own v0.14.13 section (above) described
  this as a "gap" needing a "real design sketch" — it is not a gap; it is
  the feature working exactly as designed and tested since round 146.
  Restoring the reverted code would have shipped a regression against
  this round's own founding test, not closed a hole in it.
- **A second, independent confirmation, from v0.14.9 itself (round 300)**:
  `test_check_uses_callees_own_scope_not_the_callers` states the same
  principle from the OTHER direction, for the param-argument-flow
  mechanism this whole v0.14.9-13 sub-family is built on: "The check is
  against `apply`'s OWN declared effects scope, not the CALLING scope's
  ... An unrestricted top-level call site may freely call `apply(print)`
  as long as `apply` ITSELF permits `io`." A function's own `effects
  [...]` clause is a SELF-CONTAINED, already-verified contract (checked
  once, at that function's own definition, against its own body/params);
  calling a fn whose contract is satisfied is always safe, REGARDLESS of
  the caller's own declared scope — the caller is not "performing" the
  callee's effect merely by delegating to an already-verified unit, only
  by naming an effectful builtin (or a tracked alias/return/forward of
  one) DIRECTLY in its own textual body. This is the same "one settle
  point, not full call-graph composition" discipline v0.13's return-type
  check established first (round 146's own SPEC text again) — the effect
  system was never meant to be transitive.
- **Concretely, seven of the eight failures were TRUE FALSE POSITIVES**
  under the reverted check — previously-legal, already-tested programs
  it would newly reject, all of the identical shape ("a NAMED fn with its
  own EXPLICIT, sufficient `effects [...]` clause, called from a more
  tightly-scoped enclosing fn"): `test_nested_undeclared_fn_escapes_
  outer_purity`, `test_three_way_nested_escape`, `test_inner_fn_with_
  same_param_name_is_checked_against_its_own_scope`'s second `all_ok`
  block, `test_param_rename_in_enclosing_fn_not_misattributed_to_inner_
  fn`, `test_param_forwarding_shadowed_name_is_not_misattributed`,
  `test_param_forwarding_only_correct_position_is_matched`, `test_param_
  forwarding_via_non_nameref_argument_still_not_checked`. The eighth
  (`test_param_forwarded_to_second_function_that_calls_it_is_now_
  checked`) was not a false positive (both the old and new code reject
  the program) but a diagnostic regression: the new check fires EARLIER
  and UNCONDITIONALLY (at the inner call's own parse time, independent of
  which argument is ever passed), preempting `_check_call_site_param_
  effects`'s own argument-dependent message and error location with a
  different one — proof the new check does not compose with the existing
  argument-flow mechanisms so much as race and shadow them.
- **Why "approach 1" specifically, not just this implementation, is the
  problem**: the family already has a well-established, load-bearing
  distinction between two genuinely different questions — "is THIS
  function's own declared scope internally consistent with what its own
  body/params actually reach" (checked once, at definition time, by
  `_check_effect_call`/`_check_call_site_param_effects`/`_check_param_
  forwarding`, all scoped to the CALLEE) and "does calling this function
  require something the CALLER did not declare" (a question this family
  has never asked, on purpose, since round 146). Declared-superset
  propagation collapses these into one question by construction — there
  is no narrower version of "compare caller's scope to callee's scope at
  every call site" that avoids re-litigating the first question the
  family already answered differently for the param-flow cases. A
  genuinely SOUND transitive effect check would need to replace, not
  compose with, `_check_call_site_param_effects`/`_check_param_
  forwarding`'s own "callee's own scope is the only thing that matters"
  design — a `v0.15`-class rewrite of the whole family's philosophy
  (approach 2 from v0.14.13's own sketch, full effect inference), not a
  point release alongside it. (v0.15 itself already denotes `guess`/
  confidence, round 168, below — a real future attempt at this would need
  a different major slot, e.g. `v0.17`.)
- **Backlog correction**: the "dynamic call graph" item, carried as an
  open backlog line across rounds 270/302/306/308/311/312, is CLOSED as
  of this round — not by implementation, but by determining it describes
  the effect system's own founding, deliberate, still-correctly-tested
  scope boundary, not an accidental gap. No future language(C) round
  should re-attempt "approach 1" against this family without first
  either (a) accepting it will break the seven tests named above and
  updating them to match a genuinely NEW, transitive semantics (a real,
  intentional breaking redesign — not appropriate as a quiet v0.14.x
  point release), or (b) scoping a real "approach 2" (full bottom-up
  effect inference) as its own explicit, large, multi-round feature.
- **No code, test, or example changed this round** — `git diff` over
  `whence/parser.py`/`whence/ast_nodes.py` is empty after the revert;
  `tests/test_v14.py` is confirmed back at 113 passed. This section (and
  `knowledge/round-314-...md`) is the round's own entire output: a
  verified correction to round 312's own design sketch, reached by
  actually implementing it, running the existing suite, and reading what
  the failures were actually saying instead of patching them to pass.

## v0.15 (round 168) — AI-native primitives: `guess`/confidence
- **The curriculum's last open "advanced feature" slot** (structural types
  v0.12, return types v0.13, effects v0.14 all shipped; round 146 itself
  flagged AI-native primitives as unscoped). Scope decided this round:
  model **uncertainty** — an LLM's defining property, "an answer, but not
  a guaranteed one" — as a first-class value, symmetric to how `miss`
  already models **absence**. Where a `miss` is "no answer, and here is
  why," a `guess` is "an answer, but here is how sure": `guess(value,
  confidence, source)` wraps any value with a confidence in `[0, 1]` and a
  free-text source label (`"model"`, `"sampled"`, whatever the caller's
  own provenance for the number is — Whence does not itself talk to a
  model; it gives a caller who does somewhere a value shape to report the
  result *in*).
- **New payload type, not a tagged record.** `shape`/structural types
  (v0.12) could have modeled this as `@{__tag: "guess", value: v,
  confidence: c}` with zero interpreter change — and that was seriously
  considered, then rejected: a tagged record is INERT. `record + record`
  is already a miss regardless of tags, so `guess(3, 0.9, "m") + 1` would
  have to be written point-free (`sure(g, 0.5) + 1`) every single time,
  which defeats the actual point of an AI-native primitive — that
  uncertainty should be threadable through ordinary arithmetic like `miss`
  already threads through it, not something you must manually unwrap
  before every use. That threading is the one thing a plain record cannot
  give you without operator overloading Whence does not have, so `Guess`
  is a real `values.py` class (mirroring `Miss`'s own shape exactly:
  `__slots__`, a dedup-and-order constructor for `sources`/`Miss.reasons`)
  and the interpreter's binary/unary op dispatch was extended, in exactly
  the two places that dispatch is centralized (see below).
- **Propagation rule: WEAKEST-LINK confidence (`min`), not an average.**
  `Interpreter._guess_binop` (`interp.py`) unwraps any Guess operand to
  its underlying node, computes the op AS IF both sides were certain via
  a plain recursive `self.binop(...)` call, then rewraps the result in a
  fresh `Guess` at `min()` of every contributing confidence, with sources
  unioned (deduped, ordered, mirrors `Miss.reasons`). A chain of five
  0.9-confidence additions is a 0.9-confidence sum, not a 0.59-confidence
  one (`0.9**5`) or a 0.9-confidence one via averaging that hides how many
  guesses actually went in — `min` is the only combinator under which "an
  answer is only as certain as its LEAST certain input" holds regardless
  of chain length, the same reason a `miss` chain does not need a decay
  function either. `_unary` (`-`/`not`) gets the identical treatment,
  recursing once on the unwrapped node.
- **A genuine type error stays a miss, never becomes an uncertain
  success.** `guess("x", 0.9, "model") + 5` computes `"x" + 5` on the
  unwrapped operands first; that is `mk_miss("cannot add str and num",
  ...)` under ordinary rules, and `_guess_binop` checks for exactly this
  (`isinstance(result.value, Miss)`) and returns it UNCHANGED rather than
  wrapping it in a `Guess` — a confidence score vouches for how sure you
  are of a valid answer, it cannot launder an invalid computation into a
  low-confidence one. Symmetric with `_check_ret` (v0.13) "a result that
  is already a miss propagates unchanged, before any inspection."
- **`==`/`!=` on a bare Guess go through `_guess_binop` too, not
  `deep_eq` — a genuinely different rule from structural equality
  elsewhere.** `1 == guess(1, 0.9, "model")` unwraps, computes `1 == 1`
  (True, certain), then rewraps: the RESULT is `guess(true, 0.9,
  "model")`, a Guess about whether they are equal, not a plain `true`.
  You cannot get a bare boolean out of comparing against an uncertain
  value without resolving the uncertainty first (`sure(...)` — see
  below) — the same discipline that already applies to arithmetic,
  applied to comparison for consistency, not because it was free. This is
  DELIBERATELY asymmetric with what happens when a Guess sits *inside* a
  container: `[guess(1, 0.9, "m")] == [guess(1, 0.9, "m")]` reaches
  `deep_eq` for the outer list-vs-list compare (neither top-level operand
  IS a Guess, both are lists), which recurses into elements and hits a
  new `deep_eq` case comparing two Guesses' underlying values only,
  IGNORING confidence/source — because `deep_eq` backs `contains`/`find`/
  structural-equality-as-a-utility, where "are these the same answer" is
  the useful question, not "how sure was each side." Two different
  questions, two different answers, both documented in `interp.py` at
  their respective call sites (`_guess_binop`'s docstring, `deep_eq`'s new
  `elif isinstance(l, Guess) and isinstance(r, Guess)` branch) precisely
  because the asymmetry is easy to mistake for a bug if it isn't spelled
  out.
- **`sure(v, threshold)` is the one way out, and a universal escape
  hatch, not a guess-only operation.** `sure` on a plain (non-Guess) value
  is a no-op pass-through — ordinary code can call `sure(x, 0.8)`
  defensively without checking `is_guess(x)` first, the same "total,
  works on anything" discipline `missed`/`matches`/`shapeof` already
  have. On a Guess: confidence `>=` threshold returns the ORIGINAL
  underlying node, pass-through, no new provenance step (mirrors `typed`'s
  own "no new node on a match" convention exactly) — so `sure()`ing a
  guess back down to a definite value is truly transparent, not lossy;
  below threshold is `mk_miss("guess confidence C below threshold T
  (sources)", ...)`, an ordinary miss that then propagates like any other.
- **Deliberately shallow, same discipline as v0.12–14 — costs ZERO extra
  code, not merely undocumented:** indexing (`_index`), field access
  (`_field`), and call dispatch do not recognize `Guess` as a
  list/record/callable, so `guess([1,2], 0.9, "m")[0]` is an ordinary
  "cannot index guess 0.9 (\"m\"): [1, 2]" miss — `sure()` first, same as
  any other wrong-shape value — for FREE, because those functions already
  fall through to their existing "unrecognized payload" miss branch via
  `show_payload` (which gained a `Guess` case for exactly this reason,
  `values.py::_show`). `and`/`or`/`if` are equally untouched
  (`_logic_left`, `_logic_right`, `_if_bad`): a Guess is not a `bool`, so
  those already-existing "needs true/false, got %s" misses fire
  unmodified, `show_payload` again doing the rendering work. Only
  arithmetic, comparison, and unary negation/`not` were actually touched;
  everything else "supports" Guess only in the sense that it fails
  helpfully instead of crashing, which every payload type already got for
  free from the total-by-construction interpreter.
- **`shapeof`/`typed`/`matches` integration is one line each.** `_kind`
  (`interp.py`) gained `(Guess, "guess")` in `_KIND_ORDER`, and
  `PRIMITIVE_TYPES` (`parser.py`) gained `"guess"` — so `fn f(a: guess) {
  ... }` is a real, working type contract ("this parameter must still
  carry a confidence score; committing it is the callee's job"), erased
  by the existing v0.12 machinery with no new code path.
- **New builtins** (all in `interp.py`'s builtin table, `guess`/
  `is_guess`/`confidence`/`sure`): `guess(value, confidence, source)`
  (arity 3, propagates a miss `value`/`confidence`/`source`; validates
  confidence is a num in `[0, 1]` and source is a str; a `guess` of an
  already-`Guess` value FLATTENS rather than nests — `min` of the two
  confidences, sources unioned — the same "never wrap a Miss around a
  Miss" discipline `merge_miss` already has for the sibling type);
  `is_guess(v)` (arity 1, total, mirrors `matches`); `confidence(v)`
  (arity 1, a miss "not a guess" on anything else); `sure(v, threshold)`
  (arity 2, described above).
- **New example `examples/guess.lang`** and `tests/test_v15.py`
  (mirroring `test_v14.py`'s structure): weakest-link confidence through
  a chain of arithmetic, a genuine type error staying a miss even with
  guessed operands, `sure()`'s pass-through-on-success/miss-on-shortfall
  both ways, the non-Guess-is-always-sure no-op, `guess`-of-`guess`
  flattening, `is_guess`/`confidence`/`shapeof`/`typed` integration, the
  `==`-vs-`deep_eq` asymmetry pinned explicitly both ways (bare compare
  vs. compare-inside-a-list), and `assert_three_way` cases confirming fast
  /direct/trampoline agree byte-for-byte on Guess-carrying programs (no
  reason to expect disagreement — `_guess_binop`/`_unary` sit in the
  SHARED dispatch both the generator and fast/direct-compiled paths
  eventually call through, the same reason v0.14 needed zero interpreter
  change at all worked out in v0.15's favor here too, just one level
  removed: the compiled `f_add`/`f_sub`/… closures inline only the
  int/float/str hot paths and fall through to `binop()` for anything
  else, so a `Guess` operand reaches the exact same `_guess_binop` call
  regardless of which path evaluated it, with no separate fast-path
  copy to keep in sync).
- **Guest parity: shipped round 176** (was "not started" through round
  168-174; see the subsection below) — the fastest a feature has closed
  its guest-parity gap yet (`: Type`/`-> Type` took from round 122/126 to
  round 158; `effects` from round 146 to round 164).

### v0.15 guest parity (round 176)
- **A guest Guess IS the host's own `Guess` payload, not a hand-rolled
  tagged record.** `self_eval.lang`'s `apply_host_builtin` delegates
  `guess`/`is_guess`/`confidence`/`sure` straight to the real host
  builtins (the guest passes its already-unboxed `.v` payload through),
  so arithmetic/comparison on a guest Guess reuses the host's own
  `_guess_binop`/`_unary` propagation for free — no Whence-source
  reimplementation of weakest-link confidence or source-unioning was
  needed or possible (the guest has no accessor for a Guess's raw
  `.sources`/`.node`).
- **The cost of that shortcut: every "does v look like a T" probe
  (`is_num`/`is_list`/`is_bool`/`is_str`) had to be Guess-guarded first**,
  because Guess arithmetic is transparent by design — `guess(5, .9, "s") +
  0` succeeds, so `is_num` would otherwise misreport a Guess-wrapped
  number as a plain num. `is_guess_val` is checked before all four, and
  `guest_kind` checks it immediately after `missed`.
- **`==`/`!=` on a bare guest Guess bypass the guest's own `guest_eq`
  comparator on purpose** and delegate to the host's real `==`/`!=`
  (which return a NEW Guess wrapping the boolean, per the host's own
  `==`-vs-`deep_eq` asymmetry) — every other operator needs no guest-side
  change at all, since `a.v OP b.v` in `apply_binop` is already real
  top-level Whence source running under the true host interpreter.
  `raw_deep_eq` gained its own separate Guess-vs-Guess case (compares the
  unwrapped answer via `sure(_, 0)` only, ignoring confidence/sources —
  mirroring the host `deep_eq`'s own case, used when a Guess sits inside a
  container rather than at top level).
- **Round 194 fixed a guest parity bug the round-176 work above shipped**,
  found by the why-shape differential fuzzer (seed 9205): `sure([], 0.0)` —
  a plain, non-Guess value, threshold irrelevant — diverged, guest op
  `literal` vs host ops `{let, list}`. The host's `sure` (`b_sure`) is a
  PASS-THROUGH when its value was never a Guess ("already certain: `sure`
  is a no-op escape hatch") — no new provenance node at all, so `let v =
  sure([], 0.0)` derives exactly the same two nodes as `let v = []`. Before
  this fix `sure` fell to `apply_builtin`'s generic catch-all, which always
  synthesizes a fresh "sure" box regardless of whether the host did.
  `sure` moved out of the generic `guess`/`is_guess`/`confidence`/`sure`
  delegation group (that group's own no-closure-guard comment was corrected
  accordingly) into its own `apply_builtin` branch with an explicit
  pass-through case, mirroring `typed`'s existing shape. The Guess-ABOVE-
  threshold pass-through case (unwraps to `g.node` on the host) was left
  NOT special-cased at the time — no fuzzer finding on that path yet, and
  a Guess arriving already-flattened (re-guessed, or threaded through a
  function parameter) has no local guest box to point at.
- **Round 234 closed that gap, plus a second one found alongside it, by
  direct construction rather than waiting on the fuzzer**: `sure`/`guess`
  are absent from `harness/swe/guest.py`'s `WHY_VOCAB`, and the ops the
  old code DID leak that are in that vocabulary (`literal`) already
  legitimately appear elsewhere in the host derivation — so the
  differential fuzzer's containment-only probe could never have caught
  either gap regardless of run count, a real, now-understood blind spot
  in the probe design, not bad luck. Fixed:
  - **below threshold**: host `mk_miss(..., inputs=(v,))` keeps only the
    VALUE's own derivation, never the threshold's; the old guest code
    wrapped with both, one spurious extra `literal` leaf every time.
  - **above threshold**: new `unwrap_guess_box` (`self_eval.lang`, next
    to `is_guess_val`) reconstructs the box for `g.node` purely from
    guest box structure — no new host accessor needed. It walks
    single-input wrapper boxes (`let NAME`/`arg NAME`/a plain `call`
    result all thread their one real value through unchanged) down to
    the box whose op is literally `"guess"`, takes ITS first argument
    (exactly what `b_guess` stored as `.node`), and repeats if that
    argument is itself still a Guess (mirrors `b_guess`'s own
    guess-of-guess flattening). A box with more than one `ins` element
    (a real `call`/`if`/tail-loop merge) falls back to returning the box
    unchanged — the same imperfect-but-safe behaviour this file used
    everywhere before this round, not a new failure mode.
  - Verified with a stronger check than containment: exact op-LIST
    equality (not just "no guest-only tokens") across six shapes — direct
    above/below threshold, a `let`-chain, a function-parameter hop (both
    above and below threshold), and guess-of-guess flattening — all six
    match host and guest token-for-token
    (`test_guest_sure_why_shape_matches_host_exactly_including_flattening`,
    `tests/test_self_hosting.py`). See `knowledge/round-234-whence-guest-sure-why-shape-parity-and-spec-staleness.md`.
- **`"guess"` joined `guest_primitive_types`** (both `self_eval.lang` and
  `self_host.lang`, which must stay byte-identical in their shared
  parser section — `test_parser_section_matches_self_host` pins the line
  range) so `fn f(x: guess)` type-checks on the guest exactly as it does
  on the host.
- **`harness/swe/guest.py`'s guest-differential fuzzer/oracle gained
  matching support**: the `BANNED` line-filter no longer strips
  `guess`/`is_guess`/`confidence`/`sure` calls (they were banned
  outright when this feature shipped with zero guest support, round
  168/174), and the `agree()` comparator gained a Guess-vs-Guess case
  that checks confidence/sources exactly (a stronger check than
  `deep_eq`'s answer-only comparison, deliberately — this oracle is
  hunting for guest bugs, not backing a utility function). A 300-sample
  differential fuzz run found 0 mismatches; `test_self_eval.py` gained a
  dedicated `show_payload`-based test confirming confidence/sources
  render identically host-vs-guest (a check `deep_eq`-based agreement
  alone cannot make, since `deep_eq` treats them as pure metadata).
- **Round 251's guest-targeted campaign (seed 1940) found a fresh gap in the
  same why-shape family, and round 252 closed it (plus a sibling it
  exposed)**: `binop`/`_unary`'s host-side Guess handling
  (`Interpreter._guess_binop`/`_unary`, `whence/interp.py`) is ASYMMETRIC —
  a Guess operand that makes the op SUCCEED keeps the ORIGINAL operand
  node(s) as the result's inputs (the outer "guess"-labelled node
  included), but a Guess operand that makes the op MISS (ordering a Guess
  against an incompatible type, dividing by zero, negating a Guess-wrapped
  string, `not` on a Guess-wrapped number, …) uses whatever the plain
  op-without-Guess-handling built from the Guess's UNWRAPPED inner node
  (`Guess.node`) instead — the outer "guess" node is silently dropped, so
  the host's own why-tree for that miss never mentions "guess" at all.
  `self_eval.lang`'s `apply_binop`/`eval_unary` boxed their inputs
  uniformly (`mkb(p, op, [a, b])` / `mkb(p, op, [r.v])`) regardless of this
  asymmetry, leaking a "guess" op into the guest's why-tree for a
  miss that the host's real derivation never has. Fixed with a shared
  `guess_unwrap_if_missed(a, p)` helper (reusing `sure()`'s own
  `unwrap_guess_box`, round 234) applied per-operand, but ONLY when the
  result missed — a succeeding Guess propagation keeps the original box(es)
  unchanged, matching the host's success path exactly. The unary half
  (`-`/`not` on a Guess) was never fuzzed (the differential generator's
  grammar has no unary-on-Guess template) and was found by checking the
  sibling code path for the same bug class once the binop finding was
  root-caused, not by a fresh campaign finding. Verified with exact op-LIST
  equality (not just containment) across 9 shapes: `>` miss with the Guess
  on either side, guess-of-guess ordering miss, divide-by-zero miss, a
  success control (original boxes kept), unary `-` on a Guess-string miss,
  unary `not` on a Guess-num miss, and two unary success controls
  (`test_guest_binop_guess_operand_miss_why_shape_matches_host_exactly`,
  `test_guest_unary_guess_operand_miss_why_shape_matches_host_exactly`,
  `tests/test_self_hosting.py`). See
  `knowledge/round-252-whence-guess-binop-unary-why-shape-parity.md`.

## v0.16 (round 204) — persistent records (structural sharing for `Record`)
- **The fix round 200 flagged and left as optional backlog.** `Record` was
  a thin wrapper around a plain Python `dict`; every `put` (`b_put`,
  `whence/interp.py`) did `fields = dict(r.payload.fields); fields[k] = v`
  — a full shallow copy of the CURRENT store on every single call. Since
  `derived(...)` keeps a node's `inputs` (including the superseded store)
  reachable forever — by design, `why`/`steps` must be able to trace back
  through it — N sequential `put`s onto a growing store costs O(N) each
  with the store growing ~linearly in N: O(N^2) cumulative allocation by
  construction, and every intermediate copy stays live. Round 200 measured
  this directly (`self_host.lang`'s own 66-check test section, run through
  `self_eval.lang`'s guest evaluator, passed 700 MB/1.2 GB `RLIMIT_AS`
  caps by checkpoint 35/40) but declined to fix it (no curriculum driver
  at the time, a real but nontrivial change).
- **What was built**: `whence.values.PMap`, a persistent (immutable) AVL
  tree keyed by string, giving `Record` the same treatment `WList` (v0.6)
  already gives lists. `put(k, v)` returns a NEW map allocating only the
  O(log n) nodes on the path from the root to `k`'s position —every
  sibling subtree is the SAME object as before, shared, not copied. `get`/
  `__contains__`/`__len__`/`items()`/`keys()` round-trip through the same
  dict-shaped API every existing call site already used (`in`,
  `fields[name]`, `.get(...)`, `.items()`, `set(fields)`, `sorted(fields)`,
  `len(fields)`) — no call site needed new methods except the two that
  used to hand-roll the copy: `b_put` now does
  `r.payload.fields.put(name, v)` and `merge` does
  `a.payload.fields.merged_with(b.payload.fields)` (`other` wins on
  shared keys, same as the old `dict.update` semantics). `Record.__init__`
  accepts either a plain dict (record literals, tests — built via
  `PMap.from_dict`, a one-time O(k log k) cost for the literal's own small,
  fixed field count) or an already-built `PMap` (the `put`/`merged_with`
  fast path — stored directly, no extra copy at the `Record` layer).
  Field order was never semantically meaningful to begin with — every
  display site already did `sorted(p.fields.items())` and equality is
  set-based — so `PMap`'s key-ordered iteration is not a behaviour change,
  just a faster way to reach the same order. No delete is needed (Whence
  records never lose a field), which keeps the AVL logic to the classic
  insert-only rotations.
- **Verification.** `tests/test_v16.py` (15 new tests): `PMap` unit tests
  differential against a plain dict (including a branch-from-a-snapshot
  case that only makes sense for a persistent structure — two divergent
  futures from the same shared prefix, both reading back correctly);
  `Record` integration tests (construction from a dict vs. a `PMap`,
  `put`-chain-via-real-language-builtins, `merge` conflict semantics,
  three-way fast/direct/slow parity on a long `put` chain, and a check
  that a record's OWN provenance `inputs` still come from the literal's
  DECLARED order, not `PMap`'s key order — the two are orthogonal, this
  round only changed the latter). Full suite 865/865 (850 + 15). Whole-repo
  differential (`bench/ref_diff.py --counters`, direct/fast/slow ×
  every example, binding/check/output counts) against the pre-round-204
  `HEAD`: 0 differing (file, mode) pairs — behaviour is byte-identical.
- **`bench/pmap_scaling.py`** isolates the asymptotic claim from the
  self-hosting harness's noisier end-to-end numbers (parsing, lexing, the
  guest evaluator itself all mixed in there): N sequential `put`s onto a
  record with N ~distinct keys (matching the real store-growth shape,
  NOT a small fixed key set — repeatedly overwriting a handful of keys
  keeps the old `dict`-copy approach linear, not quadratic, so the
  benchmark has to grow the store to be a fair comparison), every
  intermediate version retained in a list (mirrors provenance retention).
  Old (`dict` copy) vs new (`PMap`), same N: 200 → 0.0035s/0.0055s,
  400 → 0.020s/0.011s, 800 → 0.081s/0.038s, 1600 → 0.30s/0.050s,
  3200 → 0.61s/0.116s — old grows quadratically (16x N from 200→3200,
  ~174x time, close to the 256x a pure O(N^2) would predict), new grows
  close to N log N (~21x time for 16x N). A 12800-point run was attempted
  and killed by the OOM reaper (exit 137) — retaining ALL versions of a
  dict that reaches thousands of entries is itself O(N^2) MEMORY
  regardless of which map implementation is under it (each of the N
  retained versions has its own O(N)-sized flat dict), a reminder that
  this microbenchmark's "keep every version in a Python list" is a
  deliberately pessimistic stand-in for provenance retention, not
  something to push arbitrarily far on a memory-constrained box.
- **A real, honestly-reported trade-off, not a pure win**: re-running
  `bench/self_host_memscale.py` (round 200's own tool) shows the memory
  curve is now dramatically flatter — checkpoint 20 (`self_host.lang`'s
  real test section through the guest evaluator) peaks at 119 MB vs round
  200's 198 MB, checkpoint 25 at 121 MB vs 259 MB — but checkpoint 30
  TIMED OUT at the script's default 60s wall clock (elapsed was already
  climbing: 12.4s → 14.1s → 17.7s → 25.6s → 29.8s for checkpoints
  5/10/15/20/25, roughly 2x round 200's elapsed at the same checkpoints).
  Root cause: a Python-level AVL node allocation (attribute reads on two
  child pointers, height/size arithmetic, a `_pinsert` recursive call per
  tree level) costs far more per operation in constant-factor terms than
  a single C-level `dict.copy()` + `__setitem__`, which is exactly the
  operation it replaced. At the store sizes this specific harness
  actually reaches, the O(log n)-vs-O(1)-per-op difference does not (yet)
  outweigh the constant-factor gap — this is the textbook trade-off every
  real persistent data structure makes (Clojure's/Scala's persistent maps
  are slower per-operation than a mutable hash map for exactly this
  reason), not a bug in this implementation. See round 204's knowledge
  file for the full re-run at a longer timeout and the net verdict.

## v0.16.1 (round 206) — guest parity: `steps` in `self_eval.lang`
- **The bug round 204 found and flagged.** Getting further into
  `self_host.lang`'s test section than any previous round (its own
  checkpoint 47, `parse_whence(...)` on a small recursive function, then
  `check "guest AST is itself a real Whence value with its own history":
  not missed(p7) and len(steps(p7)) > 0`) failed under the deep
  guest-EVALUATOR level (`self_eval.lang`'s `run_src`) — but passed fine
  when the SAME `parse_whence`/`steps` call ran at the shallower
  direct/host level (self_eval.lang's own functions executed directly by
  the host, no `run_src` involved: 743 real steps). The two levels
  disagreeing pointed at `run_src`'s own machinery, not `parse_whence`.
- **Root cause, once isolated with a 12-second targeted repro (library
  text + ONE `steps(p7)` call, skipping the other 46 checkpoint-47
  checkpoints' cost) instead of replaying the whole slow checkpoint**:
  `steps` was never in `self_eval.lang`'s `builtin_names` list at all — so
  a guest program calling `steps(...)` failed at NAME RESOLUTION
  (`lookup`'s "unbound name 'steps'"), never even reaching `apply_builtin`/
  `apply_host_builtin`'s dispatch tables. This is a materially different
  failure than "arity mismatch" or "not implemented in the guest" (the
  two outcomes `apply_builtin`/`apply_host_builtin` are actually built to
  produce for a recognized-but-unsupported name) — the whole "provenance
  as data" (round 4) builtin family (`steps`, `at`, `blame`, `diverge`,
  `contrast`) was simply invisible to the guest's own name resolver,
  because no prior self-hosting round's test corpus had ever called one
  of them from GUEST-evaluated code before checkpoint 47 existed.
- **The fix**: add `"steps"` to `builtin_names` (so `new_store()` seeds a
  real builtin-ref binding for it) and `steps: -1` to `arities` (reusing
  the same "1 or 2 args" sentinel `range` already uses, matching the
  host's own `@register("steps", (1, 2))`), then delegate straight to the
  REAL host `steps` builtin in `apply_host_builtin`:
  `else if name == "steps" { if len(args) == 1 { steps(a0) } else { steps(a0, (args[1]).v) } }`.
  This is the exact same "free delegation" trick round 176 used for
  `guess`/`is_guess`/`confidence`/`sure`: `a0` (`args[0].v`, the guest
  box's own payload) is not a synthetic guest structure — it is a REAL
  host Whence value, because every guest `put`/`merge`/record-literal
  self_eval.lang's own evaluator performs to build the guest AST is
  itself a real host builtin call with real host provenance. `steps`
  walking `a0` therefore reflects genuine (if much larger — see below)
  history, for free, with zero guest-side reimplementation of
  `walk_steps`. Deliberately NOT added to the `propagating` list: like
  `is_guess`, `steps` (and `blame`) are explicitly TOTAL on the host
  (`interp.py`'s own comment: "these are total: they work on misses —
  that is the point") — an argument miss must reach the real `steps` call
  so it can walk the MISS's own history, not get short-circuited into a
  generic "builtin"-op miss first.
- **Why `at`/`blame`/`diverge`/`contrast` are NOT fixed alongside this**:
  same family, same fix shape, but nothing in the current test corpus
  exercises them from guest code, so shipping untested guest dispatch for
  them would violate this project's own testing discipline. Flagged as
  the natural, narrowly-scoped follow-up if a future round's self-hosting
  work needs one of them.
- **Why the differential fuzzer's `BANNED` list keeps `steps` banned even
  though the guest now supports it** (unlike `guess`/`confidence`, which
  round 176 DID unban): `harness/swe/guest.py`'s oracle compares bare
  PAYLOAD values between host-direct and guest-mediated execution, and
  `len(steps(x))` (or `steps(x)` itself) is a direct readout of
  provenance GRAPH SIZE — which legitimately, permanently differs between
  the two execution modes, because `self_eval.lang`'s own interpreter
  loop adds many more real host Prov nodes per guest operation (every
  guest `put`/`merge`/field-access is itself an additional real host
  builtin call) than a host directly evaluating the same expression would.
  A Guess's confidence float or a `sure()` boolean outcome does not have
  this problem (provenance-shape-independent); a step COUNT does. Unbanning
  it would manufacture false "divergence" findings on nearly any
  nontrivial fuzzed program — not a language bug, an inherent, permanent
  cost of self-hosting layering (documented alongside `guest.py`'s
  existing `depth_skew`/miss-reason-wording exemptions).
- **Verification**: `tests/test_self_hosting.py` gained the exact
  self_host.lang check (line 651-652) as a 5th assertion inside
  `test_guest_evaluator_executes_self_host_library` (now passes), plus a
  new `test_guest_steps_two_arg_pattern_and_total_on_miss` covering the
  2-arg pattern-filter form and the miss-is-total guarantee — neither was
  exercised anywhere before this round. Full suite 866/866 (865 + 1 new
  test function). Host fuzz (seed 401, n=300), oracle campaign (seed 402,
  n=200 × 6 oracles), and guest-differential campaign (seed 403, n=150,
  `steps` still banned so unaffected by construction) all clean: 0 unique
  finding signatures. `bench/ref_diff.py --counters` re-run against the
  pre-round-206 tree. **Also confirmed, NOT caused by this round** (two
  pre-existing `harness/tests/test_swe_guest.py` failures found while
  running the wider suite, isolated against a clean git-HEAD copy of
  `languages/whence` before attributing): seed 4002's `effects`-guest
  divergence (flagged since round 167/171, still open) and a NEW-to-this-
  investigation seed-152 `why_shape` guest divergence on a `guess`-family
  program (`guest-only ops: ['literal']` vs `host ops: ['let', 'list',
  'miss']`) both reproduce identically on `HEAD` with none of this
  round's or round 204's changes applied — see
  `knowledge/round-206-whence-v16-guest-steps-parity.md` §5.

## v0.16.2 (round 210, landed by round 212) — closing both seed-152/seed-4002 guest divergences
- **Seed-152 (`why_shape`)**: `self_eval.lang`'s `eval_unary` "miss" branch
  unconditionally kept the reason operand as a why-input
  (`mkb(miss r.v.v, "miss", [r.v])`) for every `miss <expr>`. The real host
  (`interp.py`'s `_miss_lit`) only keeps that input when the reason is
  itself a miss (propagation) or a valid string; a non-string, non-miss
  reason (e.g. `miss 1`) discards the operand and produces a fresh 0-input
  miss node. The guest's unconditional version invented a `"literal"` op
  the host derivation never has for that third case. Fixed to match the
  host's own three-way branch (`if missed(r.v.v) or is_str(r.v.v) { ... }
  else { mkb(miss r.v.v, "miss", []) }`); pinned with a dedicated why-shape
  op-walk test (`tests/test_self_hosting.py::
  test_guest_miss_unary_why_shape_matches_host_for_all_three_reason_kinds`)
  since a plain value-level `check` in `self_eval.lang` itself cannot see
  an input-COUNT difference, only a value difference.
- **Seed-4002 (`effects`)**: guest recursion deep enough to reach the
  HOST's own recursion-depth guard mid-chain — inside `self_eval.lang`'s
  own `eval`/`exec_stmt`/`apply`/`apply_closure` recursion, not the guest
  program's own call depth as such — got back a bare miss where that
  chain's own code unconditionally expects an `@{v:.., st:..}` store
  record, corrupting the WHOLE guest store into a miss and cascading false
  "unbound name" failures through every later statement. Fixed with a
  guest-level function-CALL depth ceiling, `GUEST_MAX_DEPTH = 400`, tracked
  as `st.gd` (threaded through `new_store`/`alloc`/`apply_closure`'s
  return) and checked ONLY in `apply_closure` — the single choke point
  every GUEST call passes through (`self_eval.lang`'s own internal
  statement-sequencing recursion never reaches `apply_closure`, so it's
  unaffected). Picked with a wide safety margin under the host's own
  effective ceiling (~1300 guest levels at ~15 host frames/guest call): no
  example or self-hosting corpus this project has ever run comes close to
  400 real guest-level call frames. Past the ceiling, `apply_closure`
  returns a well-formed miss (blaming the over-deep call by name and
  depth) with the CALLER's own still-good store untouched, instead of
  silently corrupting the store.
- **Verification**: full `languages/whence` suite 867/867 (was 866 + this
  round's 1 new test); `tests/test_self_eval.py`'s example-run count
  updated 102→103 (`self_eval.lang`'s own self-test corpus gained one
  check: `"guest miss with non-string reason still misses"`). The wider
  `harness/tests/test_swe_guest.py` differential suite: 44/44 (was 2
  failures pre-fix). Both flagged seeds directly re-probed via
  `swe.guest.oracle_self_eval` — seed 152 and seed 4002 both now return
  `ok` (were `mismatch`). A fresh 100-program guest-fuzz campaign (seed
  401, `swe.guest` CLI): 0 unique finding signatures.
- **History note**: round 210 built and tested this fix but was killed
  mid-flight (the recurring outer-driver-timeout pattern — see
  `research-state.md`'s harness(A) entry) before it could commit or write
  a knowledge file. Round 212 found it sitting as an unstaged, uncommitted
  diff, re-verified everything from a clean read of the diff (not by
  trusting any prior round's own narration, per this session's standing
  discipline), and landed it. See
  `knowledge/round-212-whence-r210-reconciliation-seed152-seed4002-closure.md`.

## v0.16.3 (round 216) — self-hosting round 8: `steps`'s real memory cost, first full 66/66-check completion
- **Falsified hypothesis, kept in the record on purpose**: `bench/
  self_host_memscale.py` (round 200/204's fresh-subprocess, `RLIMIT_AS`-
  capped memory-scaling tool) reran under the default 700 MB cap and
  failed at checkpoint 50 with `MEMORY_ERROR` at ~703 MB, where round 204's
  own table reported 310 MB for the identical checkpoint. First hypothesis
  — round 210/212's `GUEST_MAX_DEPTH` depth-guard fix added two extra
  `merge` calls per guest closure call (entry/exit `st.gd` bookkeeping),
  plausibly ~doubling retained store versions — was tested with a
  controlled A/B (identical host `interp.py`/`values.py`, `self_eval.lang`
  swapped between its pre-/post-round-210 versions) and **refuted**: both
  versions failed within 0.2 MB of each other (701.7 MB vs 701.5 MB) at
  checkpoint 50, ruling out the depth guard as the cause.
- **Real cause, found by testing one commit further back**: swapping in
  the TRUE round-204-era `self_eval.lang` (pre-round-206, before `steps`
  had a working guest builtin) reproduced round 204's own historical
  numbers almost exactly (checkpoint 45: 234.4 MB vs round 204's 234 MB;
  checkpoint 50: 310.3 MB vs round 204's 310 MB). The difference is round
  206's `steps` guest-parity fix: `self_host.lang`'s checkpoint-47 check
  (`len(steps(p2)) > 0`) failed with a cheap, immediate "unbound name"
  miss before round 206 — round 204's own checkpoint-47-and-later readings
  never actually exercised a working `steps` call. Once `steps` really
  runs (round 206 onward), it walks the FULL host-level provenance graph
  reachable from its argument, exactly as round 206's own writeup
  predicted ("much larger... for free, with zero guest-side
  reimplementation") but never quantified: a one-time jump from 282.7 MB
  (checkpoint 46) to 690.3 MB (checkpoint 47), after which growth resumes
  the same roughly-linear per-check slope as before.
- **Not a regression to fix** — `steps` genuinely working (vs. silently
  failing name resolution) is round 206's whole point; the memory cost is
  an honest, expected consequence of a real provenance walk over
  guest-multiplied host nodes, the same "not a pure win, but a real
  trade-off" framing round 204 used for `PMap`'s own elapsed-time cost.
- **New milestone**: with the cap raised to 1200 MB (round 216, informed
  by this measurement — see `bench/self_host_memscale.py`'s updated
  module docstring for the full curve and reasoning), the complete
  66-check `self_host.lang` test section now runs end-to-end through the
  deep guest-EVALUATOR level (`run_src`) for the FIRST TIME ever: 66/66
  checks passing, 1072 MB peak, ~112-122 s (two independent runs). Every
  prior round (192/198/200/204) either killed the run early or hit the
  wall-clock/memory ceiling before completion.
- **Verification**: no host code (`interp.py`/`values.py`) or guest code
  (`self_eval.lang`/`self_host.lang`) changed this round — this is a
  measurement-and-tooling round only (`bench/self_host_memscale.py`'s
  default cap/timeout and docstring updated to match reality). Full
  `languages/whence` suite reconfirmed green post-change (unaffected by
  construction, since no interpreter or example file was touched).

## v0.16.4 (round 218) — guest parity: `at`/`blame`/`diverge`/`contrast` in `self_eval.lang`
- **Closes the follow-up backlog round 206 explicitly flagged and declined
  to build**: `at`/`blame`/`diverge`/`contrast` are the same "provenance as
  data" (round 4) builtin family as `steps`, share the exact same gap —
  never in `self_eval.lang`'s `builtin_names`, so guest code calling one
  failed at NAME RESOLUTION before ever reaching `apply_builtin`/
  `apply_host_builtin`'s dispatch tables — and get the identical fix.
  Round 206 explicitly declined to build them alongside `steps` because
  nothing in the test corpus exercised them from guest code yet
  ("evaluate-before-authoring"); `self_host.lang`'s own source still calls
  none of them, so this round wrote the exercising tests FIRST (making the
  gap real, per the same discipline) before fixing it.
- **The fix**: add `"at"`, `"blame"`, `"diverge"`, `"contrast"` to
  `builtin_names`, arities `at: 2, blame: 1, diverge: -1, contrast: -1`
  (matching the host's own `@register` arities — `diverge`/`contrast` reuse
  the `-1` "1 or 2 args" sentinel `steps`/`range` already use), then
  delegate straight to the real host builtin of the same name in
  `apply_host_builtin`, exactly `steps`'s own free-delegation shape:
  `a0` (`args[0].v`) is already a real host Whence value with real host
  provenance (every guest `put`/`merge`/record-literal call
  `self_eval.lang`'s own evaluator performs is a real host builtin call),
  so `at`/`blame`/`diverge`/`contrast` walking it costs zero guest-side
  reimplementation. None of the four were added to `propagating` — like
  `steps`, host `interp.py` documents this whole family as TOTAL (a miss
  argument must reach the real builtin so it can walk the miss's own
  history, not get short-circuited into a generic "builtin"-op miss).
- **A real representational wrinkle found while writing the tests, left
  unfixed as out-of-scope**: indexing into a `steps(...)`/`blame(...)`
  result list from GUEST code and then field-accessing an element (e.g.
  `steps(x)[0].op`) returns a MISS, not the expected step-record field —
  `eval_index`'s `is_list((o.v).v)` branch passes list elements through
  UNBOXED (bare host `Record`s shaped `{op, detail, line, show, depth,
  inputs, count, value}`), but every other guest field-access path expects
  the `{v, op, ins}` "guest box" shape, so `.op` looks for a `v` field that
  isn't there. Round 206's own `test_guest_steps_two_arg_pattern_and_total_
  on_miss` had already sidestepped this by only ever comparing `len(...)`
  of two step lists, never indexing an element — this round's tests follow
  the same discipline for the same reason, and do not fix the underlying
  boxing mismatch (a real design question — should `_step_record`'s guest-
  visible list elements get `mkb`-wrapped? — with no corpus need yet to
  force an answer either way). Flagged as backlog if a future round's
  guest code actually needs to introspect individual step records.
- **A second wrinkle, informing the tests' design**: the REAL host
  provenance reachable from a guest value under `run_src` reflects
  `self_eval.lang`'s OWN internal call chain (its parameter names like
  `arg p`, its own eval helpers), not the guest program's syntax — e.g.
  `diverge(1 + 2, 1 + 2)` (the identical literal, evaluated twice) still
  reports one origin, because the two evaluations run through different
  internal paths inside `self_eval.lang` itself, not because the GUEST
  values differ. Confirmed empirically before writing any assertion (see
  the round-218 knowledge file for the raw numbers). Test assertions below
  therefore avoid exact-pattern-match and same-vs-different-divergence-
  count claims, and instead pin only properties true regardless of that
  internal noise.
- **Why the differential fuzzer's `BANNED` list needs no change**:
  `harness/swe/guest.py`'s `BANNED` regex already listed `at`, `blame`,
  `diverge`, `contrast` alongside `steps`, `why`, `snip`, `print` — banned
  from the START (well before any of them had a working guest dispatch),
  for the identical "graph size legitimately, permanently differs between
  host-direct and guest-mediated execution" reason round 206 documented
  for `steps`. Confirmed unaffected by this round's change (still banned,
  by construction, from the fuzzed/oracle/guest-differential campaigns).
- **Verification**: `tests/test_self_hosting.py` gained two new tests —
  `test_guest_at_blame_diverge_contrast_dispatch_to_real_host_builtins`
  (proves the real host builtin runs, via the real "no step named ..."
  miss wording `at` produces on a not-found search — a pre-fix guest call
  would instead hit the generic "not implemented in the guest" stub
  message, so seeing the real host wording is a genuine differential
  proof, not just "didn't crash") and
  `test_guest_at_blame_diverge_contrast_total_on_miss_arguments` (pins
  `at`'s specific total-vs-propagating split: its VALUE argument being a
  miss still gets a real search, but its PATTERN argument being a miss
  DOES propagate via `merge_miss`, matching host `b_at`; `diverge`/
  `contrast` stay total on either side). Full `languages/whence` suite
  869/869 (867 + 2 new test functions); `tests/test_self_hosting.py` alone
  7/7 (was 5/5). `harness/tests/test_swe_guest.py`'s two pre-existing,
  unrelated divergences (seed-152/seed-4002) closed by round 210/212 stay
  closed — reconfirmed, not touched by this round.

## v0.16.5 (round 222, landed by round 223) — guest parity: `steps`/`blame`/`diverge` list-element field access in `self_eval.lang`
- **Closes the "real representational wrinkle" v0.16.4 found and explicitly
  left as backlog**: guest code that indexes a `steps(...)`/`blame(...)`/
  `diverge(...)` result list and reads a field off an element (e.g.
  `steps(x)[0].op`) read as a miss ("no field 'v' (record has: count,
  depth, detail, inputs, line, op, show, value)") even though `steps(x)`
  itself and `len(steps(x))` both worked. Root cause: `eval_index`'s
  `is_list((o.v).v)` branch passes list elements through UNBOXED — correct
  for guest-*built* lists (their elements are already `{v, op, ins}` boxes,
  since guest expressions always produce boxes), wrong for these three
  builtins' elements, which are raw host `Record`s (`_step_record`'s
  `{op, detail, line, show, depth, inputs, count, value}` for
  `steps`/`blame`; a second, structurally different `{kind, a, b[, which]}`
  shape for `diverge`, whose `a`/`b` nest a `_step_record` one level down)
  — correct at the HOST level, where field access reads a `Record`
  directly with no box convention, but never boxed for guest consumption.
- **The fix**: `box_step_record(rec)` in `self_eval.lang` re-boxes each of
  the 8 `_step_record` fields individually (`mkb(rec.op, "step", [])` etc.
  — a fixed `"step"` op label and empty `ins`, since no real guest-visible
  derivation happened inside the bridge; mirrors how `range`/`key`/
  `reason` list elements are already labelled a few lines above).
  `box_diverge_record(rec)` handles the second shape by boxing `kind`/
  `which` directly and calling `box_step_record` on the nested `a`/`b`.
  Both wired into the same post-`apply_host_builtin` list-mapping branch
  `range`/`keys`/`reasons` already used (`else if name == "steps" or
  name == "blame" { map(fn(x) { mkb(box_step_record(x), "step", []) }, p) }`
  and the `diverge` analogue).
- **Note: `at`'s single-node result and `contrast`'s string result need no
  equivalent fix.** `contrast`'s payload is always a string (a rendered
  report), never a list of records, so no boxing question arises.
  `at(v, pattern)` returns a single history node rather than a list, so
  `eval_index`'s list-passthrough branch never applies to it; whether a
  successful `at()` match's own payload is guest-box-shaped depends on
  *where inside `self_eval.lang`'s own internal call chain* the match
  landed (see v0.16.4's "internal noise" note below) — not a new gap this
  round found or fixed. Confirmed empirically while investigating this fix
  (round 224): `at(x, "let x")` against a guest `let x = @{...}` record
  literal returns a MISS (`missed(found)` is `True`), the same "doesn't
  find the guest-syntax match" property v0.16.4 already documented for
  `diverge(1+2, 1+2)` — so `found.a` reading as a miss afterward is a miss
  propagating through field access as designed, not a boxing defect.
- **Verification**: new test
  `test_guest_steps_blame_diverge_element_field_access` (`tests/
  test_self_hosting.py`) indexes an element AND reads multiple fields off
  it for all three builtins (not just `len(...)`, which is all v0.16.1/
  v0.16.4's own tests exercised) — every field read a miss pre-fix, so
  this is real exercising code, not a retroactive pin. `tests/
  test_self_hosting.py` 43/43 (was 41). Full `languages/whence` suite
  green. `harness/swe/guest.py`'s `BANNED` regex needs no change (already
  excludes `steps`/`at`/`blame`/`diverge`/`contrast` from the fuzzed
  differential corpus, unaffected by construction).
- Round 222 built and tested this but was killed by the driver's own outer
  wall-clock timeout mid-round (`tool_calls=87`, well under the max-turns
  cap — a genuine wall-clock kill, not a crash or a turn-budget death) and
  left it uncommitted with no knowledge file; round 223 (harness A track)
  verified fresh from a clean read and landed it as commit `8c6aeeb`; round
  224 backfilled this SPEC.md section, which neither round's own track
  mandate covered (223 was harness work, 222 never reached documentation
  before being killed). See `knowledge/round-223-harness-round222-landing-
  and-second-timeout-kill-counterexample.md` §1 for the landing detail and
  `knowledge/round-224-whence-matches-shapeof-guest-parity.md` for this
  round's own verification.

## v0.16.6 (round 224) — guest parity: `matches`/`shapeof` in `self_eval.lang`
- **A fresh instance of the same gap class rounds 206/218 already found and
  fixed for the rest of the "introspection" builtin surface, found by
  auditing `self_eval.lang`'s `builtin_names` against the host's full
  `## Builtins` list below** (not flagged by any prior round, since neither
  builtin is exercised by `self_host.lang`'s own source or by the
  differential fuzzer's generator grammar — `harness/swe/fuzz.py` never
  emits a `matches`/`shapeof` call, so this gap was entirely invisible to
  every regression campaign run to date): `matches`/`shapeof` (v0.12
  structural types) were never added to `builtin_names` at all, so guest
  code calling either failed at NAME RESOLUTION ("unbound name"), never
  reaching `apply_builtin`/`apply_host_builtin`'s dispatch tables.
- **The fix**: `"matches"`/`"shapeof"` added to `builtin_names` and
  `arities` (`matches: 2, shapeof: 1`, matching the host's own `@register`
  arities), dispatched in `apply_host_builtin` via the same free-delegation
  trick `steps`/`at`/`blame`/`diverge`/`contrast` already use — both are
  TOTAL (host `b_matches`/`b_shapeof` are documented "like `missed`: never
  itself a miss") and return scalar payloads (a bool / a kind string), so
  no list-of-records post-processing is needed the way `steps`/`blame`/
  `diverge` (v0.16.5 above) required.
- **One real wrinkle found empirically, before writing any test, that pure
  free-delegation would have missed**: a GUEST closure is an ordinary
  tagged `Record` under the hood (`self_eval.lang`'s own `is_callable`
  guard, used a few branches above to keep `len`/`keys`/`put`/`merge`/
  `has` opaque on functions), not a real host `Closure`/`Builtin` Python
  object — so undguarded delegation to host `shapeof`/`matches` reports
  `"record"` for a guest function's shape, never `"fn"`. Unlike the
  `len`/`keys` guard (where the right guest answer is a miss — "of a
  function" makes no sense), `shapeof`'s entire job IS reporting shape, so
  silently mislabelling a function as a record would be a real,
  user-visible correctness bug in the fix itself, not a cosmetic gap left
  for later. Fixed with an explicit `is_callable(a0)` branch ahead of the
  delegation (`shapeof`: `"fn"` outright; `matches`: `is_str(spec) and
  (spec == "any" or spec == "fn")`), the same split `typed`'s own
  `guest_type_ok` already uses for its own callable case two branches
  above — found by testing every `_KIND_ORDER` shape (`num`/`str`/`bool`/
  `list`/`record`/`miss`/`guess`/`fn`) individually rather than assuming
  scalar delegation would just work once dispatch was wired up.
- **A narrower caveat, flagged here but NOT left unfixed** (stale-note
  correction, round 318): the paragraph in this spot used to predict that
  a STRUCTURAL `Record` spec matched against a guest RECORD value would
  "misbehave" (mismatch every nested check, since `_type_match` would
  recurse into a `{v, op, ins}` box instead of a raw value) and left it as
  a "no corpus need yet" backlog item. Round 240 found the real failure
  mode was WORSE than predicted — `_type_match`'s recursion hits a box
  with no `.value` attribute and raises an uncaught host `AttributeError`,
  a "never raises" discipline violation, not just a wrong boolean — and
  fixed it the same round by deep-`strip()`-ing both the value and the
  spec (when the spec is not a plain string) before delegating to the real
  host `matches`, so both sides reach `_type_match` in the plain, unboxed
  shape it already assumes. `typed`'s own guest implementation is
  unaffected (still only supports a plain string spec) since nothing has
  ever needed to lift that separately. See `tests/test_self_hosting.py::
  test_guest_matches_structural_record_spec_does_not_crash_the_host` and
  `knowledge/round-240-whence-guest-matches-structural-spec-crash.md`.
- **Verification**: new test
  `test_guest_matches_shapeof_dispatch_and_callable_guard` (`tests/
  test_self_hosting.py`) — 15 checks covering every `_KIND_ORDER` shape for
  `shapeof`, the total-on-miss property and an `"any"`/mismatching-spec
  pair for `matches`, and the callable-guard branch for both builtins
  explicitly (not just name resolution succeeding). `tests/
  test_self_hosting.py` 44/44 (was 43). Full `languages/whence` suite
  green (871/871: 869 baseline + round 222's own +1 landed by round 223,
  +1 this round). `harness/swe/guest.py`'s `BANNED` regex needs no
  addition for these two — unlike `steps`/`at`/`blame`/`diverge`/
  `contrast`, `matches`/`shapeof` report a value's own SHAPE, a property
  that is identical between host-direct and guest-mediated execution of
  the same program (a number's kind doesn't depend on which internal call
  chain computed it), so there is no "legitimate but noisy divergence"
  concern to suppress — confirmed moot in practice since the fuzzer's
  generator grammar never emits either builtin anyway. Fresh regression
  campaigns re-run this round before AND after the fix (fuzz seed 501,
  oracles seed 503, guest seed 502): 0 unique finding signatures in all
  three, both passes.
- See `knowledge/round-224-whence-matches-shapeof-guest-parity.md`.

## Builtins

Until round 349 this section was a bare list of 36 names with no argument
order anywhere in the document, and an operator bug report against v0.19
turned out to be exactly that gap: `fold(nums, 0, fn(acc, x) { acc + x })`
was reported as "`fold()` returns Miss instead of calculated values with
inline lambdas". It does not. Whence's higher-order builtins take the
FUNCTION FIRST — `fold(fn, acc, xs)`, like `map(fn, xs)` and `filter(fn,
xs)` — so that call passed a list where a function goes, and the miss said
so precisely (`miss: fold needs a list, got <fn>`). Written the documented
way it folds inline lambdas and named functions alike. The signature was
never wrong; it was never written down.

Argument names below are the interpreter's own, and since **v0.22** they
are a DECLARATION rather than a reading: `register(name, arity, sig)`
(`whence/interp.py`) records each builtin's parameter names and argument
kinds in `_BUILTIN_SIGS`, because `_order_hint` needs them at run time —
and `tests/test_spec_builtins.py` machine-checks this table's arities AND
its argument lists against that same declaration. Round 349 could only
check the two things the registry knew (the name and the arity), so the
column that had actually caused the bug report — the parameter ORDER —
was still unchecked prose: `fold(fn, acc, xs)` could have been written
`fold(acc, fn, xs)` here and every test would have passed.

| builtin | signature | notes |
| --- | --- | --- |
| `print` | `print(v)` | effectful (v0.14.2) |
| `rand` | `rand()` | effectful (v0.14.8) |
| `len` | `len(v)` | list, text or record |
| `range` | `range(hi)` / `range(lo, hi)` | 1 or 2 args |
| `map` | `map(fn, xs)` | **fn first** |
| `filter` | `filter(fn, xs)` | **fn first** |
| `fold` | `fold(fn, acc, xs)` | **fn first**, then the seed, then the list |
| `find` | `find(fn, xs)` | **fn first** |
| `push` | `push(xs, x)` | list first — the reverse of the four above |
| `str` | `str(v)` | full rendering: a miss lists its reasons, a `why` renders its tree, a string is itself |
| `show` | `show(v)` | v0.29 — the SNAPSHOT rendering miss messages are built from: one line, bounded, a miss is `miss`, a `why` is `<why>`, a string is quoted |
| `num` | `num(text)` | Whence number syntax only; see "Limits" |
| `abs` | `abs(n)` | |
| `sqrt` | `sqrt(n)` | |
| `trunc` | `trunc(n)` | |
| `missed` | `missed(v)` | |
| `reasons` | `reasons(v)` | |
| `note` | `note(label, v)` | label first |
| `contains` | `contains(hay, needle)` | haystack first |
| `join` | `join(xs, sep)` | |
| `keys` | `keys(r)` | |
| `merge` | `merge(a, b)` | |
| `get` | `get(r, name)` | |
| `has` | `has(r, name)` | |
| `put` | `put(r, name, v)` | |
| `typed` | `typed(value, spec, label)` | v0.20 names the field that missed |
| `matches` | `matches(value, spec)` | |
| `shapeof` | `shapeof(v)` | |
| `guess` | `guess(value, conf, source)` | |
| `is_guess` | `is_guess(v)` | |
| `confidence` | `confidence(v)` | |
| `sure` | `sure(v, threshold)` | |
| `steps` | `steps(v)` / `steps(v, pat)` | 1 or 2 args |
| `at` | `at(v, pat)` | |
| `blame` | `blame(v)` | |
| `diverge` | `diverge(a, b)` / `diverge(runs)` | two values, or one list of runs |
| `contrast` | `contrast(a, b)` / `contrast(runs)` | two values, or one list of runs |

Where two spellings are given the builtin accepts an argument-count RANGE,
not two fixed shapes: `@register`'s arity tuple is `(min, max)` and
`_arity_ok` tests `min <= n <= max`. Passing a count inside the range but a
value the handler cannot use is a miss, not an arity error — `contrast(a)`
answers `contrast needs two values or a list of runs`, while
`contrast(a, b, pat)` answers `contrast expects 1..2 args, got 3`.

### Blocks are always braced

The other half of the same operator report: `if` / `else` branches require
an explicit `{ ... }` block. There is no single-statement form.

```
if x > 3 { print("big") } else { print("small") }   # ok
if x > 3 print("big")                               # error, v0.22 wording:
#   expected '{', got 'print' (blocks are always braced:
#   `if c { a } else { b }`, `fn f(x) { x }`) at line 2, col 10
```

This is not a v0.19 tightening — it is how the grammar has always read, and
the parser has always said so in those words. The rule holds for `fn`
bodies too. *(Round 349's sentence here also said "and `while` bodies";
Whence has no `while` — `lexer.KEYWORDS` is 14 words and that is not one of
them, and `while i < 3 { i }` is not even a parse error: it parses as
THREE statements — `while`, `i < 3`, `{ i }` — of which the first is an
unbound name. Corrected round 354.)*

**v0.22** appends the rule itself to the message, which is what the block
above now shows. The operator's report also asked whether older scripts
should be auto-fixed for this rule; see `## v0.22` for the measurement that
answered it (of ten machine-written programs that fail to parse, the braces
rule is two of them).

## Limits that are errors, not crashes
- Expression nesting deeper than 60 levels (parentheses, prefix operators,
  `else if` chains) is a parse error (exit 2), not a host RecursionError.
- Runaway non-tail recursion is a `max_depth` miss (default 20000); a
  runaway tail loop is a `max_iter` miss (default 1000000, **v0.26**;
  before that it was unbounded, the one limit in this section that was
  neither an error nor a crash but a hang). `--max-iter 0` restores the
  old unbounded behaviour explicitly.
- **v0.27 (round 368):** a value's SIZE is a budget too. `max_value`
  (default 500000000 bytes) bounds the six places a value can come out
  bigger than the sum of its inputs — `+` on strings, `+` on lists, `push`,
  `range`, `join` — and `max_int_bits` (default 8000000 bits) bounds the
  integer half, `*` and `+`/`-` and `num`. Before v0.27 `s + s` in a tail
  loop was a raw host `MemoryError` at ~40 iterations, `x * x` did not
  return in 60 s, and `range(100000000000)` reached the OOM killer. Two
  budgets and not one because the cost models differ: string concatenation
  is linear and CPython's bigint multiply is ~n^1.58, so the byte figure
  that lets `range(max_iter)` work would license an integer whose last
  multiply takes hours. `--max-value 0` / `--max-int-bits 0` restore the old
  unbounded behaviour explicitly.
- **v0.27:** integers RENDER as `<integer, N bits>` past 13287 bits (at most
  4000 decimal digits), and `num()` refuses numeric text past the same
  4000-digit boundary, so `num` and `str` stay inverses. Until v0.27
  integers were the one payload kind `_show` rendered in full: `print` of a
  15600-digit integer, a miss message naming one, a failing `check`
  reporting one, `range(big, big + 2)` and `[1,2,3][big]` were all a host
  `ValueError` traceback with exit **1** — the "some check failed" code.
- Structural `==` on arbitrarily deep values is iterative (a 20000-deep
  record compares without touching the host stack).
- **v0.4.1 (round 011):** arithmetic that mixes an unbounded integer with
  a bounded float (`huge / 3`, `huge * 1.5`, `huge % 0.5`, `sqrt(huge)`,
  `huge / 1`) is a `miss: number too large for float arithmetic`, never a
  host OverflowError; `3 / huge` underflows to `0.0` (that is arithmetic,
  not an error). `num(text)` accepts only Whence number syntax — optional
  sign, ASCII digits, optional fraction, optional exponent — with
  surrounding whitespace tolerated (`num(" 3.5 ")` is `3.5`); host-only
  spellings (`"1_000"`, `"nan"`, `"inf"`, `"0x10"`, `"1."`, `".5"`,
  non-ASCII digits) are a `cannot parse` miss and a finite-syntax value
  that overflows a float (`"1e400"`) is an `out of range` miss. (Round 5
  had made these decisions on a temp copy of the checkout that never
  shipped; the round-11 differential oracles re-found the whole family.)
- **v0.21 (round 350):** NAMES and NUMERIC LITERALS are ASCII. Until v0.21
  the lexer classified with `str.isdigit()`/`isalpha()`/`isalnum()`, so
  `let x = ٣` was the number three (contradicting the `num(text)` rule
  directly above it) and `let x = ²` was an uncaught host `ValueError` out
  of `tokenize` — a traceback, not a `LexError`. Both are now `unexpected
  character` lex errors. Source text is still UTF-8: STRINGS and COMMENTS
  hold any character. The escape table gained `\r`, which the lexer had
  always SKIPPED in source and the language had no way to write.

## Running
`python3 run.py [--max-depth N] [--max-iter N] [--max-value N]
[--max-int-bits N] [--no-direct] [--strict-miss] examples/<name>.lang` —
exit 0 (all checks pass / none), 1 (some check failed, or `--strict-miss`
and a miss was dropped), 2 (lex/parse error). *(v0.32: the run also prints a
`dropped:` report naming every miss it computed and threw away. The report
is unconditional — the defect it names is SILENCE — but it does not move the
exit code by itself, because 1 has meant "a check failed" since v0.1 and a
caller grepping for that must keep working. `--strict-miss` is the opt-in
for a CI that wants a discarded miss to fail the run.)* *(`--max-iter 0`,
`--max-value 0` and `--max-int-bits 0` each mean unbounded; the two v0.27
flags follow the shape v0.26 settled on, omitted unless given so the class
default applies. Until v0.26
`run.py` passed `max_iter` to the `Interpreter` unconditionally — including
`None` when the flag was absent — so a class-level default would have been
unreachable from the CLI; `--max-depth` had always been passed only when
given, and the two now agree.)* *(The LEX half of exit 2 only became true in
v0.21, round 350: `run.py` caught `ParseError` and not `LexError`, so every
lex error left the CLI as a Python traceback with exit 1 — the "some check
failed" code.)* Embedding: `Interpreter(out=...,
max_depth=..., max_iter=..., max_value=..., max_int_bits=..., fast=True,
direct=True, gc_relief=False)`; no
`sys.setrecursionlimit` needed — direct mode (v0.9) spends only the host
frames that are demonstrably free and the trampoline takes over beyond
that, so a Whence call never *requires* host stack; a tail call costs zero
Whence frames (`interp.tail_calls` counts them; `interp.fast_hits` counts
driver entries into compiled closures, `interp.direct_hits` /
`direct_fallbacks` the direct calls and the ones the budget refused);
`interp.peak_value` / `interp.peak_int_bits` (v0.27) report the largest value
the run asked a growth site for, in bytes and in bits, whether or not it was
refused.


## Time-Travel Debugging — NOT integrated (whence/timetravel.py, round 132 note)
A `TimeTravelDebugger` Python class (checkpoint/rewind/timeline/diff over an
`Env.vars` dict) landed in a commit outside the round process
(`8637795`, "Time-Travel Debugger v0.7 complete!") along with a prior draft
of this section claiming five new Whence-language builtins (`snap`,
`rewind`, `timeline`, `diff_snap`, `trace`). **That draft was wrong: the
builtins are not reachable from any `.lang` program.** `install_timetravel_
builtins(interp)` exists but nothing calls it (`grep -rn install_timetravel
whence/*.py run.py` — zero hits outside `timetravel.py` itself); no example
uses it. Even if wired in, it would not work as written: it writes to
`interp.builtins[...]`, but the real dispatch table is the module-level
`_BUILTIN_TABLE` singleton (`interp.py`, built once by `_install_builtins`
— the exact per-instance-vs-shared split round 25's oracle-caught bug was
about); `snap_builtin` never forwards its own `name` argument to
`ttd.snapshot()`, which instead reads a variable `_last_snap_name` that is
never bound anywhere; and every builtin fn assumes raw Python values
(`isinstance(name, str)`, `interp.miss(...)`) where Whence's actual builtin
convention is `fn(interp, args, line)` with `args` as `Prov`-wrapped values
and no `Interpreter.miss` method exists. The corrected, previously-invalid
example (`let x = x + 10` rebinds `x` in the same block, a parse error
under decision 3) is deleted rather than fixed, since the feature it
demonstrated is not live. `tests/test_timetravel.py` (11 tests, green)
exercises `TimeTravelDebugger` directly as a Python class — that part is
real and correctly tested, just never connected to the interpreter.
**Resolved (round 138, see `state/research-state-archive.md` and
`knowledge/round-144-whence-structural-types-reconciliation.md` §3):**
`install_timetravel_builtins` was deleted rather than fixed —
`whence/timetravel.py`'s own module docstring carries the same writeup as
this section, plus the reason the fix-it option was rejected: restoring a
prior value of a named binding has no coherent meaning under decision 3
(no assignment/no rebinding), so the feature was a design misfit from the
moment it was proposed outside the round process, not just a wiring bug.
`TimeTravelDebugger` stays as a documented, never-wired, pure-Python
helper for inspecting `Env.vars` while developing the interpreter itself
(e.g. a future host-side REPL) — `tests/test_timetravel.py`'s 11 tests
exercise it directly as a Python class, real and unaffected by the
deletion. A real "time travel" language feature, if ever wanted, belongs
on top of the existing provenance builtins (`at`/`steps`/`blame`), not as
a mutable checkpoint stack — nothing has needed it since.

## Self-hosting round 9 (round 254) — `bench/self_host_memscale.py --mode steps-repro`
Round 228 root-caused `steps()`'s enormous guest-level cost (any
`steps()` call, on any value, once self_host.lang's function library has
been loaded via `self_eval.lang`'s `run_src`, walks the ENTIRE
store-threaded interpretation trace, not just the target value's own
derivation) but explicitly declined to re-run the 13-checkpoint,
multi-GB sweep `bench/self_host_memscale.py` needs to find a fresh
absolute-MB replacement for its now-stale 1200 MB default, judging the
risk/cost not worth it on this specific shared, contended host. Round
254 re-checked that judgment call with fresh numbers (`free -h`: 675 MB
physically free, 2.1 GB "available", swap already 70% full — less
headroom than round 227/228 had) and made the same call again, for the
same reason: a capped subprocess can't trigger a system-wide OOM sweep,
but a multi-GB resident probe still pages everything else on a 3.8 GB
box through swap while it runs, a real cost to this host's other live,
unrelated services (trading bots, Hermes gateways).
Instead of the full sweep, promoted round 228's own ad hoc minimal
isolation repro (library load + one trivial `steps(miss ...)` call, no
self_host.lang test-section checks, no `parse_whence` call — strictly
less prior work than checkpoint 5) into a permanent, reusable tool mode:
`bench/self_host_memscale.py --mode steps-repro`, with its own
safe-by-default cap/timeout (600 MB / 120 s — chosen to sit comfortably
inside this run's own 2.1 GB "available" figure, unlike the full sweep's
1200 MB default). Measured live, twice, via a real subprocess (not
guessed): **`MEMORY_ERROR` at peak_kb≈600,000 (~600 MB) in 85–89
seconds**, both runs. This is a strictly cheaper and safer confirmation
of round 228's finding (which reached >1.35 GB, still climbing, after
291 s uncapped) — the cost has not shrunk, and if anything has grown
further, since rounds 234/236/246/252 each added more guest-parity
dispatch code to `self_eval.lang` that becomes part of every `st` trace
`steps()` walks. A full re-sweep for a fresh absolute-MB number for the
13-checkpoint table still needs round 228's own order-3000-4000 MB /
600 s treatment, on a host that isn't mid-contention — not this one,
not this round. See `knowledge/round-254-whence-self-hosting-round9-steps-repro-tool.md`.

## v0.17 (round 318) — `trunc`: closes the `rand(lo, hi)` backlog by fixing the real blocker

- **Round 294's own item 4** ("`rand()` is deliberately narrow, arity 0
  only, no `rand(lo, hi)` ranged variant — a real but not yet
  justified-by-a-concrete-need extension") had repeated unchanged in
  `state/research-state.md`'s own next-steps list for 24 straight rounds
  (294 through 317) without ever being investigated past that one
  sentence. Investigating it properly (the same discipline round 314
  applied to the dynamic-call-graph item) found the premise itself was
  wrong: the blocker was never `rand`'s own arity. **No Whence builtin has
  ever been able to turn a float into an int** — `num()` on an
  already-numeric argument is a pure identity (`whence/interp.py`'s
  `b_num`: `if _is_num(p): return args[0]`), so the obvious pure-Whence way
  to build a ranged random draw from `rand()`'s own `[0.0, 1.0)` output,
  `num(lo + rand() * (hi - lo + 1))`, was never expressible AT ALL — not
  because `rand` lacked arguments, but because nothing in the language
  could round the result down to an integer. Confirmed by reading every
  one of the pre-existing builtins (`grep -n "^@register" whence/
  interp.py`): none does this, and none was ever intended to (`abs`/`sqrt`
  are the only two other purely-numeric unary builtins, neither touches
  the int/float boundary).
- **This reframes the real design question**: does Whence need a
  dedicated, native `rand(lo, hi)` builtin, or does it need a general
  float→int primitive that a `rand(lo, hi)`-shaped idiom (and any other
  numeric code that needs one) can then compose from ordinary Whence code?
  The second is strictly more useful for the same implementation cost — a
  native `rand(lo, hi)` would ONLY help random-range code, while a
  truncation primitive helps any computation that produces a float and
  needs an integer (a random range, an average turned into a count, a
  `sqrt` result used as an index) — so this round built the primitive, not
  the special case, and left the ranged-random idiom to ordinary
  user-level composition (demonstrated below), never touching `parser.py`'s
  effect system or `_EFFECTFUL_BUILTINS` at all (`trunc` is a pure
  function, the same class as `abs`/`sqrt`, not a third effectful
  builtin).
- **`trunc(x)`, arity 1, rounds TOWARD ZERO** (`int(p)`'s own Python
  semantics applied to `p`, whether `p` is already an int or a float) —
  `trunc(3.9)` is `3`, `trunc(-3.9)` is `-3`. **A real, named design
  decision, not a default accepted without thought**: the alternative,
  `floor` (round toward negative infinity), agrees with `trunc` for every
  non-negative input — which is all `rand()`-driven code ever produces,
  since `rand()` never returns a negative value — so the choice is
  invisible to the very use case that motivated building this at all, and
  is documented here precisely because a future round reading only the
  `rand(lo, hi)` motivating example could otherwise miss that
  `trunc(-1.5)` is `-1`, not floor's `-2`. `trunc` was chosen over `floor`
  because it composes predictably with the existing `abs` builtin's own
  "toward zero is the origin" convention (`abs(trunc(x)) == trunc(abs(x))`
  for every `x`, which is not true of `abs`/`floor`), not because of any
  `rand`-specific reasoning.
- **Total on invalid input, like `abs`/`sqrt`, never a host exception**: a
  non-numeric argument is `mk_miss("trunc of %s" % show_payload(p), ...)`,
  the identical shape `abs`/`sqrt` already use for the same case. **No
  `inf`/`nan` guard was added, unlike a first instinct might suggest**:
  audited every path that can produce a Whence float (`binop`'s
  arithmetic, already catching `OverflowError` into a miss before a value
  is ever built; `b_sqrt`, already rejecting negative inputs and catching
  its own `OverflowError`; `num()`'s string parser, already rejecting
  `"nan"`/`"inf"`/`"infinity"` spellings and out-of-range results) and
  confirmed a Python `float('inf')`/`float('nan')` can never reach a
  Whence value slot through any existing builtin or operator — so guarding
  `trunc` against them would be dead code for a state that cannot arise,
  not defensive programming for a real one (the same reasoning `abs`/
  `sqrt` already both apply by omission).
  **CORRECTION (round 323): this audit's "any existing builtin or
  operator" scope was one path too narrow — it never considered the
  LEXER's own literal scan**, which builds a `NUMBER` token via a direct
  `float(text)` call with no overflow handling at all, upstream of every
  builtin/operator this audit examined. A source literal whose digit
  string overflows a float (`1` + `"0" * 400` + `.5`, all one token) was
  ALREADY reachable before this round and already became a silent `inf`
  — never a crash itself, but `trunc(<that literal>)` then hit `int(inf)`,
  an uncaught `OverflowError`, since `_is_num` accepts `inf`/`nan` as
  ordinary floats. Round 323 found this via `BUILTIN_ARITY`-totality
  fuzzing `trunc` with `1e400` (see the round's own exponent-literal fix
  below) and fixed `b_trunc` with the identical try/except-`OverflowError`
  idiom `b_sqrt` already uses two functions above it, plus a matching
  `except ValueError` for `int(nan)`. `abs`/`sqrt` themselves remain safe
  by construction (`abs` cannot raise on any float; `sqrt` already has its
  own `OverflowError` catch for a different reason — `math.sqrt` on a
  huge-but-finite input), so this correction is `trunc`-specific, not a
  reopening of the wider claim.
- **Guest parity landed the SAME round**, unlike most `v0.14.x`/`v0.16.x`
  features (which deliberately split host and guest work across rounds) —
  justified because `trunc` is a trivial free-delegation case, structurally
  identical to `abs`/`sqrt`'s own existing guest dispatch (a scalar-in,
  scalar-out, miss-propagating, non-closure-touching builtin), not a new
  gap-class investigation: `examples/self_eval.lang` gained `"trunc"` in
  `builtin_names`, `propagating` (it propagates a miss argument exactly
  like `abs`/`sqrt`, unlike the "total" provenance-as-data family), and
  `arities` (`trunc: 1`), plus one dispatch line in `apply_host_builtin`
  (`else if name == "trunc" { trunc(a0) }`, next to `abs`/`sqrt`'s own).
- **The motivating idiom now works**, demonstrated in `examples/
  effects.lang` (where `rand()` itself already lives): `fn roll_die()
  effects [random] { trunc(rand() * 6) + 1 }` draws a uniform integer in
  `[1, 6]` — the canonical "ranged random draw" every mainstream
  language's standard library ships as a one-liner, now expressible in
  pure Whence without any change to `rand`'s own arity. **This closes
  round 294's item 4 for good, the same way round 314 closed the
  dynamic-call-graph item — not by building the literally-requested
  feature (`rand(lo, hi)`), but by determining what it actually needed and
  confirming that need is now met**: a future round should not re-open
  "give `rand` a ranged-arity variant" without first checking whether
  `trunc`-based composition already covers the concrete case in hand.
- **Verification**: `tests/test_interp.py::test_trunc` (new — positive,
  negative, already-int, and non-numeric-miss cases, plus the
  `abs(trunc(x)) == trunc(abs(x))` identity for both an int and a float
  input) and `tests/test_self_eval.py`'s differential CORPUS gained one
  new program (`let result = trunc(3.9) + trunc(-3.9) + trunc(9)`,
  agreeing between host-direct and guest-mediated execution). `examples/
  effects.lang` gained the `roll_die()` demo and two checks (9 → 11: the
  die stays in `[1, 6]` across several calls, and `trunc` composes with
  `rand` inside an effectful fn body the same way `print`/`rand`
  themselves already do). Full `languages/whence` suite,
  `run_tests_fast.sh`, cross-track `harness/run_tests_fast.sh`, host
  fuzz/oracle/guest-differential campaigns, and `bench/ref_diff.py
  --counters` numbers are recorded in `knowledge/
  round-318-whence-v017-trunc-closes-rand-backlog.md`.

## v0.12/v0.13 guest parity fix (round 320) — named-fn type-guard label wording, found by a new host-vs-guest PARSER differential tool
- **A new self-hosting instrument, not a new language feature.** Every
  prior self-hosting round tested the guest EVALUATOR's derivation shape
  (`harness/swe/guest.py`'s why-shape fuzzer) or hand-picked, single-field
  checkpoint assertions in `self_host.lang`'s own 66-check test section —
  nothing had ever canonicalized a REAL host `A.*` AST and a REAL guest
  `@{kind: ..., ...}` AST into the same shape and diffed them, field for
  field, across a real corpus. Built as `tests/test_parser_differential.py`:
  `canon_host(node)` walks `whence/ast_nodes.py`'s 20 node classes into
  plain nested tuples (dropping parser-internal-only fields with no guest
  equivalent — `Call.tail`, `FnExpr.param_call_fact`, `Block.
  tail_alias_tag`/`tail_param_name` — all v0.9/v0.14.x compiler/effect-
  system bookkeeping, not part of the SOURCE-level shape); `canon_guest
  (prov)` walks the guest's own `Record`/`WList` output the SAME way,
  dispatching on each node's `kind` field. Both a guest AST (from
  `parse_whence`, called host-level via `self_eval.lang`'s own copy of the
  shared parser section — no `run_src` evaluator layer, the same cheap
  level `test_guest_parser_parses_its_own_full_source` (round 192) already
  uses) and a host AST (`whence.parser.parse`) are REAL Python-level Prov/
  Record trees, so the comparison costs nothing beyond ordinary tuple
  equality — no bespoke guest-box unwrapping needed, the same "the
  parser's own output is never boxed" property `steps`/`at`/`blame`
  (rounds 206/218) already relied on for FREE delegation.
- **First real corpus run (35 items: 22 synthetic snippets covering every
  node kind + 13 real `examples/*.lang` files, `shapes.lang`/
  `self_eval.lang`/`self_host.lang` excluded — see the test file's own
  header for why) found exactly 4 divergences, ALL traceable to ONE root
  cause**: `fn foo(x: num) { x }`, `fn bar(a: num, b: str) { a }`, `fn
  needs_guess(g: guess) { confidence(g) }` (the exact shape `examples/
  guess.lang` line 75 already ships), and `guess.lang`'s own full source
  (which contains that same fn). Every OTHER corpus item — including every
  anonymous-fn-with-typed-param variant — matched byte-for-byte on the
  first run, meaning this is a narrow, well-isolated bug, not a sign of
  systemic guest-parser drift.
- **Root cause**: the v0.12 parameter-type-guard erasure (`_apply_type_
  guards` on the host, `build_guards`/`apply_type_guards` on the guest,
  guest parity shipped round 158) builds a `typed(param, spec, label)`
  guard call per annotated parameter. The host's label is `"parameter
  '%s'%s" % (pname, suffix)` with `suffix = " of %s" % fn_name if fn_name
  else ""` — a NAMED function's (`FnDef`) guard says which function the
  parameter belongs to (`"parameter 'x' of foo"`); an anonymous function's
  (`FnExpr`, `fn_name=None`) guard does not (`"parameter 'x'"`). The
  guest's `build_guards` NEVER threaded the enclosing fn's name through at
  all — `let label = "parameter '" + params[i] + "'"`, unconditionally,
  for both named and anonymous fns — so it silently matched the host only
  for the anonymous case (where the host's own suffix is also empty) and
  silently diverged for every named case, invisibly, since round 158.
  Nothing before this round's own new tool ever compared a named typed-
  param fn's ACTUAL LABEL STRING between host and guest — `guess.lang`'s
  own `needs_guess` check (`"a typed parameter accepts an actual guess"`)
  only ever exercises the SUCCESS path, where the label is never even
  read; the label only becomes visible in a MISS's own reason text, on
  the REJECTION path, which no existing check triggers for a named fn.
- **The fix**: `build_guards(params, types, i, acc, suffix)` and
  `apply_type_guards(block_node, params, types, suffix)` both gained a
  `suffix` parameter (label built as `"parameter '" + params[i] + "'" +
  suffix`, `build_guards`'s own recursive call threading it through
  unchanged) — the `fnexpr` call site now passes `""` (anonymous, matches
  the host's `fn_name=None` branch), the `fndef` call site now passes `"
  of " + nm.name` (matches the host's `" of %s" % fn_name` branch)
  exactly. Applied IDENTICALLY to both `self_host.lang` and `self_eval.
  lang`'s byte-identical shared section (`test_self_eval.py::test_parser_
  section_matches_self_host` pins the exact substring), with the SAME
  line count in both files before and after (no new lines needed — the
  fix only extends existing signatures/call sites in place), so neither
  file's own line-range constants (`LIB_START`/`LIB_END` in `test_self_
  hosting.py`, the `host_lines[27:561]` slice in `test_self_eval.py`)
  needed updating.
- **Verification**: the new differential sweep (`tests/test_parser_
  differential.py::test_host_and_guest_parsers_agree_on_ast_shape`, marked
  `whence_slow`) now reports 0 mismatches across all 35 corpus items, up
  from 4 before the fix — re-confirmed live, not assumed, by running the
  same tool before and after applying the edit. A dedicated non-slow pin
  (`test_named_fn_typed_param_guard_label_includes_enclosing_fn_name`)
  checks both the fixed named-fn case (`"parameter 'g' of needs_guess"`,
  independently on host AND guest) and the anonymous-fn control case
  (`"parameter 'x'"`, unchanged on both sides) directly, without going
  through the canonical-form diff, so a future accidental revert of only
  one side would still fail loudly even if the broader sweep were ever
  skipped. `run_tests_fast.sh`: 945 → **946 passed, 39 deselected** (+1
  fast test, +1 newly-deselected slow test). Full unfiltered `pytest
  tests/` (backgrounded, 279.55s): 983 → **985 passed** (+2, exactly
  matching the 2 new test functions, 0 failures, 0 regressions).
  `test_self_hosting.py`/`test_self_eval.py` (30 tests, including `test_
  guest_parser_parses_its_own_full_source`'s own 154-statement pin and
  `test_parser_section_matches_self_host`'s byte-identity check): all 30
  still pass unchanged, confirming the fix altered neither self_host.
  lang's own top-level statement count nor the shared section's byte
  identity. `python3 run.py examples/guess.lang`: still **27 passed, 0
  failed** (the fix only changes a MISS's own reason text, which
  `guess.lang`'s own checks never assert on verbatim). Every other
  `examples/*.lang` file re-run directly: unchanged pass/fail counts.
  Cross-track `bash harness/run_tests_fast.sh`: **414 passed, 229
  deselected**, byte-identical to round 319's own post-landing baseline —
  zero unintended change outside `languages/whence`.
- **Named, not chased**: this tool's canonical form deliberately does not
  attempt to compare PARSE-ERROR shapes (a host `ParseError` exception vs.
  a guest `miss` value) — `self_host.lang`'s own hand-written error-
  handling test section (67 checks, "tests: total error handling") already
  covers specific error wordings for specific inputs by direct assertion,
  and mixing that INTO a generic structural-equality sweep would need a
  second, differently-shaped comparison path for no real gain this round.
  A future language(C) round could extend `test_parser_differential.py`
  with an error-corpus mode if a genuine need for it turns up (mirroring
  how this round's own tool was itself motivated by a real, if narrow,
  finding rather than built speculatively).

## v0.17.1 (round 323, SWE-loop D) — lexer gains exponent literals; closes an `int(inf)` crash in `trunc`

- **Task selection**: `research-state.md`'s next-steps had named `harness/
  swe/fuzz.py`'s missing `BUILTIN_ARITY["trunc"]` entry since round 318,
  repeated unchanged through rounds 319-322 as "the natural next SWE-loop
  (D) round." Added it (arity 1, same generic-fallback shape as `abs`/
  `sqrt`, no special-casing needed) and hand-drove `trunc` across the
  input-type matrix a fuzz totality check would exercise — which is how
  this round's own two real findings surfaced, neither one the assigned
  task itself.
- **Finding 1 — the lexer has never supported scientific notation on a
  raw source literal.** `1e400` (chosen as a `trunc` totality probe
  specifically because `harness/swe/fuzz.py`'s own `STR_POOL` already
  lists `"1e400"`/`"1e5"` as strings, but ONLY ever feeds them to `num()`
  as quoted content, never as raw source) silently tokenized as
  `NUMBER(1)` followed by a bare `NAME("e400")` — a phantom extra
  statement outside parens (`let x = 1e400` "worked" by accident: two
  independent statements, `let x = 1` then a dangling, never-read
  `e400` name-reference) and a flat `ParseError` inside them (`trunc
  (1e400)`, `sqrt(1e400)`, even a bare `(1e400)`). Yet `whence/interp.py`'s
  own `_NUM_RE` (`^([+-]?[0-9]+)(\.[0-9]+)?([eE][+-]?[0-9]+)?$`, used by
  `num(text)`'s string parser) documents "optional exponent" as part of
  canonical "Whence decimal syntax" — a real grammar/literal
  inconsistency between what the LANGUAGE's own number syntax is defined
  to be and what a LITERAL can actually spell, invisible to the fuzzer for
  the same `STR_POOL`-only-as-string reason noted above. Fixed in
  `whence/lexer.py`'s digit-scanning branch: after the existing optional
  `.digits` fraction, an optional `[eE][+-]?[0-9]+` suffix is consumed —
  but ONLY when a full valid exponent follows (sign then ≥1 digit), so a
  bare trailing `e`/`E` that isn't a number (`5experiment`, `5e` with
  nothing after) still lexes exactly as before (a separate `NAME` token).
  An exponent literal is always a `float` (`1e5` is `100000.0`, matching
  `_NUM_RE`'s own float-if-exponent-present rule); an overflowing one
  (`1e400`) becomes Python's `inf`, matching the PRE-EXISTING convention
  for a huge digit-string-plus-fraction literal with no exponent at all
  (already silently `inf` before this round — see Finding 2), not
  `num("1e400")`'s "out of range" MISS, which is a separate,
  string-conversion-specific SPEC rule (see "Limits that are errors, not
  crashes" above), not a literal-grammar one.
- **Finding 2 — `trunc(<a literal that overflows to inf>)` was an
  uncaught host `OverflowError`, a genuine (if narrow) hole in v0.17's own
  landing audit.** That audit (see the v0.17 section above) explicitly
  checked "every path that can produce a Whence float" — arithmetic's
  `OverflowError` catch, `sqrt`'s own catch, `num()`'s string-parse
  rejection — and concluded `inf`/`nan` can never reach a Whence value
  slot, so `trunc` needed no guard. That conclusion was one path too
  narrow: it examined every BUILTIN and OPERATOR, but not the LEXER's own
  literal scan, which has ALWAYS built a `NUMBER` token via a bare
  `float(text)` call with zero overflow handling — a huge digit-string-
  plus-fraction literal (`"1" + "0" * 400 + ".5"`, one token) already
  silently became `inf` before this round, with no arithmetic or builtin
  involved at all, hence outside that audit's stated scope. `trunc`'s own
  `_is_num` guard accepts `inf`/`nan` (ordinary `float` instances), so
  `int(p)` then raised `OverflowError` (`+-inf`) or `ValueError` (`nan`,
  reachable in principle though no current Whence path produces a real
  NaN value). This round's exponent-literal fix (Finding 1) turned an
  obscure 400-digit literal into a trivial `1e400`, but the crash predates
  it and does not depend on it. Fixed with the identical idiom `b_sqrt`
  already uses two functions above `b_trunc` in `interp.py`: wrap
  `int(p)` in `try`/`except (OverflowError, ValueError)`, returning the
  same `"number too large for float arithmetic"` miss text `binop`/`sqrt`
  already use for their own overflow cases. A correction note was added
  in place in the v0.17 section above rather than editing its original
  claim, following this project's own established convention for
  superseded audit claims.
- **Verification**: `tests/test_lexer.py` gained 3 tests (one-token
  exponent parse for `1e5`/`1E10`/`2.5e3`/`1e-2`/`1e+2`; overflow-to-`inf`
  for `1e400`/`-1e400`, not a `LexError`; the bare-trailing-`e` no-op
  cases `5e`/`5experiment`/`5e+`). `tests/test_interp.py::test_trunc`
  gained a new sibling test (`trunc` of the huge-digit-literal, `1e400`,
  and `-1e400`, all now a clean miss, not a crash). `run_tests_fast.sh`:
  946 → **950 passed, 39 deselected** (+4, exact). Full unfiltered
  `pytest tests/` (backgrounded, 303.28s, run BEFORE the new tests were
  added, confirming the pre-existing suite was unaffected by the fixes
  alone): 985 passed, 0 regressions. `harness/swe/fuzz.py`: 1500-program
  grammar-directed campaign (seed 323) after both fixes — **0 unique
  crashers** (1350 ok, 127 parse_error, 23 timeout — all pre-existing
  categories, nothing new). `harness/tests/test_swe_fuzz.py` gained 2
  tests (`trunc` reach guard mirroring `test_generator_now_emits_rand_
  calls`; a totality sweep across `5/-5/3.7/-3.7/0/1e400/-1e400/1e5/
  "abc"/true/[1,2]/@{a:1}`, all `ok`). `harness/swe/guest.py`'s
  `WHY_VOCAB` gained `"trunc"` for tabular completeness with `abs`/
  `sqrt`/`num` — investigated directly and found NOT independently
  exploitable for this class of builtin (see the code comment at its
  definition): every generic single-arg host-delegate's guest-side op
  label is the literal dispatch-time NAME string, never derived from
  which internal host builtin actually ran, unlike `range`/`keys`/
  `reasons`/`steps`/`blame`/`diverge`'s hand-written per-element `mkb`
  wrapping (round 20's real bug class). Cross-track `bash harness/
  run_tests_fast.sh`: 414 passed, 229 deselected, unchanged. Full
  metrics, campaign counts, and the investigation trail are in
  `knowledge/round-323-swe-loop-d-trunc-arity-and-exponent-literal-lexer-bug.md`.

## v0.13 guest parity fix (round 326, language C) — return-type guard label wording for anonymous fns

- **Same bug class as round 320, one guard family over**: round 320 found
  and fixed a host/guest label divergence in the v0.12 PARAMETER type
  guard (a named fn's guard is missing "of `<fn_name>`" on the guest).
  This round asked the obvious follow-up — does the v0.13 RETURN type
  guard (`_check_ret`/`_closure_ret` in `interp.py`, guest counterpart
  `check_ret` in `self_eval.lang`) have the same class of bug? — and found
  yes, in the opposite direction: the guest's `check_ret` UNCONDITIONALLY
  built `"return value of " + fn_name`, while the host's `_closure_ret`
  only appends `" of %s" % name` when the closure has a name at all
  (`label = "return value of %s" % name if name else "return value"`,
  never true for an `A.FnExpr`/anonymous closure, `_mk_closure(None, ...)`
  at both of its call sites in `interp.py`).
- **Why this was invisible for 18 rounds** (`check_ret` shipped round 158
  alongside the parameter guard fixed by round 320): the guest represents
  every closure's runtime "name" as a non-empty string — `"(anonymous)"`
  for an unnamed one (`eval_FnExpr`'s own `@{... name: "(anonymous)", ...}`
  literal, matching the host's OWN internal op-label for a bare `fn`
  literal, `leaf("fn", "(anonymous)", ...)` in `interp.py` — so `c.name`
  is never absent, only ever a real name or that one sentinel string).
  `check_ret`'s naive `"return value of " + fn_name` therefore silently
  produced `"return value of (anonymous)"` for every anonymous fn whose
  `-> Type` check failed — and `self_eval.lang`'s own pre-existing check,
  `"guest anonymous fn honors both param and return types"`, only ever
  exercised the SUCCESS path (`fn(a: str) -> str { a + "!" }` called with a
  matching arg) — the exact same "success-path-only" blind spot round
  320's finding named as its own root cause, this time recurring in a
  sibling guard family that round 320 itself never touched.
- **The fix**: `check_ret` (`self_eval.lang`) now branches on the
  `"(anonymous)"` sentinel the same way `show_callable` (two functions
  above it in the same file) already does for a different purpose (call
  labels): `let label = if fn_name == "(anonymous)" { "return value" }
  else { "return value of " + fn_name }`. No shared-section edit needed —
  unlike round 320's fix, `check_ret`/`apply_closure` live only in
  `self_eval.lang`'s own evaluator portion (self-hosting round 4+), never
  in `self_host.lang`'s lexer/parser-only file, confirmed directly
  (`grep check_ret examples/self_host.lang` — no hits).
- **New coverage, mirroring round 320's own "dedicated pin, isolated from
  the corpus" pattern**: two new checks added directly after the
  pre-existing success-path-only one in `self_eval.lang`'s own SELF-TESTS
  section — one for the anonymous rejection path (`contains(reasons(...)
  [0], "return value expected num, got str")`, i.e. no "of" anywhere), one
  for the NAMED rejection path as a regression control (still says "of
  g"). A third, independent pin lives at the Python level:
  `tests/test_self_eval.py::test_return_type_guard_label_agrees_host_vs_
  guest` runs BOTH the anonymous and named cases through the real host
  `Interpreter` AND the real guest (`guest_eval_all`), asserting the exact
  reason-text PREFIX matches on both sides for both cases — deliberately
  outside `test_differential_host_vs_guest`'s own corpus sweep, whose
  `payloads_agree()` helper exempts miss REASON text by design (only
  missed-ness itself is compared there), so this class of bug could never
  have been caught by that sweep no matter how large the corpus grew.
- **Verification**: `python3 run.py examples/self_eval.lang`: **103 → 105
  passed, 0 failed** (+2, exactly the two new in-language checks) —
  `tests/test_self_eval.py::test_example_runs_green`'s own hardcoded
  count updated to match. `pytest tests/test_self_eval.py`: 14 → **15
  passed** (+1, the new dedicated host-vs-guest pin). `run_tests_fast.sh`:
  950 → **951 passed, 40 deselected** (+1 exact, deselected count
  unchanged — the new test is cheap enough to stay in the fast tier, no
  `whence_slow` marker needed). Full unfiltered `pytest tests/`
  (backgrounded, 455.27s): **991 passed, 0 failed** — the implied prior
  baseline is 990 (round 320's own post-fix 985 was measured BEFORE round
  323's own 4 new tests landed, per that round's own note; 985 + 4 (round
  323) + 1 (round 324's fuzzer-sweep test) = 990), so this round's +1
  (the one new Python-level test — `test_example_runs_green` itself is
  `whence_slow`-marked and counts as ONE pytest test regardless of how
  many in-language checks it covers) lands exactly on 991, 0 regressions.
  Cross-track `bash harness/
  run_tests_fast.sh`: 416 passed, 231 deselected, byte-identical to round
  325's own post-landing baseline. `test_self_hosting.py`'s 15 tests
  (`self_host.lang`, untouched by this round) still pass unchanged; `bash
  bench/ref_diff.py --counters examples/*.lang --show` (all 18 example
  files × 3 modes, live-confirmed) confirms `self_eval.lang` now reports
  `checks=105` (was 103) on direct/fast/slow alike, `self_host.lang`
  still `checks=66`, every other file's counters unchanged, and **"0
  differing (file, mode) pairs"** overall.
- **Named, not chased**: the sibling `call`/arity/depth-guard messages
  in `apply_closure` (`"call " + c.name`, producing an op-LABEL of `"call
  (anonymous)"` on the guest vs. the host's `"call <fn>"`, `name = p.name
  or "<fn>"`) are a related but DIFFERENT divergence — not fixed this
  round. Unlike the return-type guard (an explicit "guest parity" feature,
  round 158's own comment: "mirrors the host's `_check_ret` exactly"),
  arity/callable-error wording is a documented, DELIBERATE divergence
  (this file's own header: "reason STRINGS for arity/callable errors are
  worded differently (missed-ness always agrees)") — conflating the two
  would blur a real parity contract with an intentionally-loose one for no
  concrete gain. A future language(C) round could still audit whether the
  op-LABEL (as opposed to the miss-reason TEXT) is meant to match exactly
  for provenance-comparison purposes, since `test_provenance_labels_agree_
  host_vs_guest` compares label sets but has never included an anonymous-
  fn call case — left as an open, not-yet-investigated question, not a
  confirmed bug.

## v0.17.1 guest parity fix (round 332, language C) — exponent-literal lexing

- **Closes a real, previously-undocumented host/guest divergence**: round
  323 (SWE-loop D) taught the HOST lexer (`whence/lexer.py`) to consume a
  trailing `[eE][+-]?[0-9]+` exponent suffix onto a numeric literal
  (`1e5` -> `100000.0`), fixing an inconsistency between `SPEC.md`'s own
  documented number grammar (which `num(text)`'s STRING-parsing path,
  `interp.py`'s `_NUM_RE`, already honored) and the raw SOURCE-literal
  grammar, which previously had no exponent handling at all. That fix
  landed only in `whence/lexer.py` — the GUEST lexer
  (`self_host.lang`/`self_eval.lang`'s byte-identical shared `lex`
  function) was never revisited, so `1e5` as a guest source literal still
  silently split into `NUMBER(1)` followed by `NAME("e5")`, nine rounds
  after the host fix landed. Found by direct reading of the guest's
  digit-scanning branch (no exponent lookahead at all), the same
  "feasibility check first, not fuzz-and-hope" discipline round 324 used
  wiring `fuzz.py` into the parser-differential file — not found BY that
  fuzzer, since (per round 323's own knowledge file) no fuzz corpus in
  this project has ever emitted a raw exponent-literal SOURCE token.
- **The fix**: a new guest helper `exp_end(s, j)`, added to BOTH
  `self_host.lang` and `self_eval.lang` at the identical point in their
  byte-identical shared lexer section (right after `slice`, mirroring
  `test_self_eval.py::test_parser_section_matches_self_host`'s
  substring-identity requirement) — same lookahead the host's
  `lexer.py` uses: only consumes `e`/`E` + optional sign + digits when a
  FULL, valid exponent follows, otherwise leaves the position untouched
  (so `5e`/`5experiment` still lex as `NUMBER(5)` `NAME("e"/"experiment")`,
  exactly like the host). The digit-lexing branch's own `let j = ...`
  now threads through `exp_end` before slicing the literal's text and
  handing it to the (pre-existing, unmodified) `num(...)` builtin, which
  already parses an exponent-bearing string correctly via `_NUM_RE` — no
  change needed there, only to where the guest lexer's own token
  boundary `j` stops.
- **New coverage**: 7 new checkpoint checks added to `self_host.lang`'s
  own lexer test section, right after the pre-existing `"lexer float"`
  check — basic/negative/uppercase/explicit-positive exponent literals,
  the two "bare trailing e is NOT consumed" boundary cases
  (`"5e"`, `"5experiment"`), and one end-to-end `parse_whence` sanity
  check. Also added one new entry to `tests/test_parser_differential.py`'s
  hand-picked `SYNTHETIC` corpus (`'let e = 1e5 + 1e-3 - 2.5E2'`),
  exercising the full host-vs-guest AST-shape comparison (`canon_host`/
  `canon_guest`'s `"num"` case already carries the literal's parsed
  VALUE, so this also catches a one-sided fix, not just a one-sided
  crash). `self_eval.lang`'s own SELF-TESTS section was left untouched —
  it tests the EVALUATOR, not the lexer, and self_host.lang already
  covers the lexer directly; the two files still share the fix because
  it lives in their shared library section, confirmed by
  `test_parser_section_matches_self_host`.
- **Bookkeeping updates this fix required**: `self_host.lang` now parses
  to 162 top-level statements (was 154; +1 for `exp_end`, +7 for the new
  checks) — `tests/test_self_hosting.py::test_guest_parser_parses_its_
  own_full_source`'s pin updated. The shared library section grew from
  `self_host.lang` lines 28..561 to 28..574 (both `LIB_START, LIB_END` in
  `test_self_hosting.py` and the hard-coded slice in
  `test_self_eval.py::test_parser_section_matches_self_host` updated
  together, since a length mismatch between them would silently pass the
  substring check on a truncated section). `self_host.lang` direct-run
  checkpoint count: 66 -> 73 passed (`tests/test_examples.py::test_self_
  hosting_real_syntax`'s hardcoded string updated to match).
  `self_eval.lang` unaffected (still 105 passed) — it never had its own
  lexer checkpoints.
- **Verification**: `python3 run.py examples/self_host.lang`: 66 -> **73
  passed, 0 failed** (+7 exact). `python3 run.py examples/self_eval.lang`:
  unchanged, **105 passed, 0 failed**. `pytest tests/test_self_hosting.py
  tests/test_self_eval.py`: **32 passed** (all green, including the two
  updated pins). `pytest tests/test_parser_differential.py -m
  whence_slow`: **2 passed, 1 deselected** (the new SYNTHETIC entry adds
  an assertion inside an existing test, not a new test node).
  `run_tests_fast.sh`: **952 passed, 40 deselected**, pytest test-node
  count unchanged from round 331 (all new coverage lives as in-language
  `check`s or corpus entries inside existing test functions). Full
  unfiltered `pytest tests/` (backgrounded, 388.45s): **992 passed, 0
  failed** — matches the implied 991-baseline (round 326's own post-fix
  count, unchanged since by any full-suite-affecting round) + 1 (round
  330's new `test_self_eval.py` pin), exactly; this round adds 0 new
  pytest test nodes. Cross-track `bash harness/run_tests_fast.sh`: **417
  passed, 234 deselected**, byte-identical to round 331's own baseline.

## v0.12/v0.13 guest parity (round 338, language C) — `shape` in the self-hosted parser and evaluator
- **The last piece of structural-type parity, open since v0.12 shipped in
  round 128.** Round 335's next-steps item 2 (carried unchanged by round
  336 as its item 4) named it: `self_eval.lang`/`self_host.lang`'s shared
  parser section had no `shape` statement at all, and `expect_type_name`
  accepted primitive tags only. The v0.12 section above already recorded
  the consequence from the other side — "`TYPE_TAGS` is primitive tags
  only, so no fuzzed program ever names a `shape` as a type spec on
  either the host or guest side — `self_eval.lang` still has no `shape`
  support at all". That sentence is now **stale and superseded by this
  section**; the guest half is closed. (`TYPE_TAGS` is still primitives
  only, so the FUZZER still emits no shape — after this round that is a
  generator choice, not a guest limitation.)
- **What "no support" actually looked like.** `shape` is a contextual
  keyword, so the guest lexer tokenized `shape Point` as two ordinary
  NAME tokens and the guest parser reached the `=` with nothing to do
  with it. Every `shape` program failed with the SAME reason —
  `"unexpected token '=' at line 1"` — no matter what was wrong with it.
- **Decision 27 (new): the guest recovers the host's mutable parser state
  from the TOKEN STREAM rather than threading an accumulator.** The host
  `Parser` keeps `self.shapes`, a dict `shape_def()` writes into and
  `parse_type()` reads. Whence has no mutation. Threading a shapes
  accumulator through the guest parser would not have been enough either:
  every one of the guest parser's ~25 functions would have had to RETURN
  the accumulator as well as take it, including the whole expression
  parser, because an anonymous `fn(a: Point)` can carry an annotation.
  (**Round 342 correction:** this sentence originally rested on "the
  host's set is deliberately NOT scope-aware ... that is exactly the case
  `_UnboundRetType` exists for", which v0.18 has since made false. The
  threading argument survives unchanged — it never depended on the table
  being flat — and decision 27 itself is unchanged, with a third premise
  added; see `## v0.18`.)
  `shapes_declared_before(toks, p)` replaces all of that with a pure
  function. It is exact, not approximate, and rests on two premises that
  are pinned as tests rather than assumed:
  1. **Adjacency.** The three tokens `shape` NAME `=` must be adjacent,
     which is what the host's own `peek(1)`/`peek(2)` require — neither
     skips a NEWLINE. Verified against the host: `shape\nPoint = @{x:
     num}` is `"unexpected '=' at line 2"` there, and a miss on the guest.
     And since NAME NAME never occurs adjacently inside any legal Whence
     expression, a match can only ever be at statement start — exactly
     where the host tests for it.
  2. **Completion.** The declaration's closing `}` must come before `p`
     (`shape_close`), because the host runs `self.shapes[name] = fields`
     only after `expect("}")`. This is what rejects `shape Foo = @{x:
     Foo}`, which the host also rejects ("unknown type 'Foo'") while it
     is still parsing that shape's own field types.
  The cost is O(tokens) per NON-PRIMITIVE type name, and zero otherwise:
  the primitive-tag branch is tested first, so every program written
  before this round — and every program the fuzzer emits today — pays
  nothing. Both scan functions are tail-recursive, so v0.3 tail merging
  keeps them to one frame.
- **Type annotations now carry a spec NODE, not a type-name string.**
  `expect_type_name` returns `spec: @{kind: "str", value: tag}` for a
  primitive and `spec: @{kind: "name", value: Name}` for a shape,
  mirroring the host's `_type_spec_expr` exactly. The NameRef, rather
  than a copy of the shape record, is what makes `shape Line = @{a:
  Point, b: Point}` read the ONE binding `Point` names on both sides —
  pinned by `L.a.__shape == "P"` surviving on the guest.
- **Parameter guards needed no evaluator change at all.** A guard is
  `let p = typed(p, <spec>, label)`, and round 335 had already taught the
  guest `typed` to accept a RECORD spec (via `guest_spec_match`). So the
  whole `: Shape` half of this round is parser-only — a statement as much
  about round 335 as about this one.
- **`-> Shape` is the half that did need the evaluator.** The guest now
  mirrors `_closure_ret`: `resolve_ret_spec` resolves the annotation ONCE
  at closure-creation time, never per call (round 336's tail-transparency
  work depends on a typed tail-recursive function costing nothing per
  bounce, and this preserves that). A primitive resolves to its own plain
  string, so an unannotated or primitive-annotated closure's record is
  behaviourally unchanged; a shape resolves through the environment to
  the shape's own record value.
- **The guest needs `_UnboundRetType` too, for the host's exact reason.**
  `fn g() { shape L = @{x: num}  1 }  fn f() -> L { 1 }` parses on both
  sides (L was declared earlier in the token stream) while L's binding
  only ever lives inside g's call frame. On the host a naive
  `env.get(name).payload` raised `AttributeError` (see the v0.13 section
  above); the guest's `lookup` misses rather than raising, so there is no
  crash to mirror — what had to be mirrored is the MESSAGE, since an
  unbound shape would otherwise read as an ordinary mismatch against a
  miss-valued spec. The guest tags it `@{__unbound_ret: name}` and
  `check_ret` renders the host's own wording, `"<label>: type '<name>' is
  not in scope here"`.
- **A differential blind spot, measured rather than argued.** The
  host-vs-guest corpus differential (`payloads_agree`) deliberately
  exempts miss REASONS, because guest wordings differ by design. That
  exemption is what hid this gap for 210 rounds: on the pre-338 guest,
  all six `shape` DECLARATION-error programs miss on both sides, so a
  missed-ness-only comparison rates all six "agree" — while the guest is
  in fact reporting one single reason for six different host errors.
  Over a 32-program case list the pre-round guest scores **14/32
  agreeing** and this one **32/32**; **6 of those 14 are blind ones**.
  So the reason WORDING is where the information is, and
  `test_shape_declaration_errors_agree_host_vs_guest_by_wording` pins it.
- **The one divergence, pinned as pre-existing rather than asserted
  away.** Every reason comparison strips a `(line N)` suffix: the guest
  AST carries no line numbers, so the host attaches `self_eval.lang`'s
  OWN line to a miss the guest constructs. This is documented in the
  example's header and predates this round —
  `test_shape_line_divergence_is_pre_existing_not_new` exhibits the
  identical divergence on a PRIMITIVE `-> num` return, unchanged since
  round 158. Recorded, not stripped quietly.
- **Verification**: `python3 run.py examples/self_host.lang`: 73 -> **94
  passed, 0 failed** (+21 exact). `python3 run.py examples/self_eval.lang`:
  105 -> **123 passed, 0 failed** (+18 exact). 5 new pytest tests in
  `tests/test_self_eval.py`; run inside a pristine package copy with the
  PRE-round `self_eval.lang`/`self_host.lang` dropped in, **3 of the 5
  fail** — real regression guards. The other two pass on both builds
  deliberately and are labelled as such: one pins the adjacency premise
  (the pre-round guest also refused that program, for a different
  reason), the other IS the pre-existing-divergence record. The two
  deepest self-hosting tests were extended rather than duplicated:
  `test_guest_parser_parses_its_own_full_source` (162 -> **195**
  top-level statements), and `test_guest_evaluator_executes_self_host_
  library` (4 -> **8** inner checks), which runs the new
  `shapes_declared_before`/`shape_close` scans under the guest EVALUATOR
  interpreting the guest PARSER — two full levels down. Shared-section
  bounds moved 27:574 -> **27:697** in both the sync test and
  `test_self_hosting.py`'s `LIB_END`.

## v0.18 (round 342, language C) — type names are value names: `shape` becomes block-scoped

- **The defect in one sentence: a `shape` is a `let` (v0.12's own first
  bullet says so), so its name obeys decision 3 at RUN time — bound in the
  block it is written in, shadowable, gone when that block closes — while
  the PARSER kept one flat file-global `self.shapes` dict and accepted the
  name in any annotation anywhere later in the file.** The two namespaces
  had different scope rules for the same name. Round 128 met this as a
  crash (`_UnboundRetType`, below), fixed the crash, and left the cause;
  round 338 had to port the flat table into the self-hosted parser and
  wrote the asymmetry down as a premise (decision 27); round 338's own
  next-steps item 3 asked whether the parser should be scope-aware
  instead. It should.
- **What the missing scope rule cost, measured rather than argued.** One
  mistake — naming a shape whose block has closed — reached run time by
  three different routes and produced three different outcomes, none of
  them at the annotation:

  | annotation | pre-v0.18 outcome |
  |---|---|
  | `fn f() -> L { … }` | every call misses `return value of f: type 'L' is not in scope here` (the `_UnboundRetType` path) |
  | `fn f(p: L) { … }` | every call misses `unbound name 'L'` — different wording for the identical mistake, because a param guard is an ordinary `A.NameRef` walked by the everyday evaluator |
  | `shape W = @{i: L}` | **no miss at all**: `W` is built with a miss-valued `i` field, and only something that later reads `W.i` — or a `matches(x, W)` that quietly answers `false` — ever notices |

  v0.18 makes all three one parse error at the annotation's own line and
  column: `type 'L' is not in scope here`, the same sentence the `->`
  route used to produce per call.
- **Decision 28 (new): the type namespace IS the value namespace, so it has
  exactly one scope rule — decision 3's.** `Parser.self.shapes` becomes
  `self.shape_scopes`, a stack of frames pushed and popped by `stmt_list`
  alongside the seven alias-tracking stacks already there (one frame per
  block, frame 0 = the module; `block()` and `parse_program` are its only
  two callers, so a frame is exactly a `{ … }`). `parse_type` looks up
  innermost-out — the same walk the desugared `let`'s `NameRef` will do
  at run time, which is the whole point. Three consequences, each one an
  ordinary `let`'s behaviour arriving for `shape`:
  1. an annotation naming a shape whose block has closed is refused where
     it is written;
  2. **sibling blocks may each declare the same shape name** (nothing is
     shadowed — the blocks never see each other);
  3. **an inner block may shadow an outer shape name**, and the inner
     annotation means the inner shape while an outer annotation still
     means the outer one (pinned both ways, host and guest).
  (2) and (3) were parse errors before v0.18 — "shape 'S' is already
  declared" — for no reason other than the table being flat.
- **Two messages, because they are two different mistakes.** A name never
  declared anywhere is still `unknown type 'Nope'` (a typo); a name whose
  declaration exists but is out of scope is `type 'L' is not in scope
  here`. `self.shapes_seen` — every completed declaration, never popped —
  exists only to tell them apart and decides nothing about acceptance.
  The declaration's LINE was deliberately left out of the message: the
  guest reproduces host wording exactly and that comparison is what
  `test_shape_declaration_errors_agree_host_vs_guest_by_wording` measures
  (round 338), so a diagnostic the guest would have to reconstruct from
  the token stream — with its own edge cases around incomplete
  declarations — buys less than the differential it would put at risk.
- **The same-block duplicate check is kept, scoped, and reworded** to
  `shape 'P' is already declared in this block`. It is now strictly
  redundant: a `shape` reaches `stmt_list`'s general no-rebinding check as
  an `A.Let`, which would catch it one statement later. It is kept because
  it fires first with the more specific sentence, and because that
  sentence is one of the host/guest wording witnesses round 338 built.
- **`_UnboundRetType` is now unreachable from source text, and stays.**
  `_closure_ret` resolves a `-> Shape` spec directly in Python, not
  through a Whence expression, so a `None` lookup there would raise rather
  than miss — the sentinel is the floor under that, and the floor is worth
  keeping even when the parser above it is sound.
  `test_unbound_ret_type_sentinel_is_still_the_defensive_floor` calls
  `_check_ret` with the sentinel directly, since no program can reach it.
  The guest's mirror (`__unbound_ret`) is kept for the same reason.
- **Annotations are static; expressions stay dynamic.** `matches(r, L)`
  naming an out-of-scope `L` is unchanged: there `L` is an ordinary
  expression, so it is an ordinary unbound-name miss, and `matches` — a
  total builtin — answers `false`. Only `parse_type` positions (parameter
  type, return type, shape field type) got a scope rule, because only they
  are annotations the parser resolves.
- **Guest parity landed the same round, and decision 27 grew a third
  premise.** `shapes_declared_before` (round 338) becomes
  `shapes_before(toks, limit, want, …)` answering three questions —
  `"any"` (declared anywhere earlier, mirroring `shapes_seen`), `"scope"`
  (visible here, mirroring "any frame"), `"block"` (declared in the very
  block this position sits in, mirroring "the top frame"). The new premise
  is that **the host's frame stack is exactly the bracket structure**, so
  the guest can replay it from the tokens alone: `shape_rel_depth` scans
  from the declaration's closing `}` to the use, counting `{` and `@{` up
  and `}` down, and returns the depth RELATIVE to the declaration, or -1
  if the declaring block closed on the way. `>= 0` is "in scope"; `== 0`
  is "same block". Including `@{` in the count is safe and not an
  approximation: a record literal is balanced, so it shifts every position
  inside it by the same constant, and only DIFFERENCES of depth are ever
  compared — which matters, because an annotation really can appear
  inside a record literal (`@{f: fn(a: P) { a }}`) and a `shape` really can
  be declared inside a block inside one.
- **The capture hazard v0.18 makes nameable (pre-existing, deliberately not
  fixed).** Once the parser has an opinion about WHICH declaration an
  annotation names, the run time can be seen to disagree with it. A param
  guard is a prepended `let p = typed(p, <NameRef>, …)` re-evaluated on
  every call, so its spec resolves in the CALL env; a return spec is
  resolved once, at closure creation, in the DEFINING env (`_closure_ret`).
  A block's env is one dict later statements keep adding to — that is what
  makes mutual recursion work — so a binding added AFTER the annotation is
  still visible to a later call. The sharpest witness, pinned as
  `test_one_signature_can_mean_two_different_shapes` (renamed by round 344
  to `test_one_signature_now_means_exactly_one_shape` when v0.19 closed it —
  see `## v0.19`):

  ```
  shape P = @{x: num}
  fn g() {
    fn h(p: P) -> P { p }      # param P and return P are DIFFERENT shapes
    shape P = @{y: str}
    …
  }
  ```

  `h(@{x: 1, y: "a"})` passes; `h(@{y: "a"})` satisfies the param (the
  inner `P`) and misses on the RETURN (the outer one); `h(@{x: 1})` does
  the reverse. Two facts settle what to do about it: (a) it is NOT about
  shapes — a plain `let P = 3` in the same position captures the guard
  identically (`typed spec must be a type name or a shape, got 3`), so
  forbidding shape shadowing would not close it; (b) closing it properly
  means resolving a param spec at closure creation like a return spec,
  i.e. moving param checks from prepended body statements to the call
  boundary — all three call paths, and a changed why-tree for every typed
  function. That is a v0.19-sized change and is named as one, not
  smuggled in here.

## v0.19 (round 344, landed by round 345; specified round 348) — parameter contracts: both ends of a signature become one rule

*Provenance of this section.* Round 344 built v0.19 and was killed by the
driver's 3300 s outer timeout before writing any of it down; round 345
verified the diff from a clean read and landed it as `6132f1f`, deliberately
NOT writing the design rationale for another track's round, and recorded the
dangling `SPEC decision 29` as a language(C) handoff. This section is round
348 discharging that handoff. It is derived from the code and from probes run
against it, not transcribed from round 344's intent, and every behavioural
claim below is pinned by a test named beside it.

- **The defect in one sentence: a `-> Type` and a `p: Type` on the same
  signature were resolved at different times, in different environments, by
  different machinery — so one signature could name two different shapes
  with one name.** v0.13's return annotation was carried on the fn node
  (`FnDef.ret_type`) and resolved ONCE, in the DEFINING env, at closure
  creation (`_closure_ret`). v0.12's parameter annotation was ERASED by the
  parser into a statement prepended to the body:

  ```
  fn f(p: P) { … }        # v0.12-v0.18, after parsing:
  fn f(p) { let p = typed(p, P, "parameter 'p' of f")
            … }
  ```

  so its spec was an ordinary expression walked by the everyday evaluator in
  the CALL env, on every call. The call env's parent is the closure's
  defining env, so most of the time the two agreed — which is exactly why
  this survived seven versions. They disagree when something binds the name
  *between* the two: a `let` in the closure's own block, or the parameter
  list itself.

  ```
  shape P = @{x: num}
  fn f(P, p: P) { p }     # v0.18: the annotation's P is the ARGUMENT
  ```

  `P` is bound in the call env before the prepended guard runs, so `f(3, …)`
  checked `p` against `3` and answered `typed spec must be a type name or a
  shape, got 3`. v0.18 §7 found the shape-shadowing form of this, showed it
  was not about shapes (a plain `let P = 3` captures the guard identically),
  and named the fix as v0.19-sized rather than smuggling it in.

- **Decision 29: a parameter contract and a return contract are ONE rule,
  resolved at ONE moment in ONE environment.** The parameter half moves onto
  the node beside the return half:

  | | v0.13 return | v0.19 parameter |
  |---|---|---|
  | carried on | `FnDef.ret_type` / `FnExpr.ret_type` | `FnDef.param_types` / `FnExpr.param_types` |
  | built by | `parser._type_spec_expr` | `parser._param_contracts`, same spec-expr shape |
  | resolved by | `_closure_ret` → `_closure_spec` | `_closure_params` → **the same `_closure_spec`** |
  | resolved when | closure creation, defining env | **closure creation, defining env** |
  | checked by | `_check_contract` | **the same `_check_contract`** |

  `_check_ret` is renamed `_check_contract` because it was never about
  returns: it is "check one half of a contract at the one point every call
  path has the value in hand". `_mk_closure` is the single choke point all
  five FnDef/FnExpr construction sites (fast, direct, three generator sites)
  go through, so closures built for the same function by any evaluation mode
  agree byte for byte on `ret_spec` / `ret_label` / `param_specs` — which
  the three-way fast/direct/trampoline differential requires.

- **A parameter annotation no longer changes the body.** `fn f(p: num) { p }`
  and `fn f(p) { p }` now have byte-identical bodies; the annotation lives
  entirely on the node. Two consequences that are not cosmetic: a satisfied
  parameter contract leaves NO node in the why-tree (`_check_contract`
  returns its input unchanged), exactly as a satisfied `-> Type` already
  left none; and `self_host.lang`'s round-338 pin
  `len(parse_whence("fn f(a) { a }…").stmts[0].param_types) == 0` now
  measures the annotation's absence on the node rather than the absence of a
  prepended statement.

- **The check runs at every site that binds a parameter — all three of
  them.** `_check_params(vs, param_specs)` is applied immediately after the
  `Prov("arg", …)` bindings in `_call_direct` (the direct/trampoline loop),
  `_closure_inline` (the F2 fast path for a call-free body) and `_call_gen`
  (the generator loop). Round 128 found the mirror-image bug on the return
  half — `_closure_inline` was a THIRD place a call settles and was missing
  `_check_contract` entirely, so a `-> Type` on any call-free-bodied
  function was silently never checked — which is why the audit here is
  "every `Prov("arg", …)` site", not "every call path in the docstring".

- **Four asymmetries REMAIN, and all four are deliberate.** Decision 29 says
  the two ends are one *rule*; it does not say they are the same *event*.
  Each of these is a place where the ends genuinely differ:

  1. **When.** Parameters are checked as the call env is entered, before the
     body; the return is checked once the body — and any merged tail chain —
     has settled.
  2. **Tail chains.** `ret_spec` is captured ONCE from the originally-called
     closure, before the tail loop may reassign `p`, because a `-> Type` is
     a contract on what THIS call returns to ITS caller (v0.13); the
     contracts of closures the loop bounced *through* are collected in
     `chain_rets` and applied innermost-first (round 336). `param_specs` is
     the exact opposite: it is re-read beside `params` on every hop, because
     it guards the closure being ENTERED and its values cross that
     closure's own boundary. Verified: in `fn a(n: num) {… b(n-1) }` /
     `fn b(n: str) { a(n) }`, hop 2 blames `parameter 'n' of b`.
  3. **Which line is blamed.** A parameter miss reports the function body's
     opening line — where the contract is WRITTEN — because the offending
     argument is right there in the miss's inputs carrying its own call-site
     line. A return miss reports the CALL's line, which is round 336's rule
     and is what lets a merged tail chain say which hop it is blaming. v0.19
     unified the CHECK; it deliberately did not unify the blame location.
  4. **What a failure does.** A failing parameter check binds the miss and
     **the body still runs**. It does not short-circuit the call, so a
     function that never reads a badly-typed parameter still returns
     normally (`fn f(p: num) { 42 }`; `f("s")` is `42`). This is inherited
     from the v0.12 guards unchanged, so that moving the check did not also
     change what it means — and it is consistent with decision 2, under
     which an unobserved miss is simply never observed. Making a bad
     parameter abort the call is a separate decision with its own corpus
     cost and is named as one here rather than smuggled in.

- **Two guard branches now protect the parameter half too, and one of them
  was a live totality violation.** `_check_contract` sits ahead of
  `_type_match`, which documents `_spec_ok(spec)` as its PRECONDITION:
  - `_UnboundType` — the annotation named a shape with no binding at
    closure-creation time. v0.12-v0.18 the parameter half degraded on its
    own (a guard's spec was an ordinary `A.NameRef`, and the everyday
    evaluator turns an unbound name into a miss); resolving it in Python
    like the return half means it now needs, and shares, the same floor.
    Unreachable from source text since v0.18 made the parser scope-aware,
    and kept anyway as the floor under `_closure_spec`.
  - `not _spec_ok(spec)` — the name resolved to something that is not a
    usable spec. Round 335 added this guard to `typed`/`matches` and
    recorded `_check_ret` as "has no `_spec_ok` guard, unreachable today".
    That was wrong, and round 344 measured it: an ordinary `let P = 3`
    shadowing a shape name inside a block made `fn h() -> P { 1 }` raise
    `AttributeError: 'int' object has no attribute 'fields'` straight out
    of the interpreter, in all three modes, for both `FnDef` and `FnExpr`,
    tail and non-tail — a crash where decision 2 promises a miss. It is now
    an ordinary miss with `typed`'s own wording for the same condition.

- **v0.18 §7's hazard is closed, and this is the check that shows it.**
  Re-run against v0.19 (round 348):

  ```
  shape P = @{x: num}
  fn g() {
    fn h(p: P) -> P { p }
    shape P = @{y: str}
    h(ARG)
  }
  ```

  | `ARG` | v0.18 | v0.19 |
  |---|---|---|
  | `@{x: 1, y: "a"}` | passes | passes |
  | `@{y: "a"}` | passes the param (inner `P`), misses the return (outer `P`) | **misses the param** — one `P`, the outer one |
  | `@{x: 1}` | misses the param, passes the return | **passes both** |

  v0.18 §7 cited `test_one_signature_can_mean_two_different_shapes`; round
  344 renamed it `test_one_signature_now_means_exactly_one_shape`
  (`tests/test_v12.py`), which is the sentence v0.19 is for.

- **The index is kept on the AST and dropped at resolution.** Every host
  call path binds parameters by NAME into the call env's `vars`, so a name
  is what `_check_params` needs and carrying an index as well would be a
  second way to say the same thing. `parser._param_contracts` keeps it
  because a POSITIONAL consumer wants it — and `self_eval.lang`'s own
  `bind_params`, which walks parameters by position and finds its entry with
  a linear `param_spec_at` scan, is that consumer. `param_specs` holds only
  the ANNOTATED parameters, so `fn f(a, b: num)` has exactly one entry, at
  index 1.

- **Guest parity landed in the same round** (`examples/self_eval.lang`):
  `resolve_spec` is the guest's `_closure_spec` — ONE lookup, used by both
  halves, which is the point of the round in a nutshell — with
  `resolve_ret_spec` and `resolve_param_specs` above it, and `bind_params`
  applying the parameter half as each argument crosses the call boundary.
  Round 344 also closed round 335's open item "the guest does not mirror
  `_spec_ok`" (`guest_spec_ok` / `guest_spec_fields_ok`), because v0.19 is
  what made the malformed-spec case reachable from an ordinary annotation on
  both sides.

- **Measured (round 348), because the round that built it could not.** A
  16-program parameter-contract corpus — named and anonymous fns, one and
  two annotated parameters, an unread parameter, shadowed shapes, tail
  chains, a re-read-per-hop chain, shape specs, `guess`, `any`, an
  already-missed argument, both ends failing at once — run on the host in
  all three evaluation modes and through `self_eval.lang`, comparing the
  full miss REASON and not merely missed-ness:

  ```
  host fast / direct / generator : 3/3 identical on all 16
  host vs guest (reason text)    : 16/16 identical
  ```

  Miss reasons are an explicit exemption of the ordinary guest differential
  (round 17), so agreement here was not implied by the suite that was
  already green; `test_param_contract_wording_agrees_host_vs_guest`
  (`tests/test_v20.py`) is what keeps it. The one thing that does NOT agree
  is the miss's LINE — the guest's misses carry a line in `self_eval.lang`,
  not in the program under test — which is structural and pre-existing
  (round 338's `test_shape_line_divergence_is_pre_existing_not_new`).


## v0.20 (round 348, language C) — a type miss names the field

- **The defect in one sentence: `_type_match` walks a record spec field by
  field, knows exactly which field broke the match and how, and threw all of
  it away — returning only the spec's NAME.** So the entire contract system
  answered a structural mismatch with the one thing the reader already knew:

  ```
  shape Point = @{x: num, y: num}
  fn midpoint(l: Line) -> Point { @{x: (l.a.x + l.b.x) / 2} }

  return value of midpoint expected Point, got record        # v0.19
  ```

  Which field? The message cannot say, and on a hand-built spec — legal, and
  ordinary under this file's own "structural, not nominal" rule, where "a
  record built entirely by hand, with no relation to the shape ever
  declared, matches it exactly as one built from it" — the spec has no
  `__shape`, `desc` falls back to `"record"`, and the whole sentence
  degenerates to:

  ```
  parameter 'p' of g expected record, got record             # v0.19
  ```

  which says nothing at all. Decision 2's promise is that a miss, unlike a
  NaN, *can tell you why*. This is where the newest and most-used contract
  surface stopped keeping it.

- **Decision 30: a type miss names the FIELD.** A failed check appends the
  PATH to the field that broke it, in one of three forms:

  ```
  parameter 'l' of length expected Line, got record (no field 'a'.'y')
  parameter 'p' of f expected P, got record (field 'x' expected num, got str)
  parameter 'p' of f expected P, got record (field 'x' is a miss)
  ```

  and, on the case that used to say nothing:

  ```
  parameter 'p' of g expected record, got record (no field 'y')
  ```

  A nested path is dotted per level (`field 'b'.'a'.'n' expected num, got
  str` for three shapes deep). The clause is OMITTED, leaving v0.12's
  sentence exactly as it was, when there is nothing more to say: a
  primitive-tag spec (`expected num, got str` is already complete) and a
  non-record payload (`got num` already says why).

- **It is a SEPARATE walk, not a third return value from `_type_match`.**
  `_type_match` runs on every `matches` call, on every SATISFIED contract,
  and as its own recursive worker; an extra allocation per level would be
  paid by the success path. `_match_why(payload, spec, path="")` runs only
  after a failure, from the two sites that build a message, and
  `_mismatch_reason` is the single place both of them build it — the same
  reason `_check_contract` is one function for both contract ends.
  `matches` is untouched: it returns a bool and has no message to improve.

- **Fields are visited in SORTED order, not declaration order, and the
  reason is decision 27.** Which field a multi-field mismatch names is
  arbitrary either way. Declaration order survives in the host's `fields`
  dict but is NOT recoverable through any Whence builtin — `keys()` sorts —
  so `self_eval.lang`, Whence's own definition of Whence, could not mirror a
  declaration-order rule at all, and the two sides would name a different
  field in every multi-field mismatch. A rule the guest cannot express is a
  rule the two implementations will silently disagree about; the host walks
  `sorted(spec.fields)` so that both sides can walk the same list.

- **Four surfaces improved from one change, which is decision 29 paying
  out.** `typed(x, spec, label)`, `-> Type` (v0.13), `p: Type` (v0.19) and
  every `shape` in every example all build their mismatch text through
  `_mismatch_reason` now. Before v0.19 the parameter half went through a
  prepended `typed()` call and the return half through `_check_ret`, and
  this would have been two changes that could drift; `examples/shapes.lang`
  demonstrates both ends in one file and pins both clauses as in-language
  `check`s.

- **Guest parity landed the same round.** `guest_match_why` /
  `guest_match_why_at` / `guest_mismatch_reason` in `examples/self_eval.lang`
  mirror the host, walking `keys(spec)` (already sorted) and skipping
  `__shape`, with `is_callable(v)` tested before `is_record(v)` for the
  reason `guest_spec_ok` gives — a guest closure is an ordinary record under
  the hood, and the host's `isinstance(payload, Record)` excludes a Closure
  (round 18's tag-spoofing shape). `matches(fv, fspec)` is exactly the
  host's `_type_match(fv, fspec)[0]` at every level here, because every
  caller has already established `guest_spec_ok(spec)` and that check is
  recursive, so no nested spec can be the malformed kind `matches` answers
  false for on principle rather than on structure. One naming note: `why` is
  a KEYWORD, so the guest's local is `clause` where the host's is `why`.

- **Measured.** A 17-program corpus (missing field, wrong field type from
  each end, nested to two and three levels, a miss-valued field, the
  `typed` builtin with a hand-built record spec, a shadowed shape resolving
  to a plain record, a non-record payload, a primitive spec, sort order with
  `b` declared before `a`, a callable value, `matches` still returning a
  bool) run on the host in all three modes and through `self_eval.lang`,
  comparing full reason text: **3/3 modes identical, 17/17 host vs guest
  identical.** `tests/test_v20.py`.

- **What this deliberately does NOT do.** It does not report EVERY failing
  field — the first in sorted order wins, matching `_type_match`'s own early
  return, and a full failure list would be a different feature with a
  different rendering problem. It does not change what MATCHES: no program's
  value changes, only the text of a miss that was already a miss, which is
  why the whole change is invisible to the guest differential's payload
  comparison and had to be pinned by wording (round 17's exemption again).
  And it does not touch `matches`, `shapeof`, or the parse-time errors of
  v0.18.

## v0.21 (round 350, language C) — the lexer's grammar is ASCII, and the guest lexer is checked against the host rather than against its history

Round 332's next-steps item 1 asked for *"an exhaustive sweep of
`whence/lexer.py`'s full history against the guest `lex` function"*. It was
carried unchanged for sixteen rounds; round 348 said the seventeenth was the
worst option. The sweep takes five minutes:

```
$ git log --follow --oneline -- languages/whence/whence/lexer.py
7b3afcb  Round 323 (SWE-loop D)   exponent literals
8d92ff9  Round 144 (language C)   `->` into TWO_CHAR_OPS and CONTINUES
ee30654  Initial clean commit v3  (the whole file; no parent to diff against)
```

Two semantic diffs in the lexer's entire recorded history, and the guest
mirrors both (`two_char_ops`/`continue_ops` carry `->`; round 332 added
`exp_end`). **A history sweep covers two lines of a two-hundred-line lexer
and says nothing about the rest, because the rest never was a diff.** The
item was undischargeable as worded, not merely unscheduled. What can settle
the question is comparing what the two lexers DO, and doing that found four
guest disagreements, two host defects, and one CLI defect — none of which a
history read could have surfaced.

### The host: names and numerals are ASCII

`whence/lexer.py` classified characters with `str.isdigit()`,
`str.isalpha()` and `str.isalnum()` from its first commit. Those are
Python's UNICODE predicates, and two things followed.

**`str.isdigit()` is true for 798 characters.** `let x = ٣` (Arabic-Indic
three) lexed to `NUMBER 3`. Nothing chose that; nothing documented it. This
file's own `## Limits that are errors, not crashes` has said the opposite
since v0.4.1 — Whence number syntax is "optional sign, **ASCII digits**,
optional fraction, optional exponent" — and `interp.py`'s `_NUM_RE` enforces
exactly that for `num(text)`, with a comment naming "non-ASCII digits" among
the host-only spellings that are *not* numbers here. So `num("٣")` was a
`cannot parse` miss while the literal `٣` was the number three. The literal
grammar and the documented grammar disagreed.

**For 128 of those 798 characters `int()` raises.** `let x = ²` was an
uncaught Python `ValueError` out of `tokenize` — not a `LexError`, not exit
2, not a miss, a traceback. A one-character source file crashed the
implementation. Both the float branch (`².5`) and the int branch reach it,
and a valid ASCII literal with one of these appended (`1²`) reaches it too.

This is the same defect round 323 found and half-fixed: the literal grammar
drifting from `_NUM_RE`. Round 323 closed the *exponent* half (`1e5` had no
lexer support at all while `num("1e5")` worked). v0.21 closes the *digit-set*
half.

`_DIGITS`, `_NAME_START` and `_NAME_CONT` are now explicit ASCII strings.
`let x = ²` and `let x = ٣` are `unexpected character` lex errors. Names
narrow for the same reason plus a third: `examples/self_eval.lang`'s guest
lexer has only ever had `contains("abcdefghijklmnopqrstuvwxyz…", c)`, a guest
written in Whence cannot enumerate Unicode, and so parity on names is
unreachable in the widening direction and free in the narrowing one. Zero of
the thirty `.lang` files in this tree contain a non-ASCII NAME token, so the
narrowing costs nothing that exists.

**Source text is still UTF-8 and STRINGS and COMMENTS still hold any
character.** Only identifiers and numeric literals are ASCII.

### The host: `\r` is writable

The lexer has skipped a carriage return in source since its first commit
(`if c in " \t\r"`, so a CRLF file lexes), and the escape table had `\n`,
`\t`, `\"` and `\\` but no `\r` — a character the language knew about and
could not name. `_ESCAPES` gains `"r"`. That is what made the guest fix
below writable at all: a guest lexer written in Whence cannot test for a
character Whence cannot spell.

### The CLI: a lex error is exit 2

`run.py` caught `ParseError` and not `LexError`, so **every** lex error —
`$`, an unterminated string, a bad escape — left the CLI as a raw Python
traceback with exit **1**, while `## Running` above has always promised
`exit … 2 (lex/parse error)` and a parse error already did exactly that.
Exit 1 is the "some check failed" code, so a caller could not tell a program
whose checks failed from a program that does not lex. Every other entry
point in the tree (`bench/ref_diff.py`, `bench/reserve_probe.py`,
`tests/test_generated_killers.py`) already catches the two exceptions
together, which is what makes this an oversight rather than a decision.

### The guest: four disagreements

Found by comparing token streams, all fixed in `examples/self_eval.lang` and
`examples/self_host.lang` (the lexer section is byte-identical in both and
pinned by `test_parser_section_matches_self_host`).

| | host | guest, before v0.21 |
| --- | --- | --- |
| `\r` in source | skipped as whitespace | `bad: unexpected character` |
| raw newline inside a string literal | `unterminated string` | consumed; a multi-line string token the host refuses |
| overflowing literal (`1e400`, a 400-digit literal with a fraction) | `inf` | a **miss**, as the token's value |
| a lex error's message | `unterminated string` | `unterminated string (line 161)` |

The overflow one is the instructive one. Round 332 mirrored the exponent
SCAN into `exp_end` and silently inherited `num`'s CONVERSION with it —
`num(text)` answers an out-of-range finite-syntax string with an `out of
range` miss, a string-conversion rule that `whence/lexer.py`'s own comment
is careful to separate from the literal-grammar rule, and the guest used
`num` for both. The 400-digit case predates round 332 entirely. The fix is
`lit_num`, which falls back to `pos_inf` — bound to the literal `1e400`, so
the guest gets the host's answer the host's own way, one level up. A literal
the scan produced is always valid Whence number syntax and never signed
(`-1e400` is the op `-` then the literal), so "out of range" is the only way
`num` can fail on it and the overflow is always toward `+inf`.

The message one: `miss "unterminated string"` gives a reason of
`unterminated string (line 161)`, and 161 is a line in `self_eval.lang`. A
guest lex error was describing the program being lexed with a coordinate
into the lexer's own source, and it moved every time the file was edited.
`lex_str_body` now returns `@{err: …}` instead of a miss.

### The instrument

`tests/test_lexer_guest_parity.py`. Three rules:

1. **Acceptance agrees.** `tokenize(src)` raises a `LexError` if and only if
   `lex_all(src)` ends in a `bad` token.
2. **On acceptance the streams are equal** — kind, value and line, element
   for element, EOF included.
3. **On rejection the messages are equal**, minus the position.

Plus **table parity**: the host's eight keyword/operator/character tables
against the guest's own bindings, read out of a real interpreter run. Round
144 added `->` to `TWO_CHAR_OPS` *and* `CONTINUES`, and nothing in this tree
would have failed if it had touched one and not the other, or the host and
not the guest. That is the mechanism by which a lexer table drifts, and it
is now a test failure.

Two things are pinned as real divergences rather than fixed. Guest tokens
carry no `col` (nothing in the guest parser reads one). And the host builds
its message with Python's `%r`, which switches quote style for `'` and
doubles a backslash, while Whence has no `repr` — established exhaustively
over printable ASCII to be **exactly two characters**, not a sample.

### Measured

- 70-case hand corpus, one per branch of `tokenize`: 0 divergences.
- **All 30 `examples/*.lang` files, ~37,000 tokens, including
  `self_eval.lang` lexing its own 138 KB source: 0 divergences.**
- `self_host.lang`'s own check section 102 → 109; the guest-EVALUATOR
  checkpoint (`test_guest_evaluator_executes_self_host_library`) 11 → 14
  checks, so each fix is also proved two levels of interpretation down,
  under store-passing, which is where round 192's newline-continuation bug
  was actually caught.
- `languages/whence` fast tier 1049 → **1137** passed / 53 deselected.

### What this deliberately does NOT do

It does not widen the guest to Unicode — that is not implementable in
Whence. It does not make an overflowing literal an error: `inf` is pinned by
`test_exponent_overflow_becomes_inf_not_a_lex_error` and by the fuzz
regression corpus, and v0.21's job was to make the guest agree with the
host, not to relitigate what the host does. And it does not touch the
PARSER's own host/guest parity, which has its own differential
(`tests/test_parser_differential.py`) and its own history.

## v0.22 (round 354, language C) — an error that can name the fix, names it

Decision 32. Two surfaces, one rule, and both of them exist because of a
single operator bug report against v0.19 that round 349 answered *as
documentation* and this round finishes *as language*.

### The report, and what was left of it

> `fold()` returns Miss instead of calculated values when using inline
> lambdas or external functions. … The parser requires explicit `{}` blocks
> for all if/else branches in v0.19. Document this strictly and consider
> auto-fixing older scripts.

Round 349 established that neither half was a defect. `fold(nums, 0,
fn(acc, x) {...})` misses because Whence's higher-order builtins take the
FUNCTION FIRST, and the braces rule is how the grammar has always read. It
wrote the `## Builtins` signature table and `### Blocks are always braced`,
and it pinned both (`tests/test_spec_builtins.py`).

What it could not do from the harness track is the part that is the
language's own job. In both halves the interpreter knew the cure and said
only the symptom:

```
fold needs a list, got <fn>                  # true. now what?
expected '{', got 'print' at line 2, col 10  # true. now what?
```

That is decision 2's promise ("unlike NaN it can tell you *why*") read at
half strength for twenty-two versions.

### (a) The builtin half — `(arguments fit fold(fn, acc, xs))`

Every builtin now declares its parameter names and argument kinds:

```python
@register("fold", 3, "fn:fn, acc, xs:list")
@register("push", 2, "xs:list, x")
@register("guess", 3, "value, conf:num, source:str")
```

A bare name is kind `any`; `name:tag` constrains a position to one
`_kind()` tag and `name:a|b` to a union. `sig` is a REQUIRED positional
argument of `register`, so a builtin added later cannot quietly opt out.

When a handler rejects an argument for its kind, `_order_hint(name, args)`
re-checks the arguments the caller actually supplied against the
declaration in every other order. If any order fits, the reason gains a
clause:

```
fold needs a list, got <fn> (arguments fit fold(fn, acc, xs)) (line 2)
push needs a list, got 7 (arguments fit push(xs, x)) (line 1)
guess confidence must be a number between 0 and 1, got "src"
  (arguments fit guess(value, conf, source)) (line 1)
```

**EXISTENCE, not uniqueness.** The sentence claims that the arguments fit
the signature in *some* order and then names the signature — true as soon
as one order fits, and its text does not depend on which one. An earlier
draft demanded a unique fitting order on the reflex that ambiguous advice
is bad advice; but the advice IS the signature, which is the same string
for every fitting order, so uniqueness would only have suppressed hints
without making any surviving hint truer. `guess("s", 1, 2)` fits in two
orders and gets the clause.

**The three silences are the load-bearing half.** No clause when: there is
no declared signature for that argument count (an ARITY error is a
different, already-precise miss); there are fewer than two arguments; or
**the given order already satisfies the declared kinds** — which means the
miss is about something the kinds do not model (`filter`'s predicate
returning a non-bool, a confidence outside [0, 1], a record that is not a
well-formed `typed` spec) and reordering would not help. That last case is
what stops the clause being pasted onto misses it does not explain, and it
is why `_order_hint` is self-guarding rather than needing a whitelist of
call sites.

The clause does NOT promise the reordered call succeeds — `fold(fn, acc,
xs)` with a callback that misses still misses. It promises exactly what was
checked: the kinds line up that way.

A `guess`-wrapped list is kind `guess`, not `list`, so
`map(f, guess(xs, 0.9, "s"))` gets no clause. Correct: v0.15 is
deliberately shallow and the cure there is `sure()`, not reordering.

**The declaration pays for itself twice.** `tests/test_spec_builtins.py`
now checks this document's argument NAMES against `_BUILTIN_SIGS`, not just
its arities — and round 349's `assert "fn, acc, xs = args" in src`, a grep
for a local-variable assignment because there was nothing better to read,
becomes an assertion about the thing the interpreter actually uses.

### (b) The parser half — five hints, chosen by measurement

The operator asked whether to auto-fix older scripts for the braces rule.
The scripts exist: ten machine-written Whence programs sit untracked in
`examples/` (a separate system's output — `state/known-standing-dirty-
paths.json`). All ten fail to parse. Measured before deciding:

| cause | files | before v0.22 | after |
| --- | --- | --- | --- |
| unbraced `if`/`else`/`fn` body | 2 | bare | hint |
| `if` without `else` | 1 | already named its cure | unchanged |
| `x = 2` assignment | 1 | bare | hint |
| `rescue { } catch` block | 2 | bare | hint |
| `{a: 1}` record literal | 1 | bare | hint |
| two adjacent names | 3 | bare | 2 hint, 1 bare |

Six distinct causes; the braces rule is TWO of them. Auto-fixing braces
would have repaired a fifth of the corpus and left the rest failing with
errors that still named no cure. But every one of the six is the same
underlying mistake in different clothes — the author reached for a
mainstream construct Whence deliberately does not have — so the answer was
to make the errors teach:

```
unexpected '=' (Whence has no assignment; a name binds once
  — write `let name = value`) at line 2, col 3
unexpected ':' (records are written `@{a: 1}`, not `{a: 1}`) at line 1, col 11
unexpected 'rescue' (`rescue` is infix: `risky rescue fallback`) at line 1, col 9
expected ], got 'Unit' (two names in a row: Whence has no juxtaposition
  — a call is `f(x)` and text must be quoted) at line 1, col 20
```

**One of ten was still bare, and the reason was a grammar property, not a
missing hint.** `let d = f one, two` could not be diagnosed at the mistake
because the parser ACCEPTED it: Whence statements needed no separator, so
`let d = f` and `one` were two complete statements on one line and the error
surfaced three tokens later at the `,`, where the adjacency was no longer
visible. The two juxtaposition cases that ARE hinted happen inside brackets,
where the statement rule could not swallow them. v0.22 pinned this as a known
property rather than fixing it — a mandatory statement separator is a real
grammar change with its own guest-parity obligations and belongs to its own
round. **v0.23 (round 356) is that round**, and the corpus went 9/10 to
10/10 with no new hint written; see `## v0.23` below.

Two rules deserve their exactness noted. The `{a: 1}` case is caught by a
two-token lookahead in `block()` — a block statement can never begin
`NAME :` or `STRING :`, so the pattern identifies a record literal missing
its `@` unambiguously, and without it the error lands on the `:` two tokens
past the actual mistake. And the juxtaposition rule excepts exactly one
word: `shape` is a SOFT keyword (`lexer.KEYWORDS` has 14 words and it is
not one of them), so `shape Foo` is the grammar's one legal `NAME NAME`.

**The parser half needs no guest mirror**, and that is established rather
than assumed. Host parse errors are exceptions carrying line AND column;
guest parse errors are `miss` values carrying a line only, and the two have
never used the same words (`unexpected '=' at line 2, col 3` vs `unexpected
token '=' at line 2`). Adding a clause to one cannot create a divergence
where there was never an agreement — pinned by
`test_parse_error_wording_is_not_a_guest_contract`, so a future round that
DOES make them agree finds this decision instead of rediscovering it.

### Guest parity for the builtin half, and three bugs it found

`self_eval.lang` re-implements `map`/`filter`/`fold`/`find` (everything else
is delegated to the host, which appends its own clause, so parity there is
free). Mirroring `_order_hint` in Whence is decision 31 in the small: the
host enumerates orderings with `itertools.permutations`, the four mirrored
builtins take two or three arguments, and two and three arguments have two
and six orderings, so the guest lists them. The one subtlety is that a
guest closure IS a record under the hood, so the kind test must use the
existing `guest_kind` (callable before record) and not `shapeof`.

Writing the wording differential found **three pre-existing divergences**
that no test could have caught, because the ordinary corpus differential
exempts miss reasons by design (round 17):

1. `fold`/`map`/`filter`/`find`'s "needs a list" miss rendered a callable
   with `str(strip(...))`, dumping the guest's own closure record —
   `@{__tag: "closure", body: @{…}, env: ["f1", "f0"], name: "(anonymous)",
   …}` — where the host says `<fn>`. Round 156 wrote `show_callable`
   for exactly this class and it never reached these four sites, so the
   guest leaked its evaluator's internals into a message about the user's
   program.
2. `filter predicate must return true/false` — the guest dropped the
   host's `, got 5`.
3. `find predicate must return true/false` — same.

All three predate this round (verified against the committed tree) and are
fixed here.

### Measured

```
languages/whence  pytest tests/            1191 passed, 54 deselected
                                           (350/351 baseline 1137, +54)
                  run.py examples/self_eval.lang   142 passed, 0 failed
                  run.py examples/self_host.lang   109 passed, 0 failed
tests/test_v22.py                          53 passed (1 whence_slow)
machine-written corpus                     1/10 named a cure -> 9/10
```

### What this deliberately does NOT do

It does not make the hint a separate value or provenance field: the clause
rides on the miss's REASON, exactly as v0.20's field clause does, so it
reaches `reasons`, `why`, `blame` and a failing `check` report with no new
surface and the miss's provenance INPUTS are untouched (round 347 put
`fold`'s accumulator back into them and this must not undo that). It does
not add kinds to one-argument builtins, whose declaration is a name only —
there is no other order for one argument, so a kind there would be an
assertion nothing executes. It does not require a statement separator (v0.23
does). And
it does not touch `matches`, which returns a bool and has no message.

## v0.23 (round 356, language C) — a line break is the only statement separator

Decision 33. One rule, two implementations (host and guest), and it exists
because v0.22 could not finish its own job without it.

### The gap v0.22 left, in its own words

Round 354 measured decision 32's parser half against the ten machine-written
Whence programs a separate system leaves in `examples/`. Nine gained a cure.
The tenth did not, and the reason was written down at the time:

> `let d = f one, two` cannot be diagnosed at the mistake because the parser
> ACCEPTS it: Whence statements need no separator, so `let d = f` and `one`
> are two complete statements on one line and the error surfaces three tokens
> later at the `,`, where the adjacency is no longer visible.

That is not a missing hint. It is the grammar destroying the evidence before
any hint could be computed. `Parser.stmt_list` looped `statement()` until its
end token with `skip_newlines()` in between, so a newline was *permitted*
everywhere and *required* nowhere — while `lexer.py`'s own first line has
said "Newlines are statement separators" since its first commit, and this
document's `## Syntax` heading has said the same. The separator was
documented and unenforced for twenty-two versions.

### The rule

Between two statements there must be at least one NEWLINE token. Three
qualifications, each of which is the design rather than a caveat.

**1. Only BETWEEN.** Nothing is required before the first statement or after
the last: `at(end)` is what closes a block, so `{ x }`, `let a = 1` with no
trailing newline, and a file starting with blank lines are all unchanged. A
run of newlines is one separator. A trailing `#` comment separates, because
the comment ends at the line break the lexer then emits — and there is no way
to write a comment that does *not* end the line, so a comment can never
separate on its own.

**2. Only for a token that could START a statement.**

```python
_STARTS_STATEMENT_TYPES = frozenset(("NUMBER", "STRING", "NAME", "[", "@{", "(", "{", "-"))
_STARTS_STATEMENT_KWS   = frozenset(("let", "fn", "check", "if", "true", "false",
                                     "why", "snip", "miss", "not"))
```

Every other token is not a second statement that needed a newline in front of
it — it is a token that can never start a statement at all, and it must keep
the diagnosis it already had:

```
let x = 1
x = 2      -> unexpected '=' (Whence has no assignment; a name binds once
                — write `let name = value`) at line 2, col 3
```

A separator rule that shadowed that would have made decision 32's own
regression tests go quiet, which is the failure mode this qualification
exists to prevent. The set of keywords excluded is exactly the four infix
ones — `and`, `or`, `rescue`, `else` — every keyword that needs a left
operand. `tests/test_v23.py::test_every_token_is_classified_by_whether_it_can
_start_a_statement` re-derives both sets from the parser over all 40 tokens
rather than trusting the constants.

**3. The error names the cure, and defers when the newline is not the cure.**

```
let a = 1 let b = 2
  -> two statements on one line (a line break is the only statement
     separator Whence has — start `let` on the next line) at line 1, col 11

let d = f one, two
  -> two statements on one line (two names in a row: Whence has no
     juxtaposition — a call is `f(x)` and text must be quoted) at line 1, col 11
```

The second is the point. A NAME touching a NAME is a paren-less call or an
unquoted string; telling that author to add a newline would be advice for a
mistake they did not make, so the site reuses decision 32's own juxtaposition
rule verbatim. `statement()`'s comment had already claimed "no other legal
statement starts with two bare names in a row" — true of the `shape` head,
and false in general only because two statements could share a line. v0.23
makes the sentence true, and a `shape` HEAD after another statement is
excluded by the same three-token test `statement()` uses, so it draws the
separator hint and not the juxtaposition one.

### The honest limit

`-`, `(` and `[` both start a statement and continue an expression
(subtraction, a call, an index). After an expression statement the
longest-match grammar has already consumed them by the time `stmt_list`
looks:

```
let a = 1 -2      -> ONE statement; `a` is -1
let a = 1 (2)     -> ONE statement; a call
let a = 1 .x      -> ONE statement; a field access (`.` is not a statement head)
fn f() { 1 } (2)  -> two statements on one line   # `fn` cannot be extended
```

This is automatic-semicolon-insertion's hazard, and Whence has it in exactly
three places instead of everywhere. It is a property of having both prefix
and infix `-`, not of this rule; removing it would mean either a real
separator token or newline-sensitive expression parsing, and both are larger
languages than this one. Written down (`test_a_token_that_also_continues_an
_expression_is_absorbed_first`) rather than left to be discovered.

### Guest parity

`examples/self_host.lang`'s `parse_stmt_list` implements the identical rule
(`after == s.pos` is "`skip_nl` found no newline"), with `starts_stmt` and the
`stmt_start_kws`/`stmt_start_ops` lists mirroring the host's two frozensets;
`examples/self_eval.lang` carries the byte-identical copy, which grew from 773
to 803 lines. Host and guest agree on ACCEPT/REFUSE over a 23-program corpus.
They do NOT agree on wording, by design and as before: host parse errors are
exceptions with a line and a column, guest ones are `miss` values with a line
(`tests/test_v22.py::test_parse_error_wording_is_not_a_guest_contract`).

### What it cost

One tracked program. `examples/effects.lang` had
`fold(fn(acc, x) { debug_print(x) acc + x }, 0, xs)`; it is now three lines.
Fifteen of the sixteen tracked `.lang` files were already conformant, which is
the measurement that says this rule matches how the language was actually
being written.

The one interesting cost is in the test suite. Round 336's tail-vs-lifted
differential rewrites every tail call `f()` to `let t = f()  t` **on the same
line**, so a `-> Type` miss must report the same line under both forms; round
353 named line-alignment as what makes that oracle strict. Decision 33 forbids
the one-line spelling — but alignment, not one-line-ness, is what the oracle
needs. Both forms now take exactly two lines per function (the tail form's
second is blank), every call site keeps its line number, and the differential
is unchanged in strength: 75 + 375 programs at 2 and 3 hops, 1875 more at 4.

### Measured

```
languages/whence  pytest -m "not whence_slow"     1249 passed, 57 deselected
                                                  (354 baseline 1191; 355 1193)
                  tests/test_v23.py               59 passed (3 whence_slow)
                  run.py examples/self_host.lang  112 passed, 0 failed (was 109)
                  run.py examples/self_eval.lang  142 passed, 0 failed
                  tracked .lang files that parse  16/16
machine-written corpus, cures named               9/10 -> 10/10
```

### What this deliberately does NOT do

It does not add a `;`. A separator token would make the newline rule optional
again and put the language back where it started, one keystroke louder. It
does not make newlines significant anywhere else — `( ) [ ] @{ }` suppression
and the continuation rule after a trailing operator are untouched, which is
why a block inside a call's parens still separates on newlines and
`examples/effects.lang`'s fix is a normal-looking lambda. It does not change
any wording the guest and host already disagreed on. And it does not tighten
the three expression-continuation tokens, for the reason given above.

## v0.24 (round 360, language C) — a position is a fact about the program

Decision 34. Two implementations, one question they had never been asked:
**where does a program stop being legal?**

The corpus that could answer it did not exist. `test_parser_differential.py`
(round 320) compares host and guest ASTs and has only ever been fed programs
that PARSE. `test_lexer_guest_parity.py` (round 350) compares rejection, but
only the lexer's. Round 354 established, correctly, that host and guest parse
error WORDING had never agreed and pinned that as a deliberate non-contract.
What nobody had checked was whether the two parsers refuse the same programs
at all.

### The rule

For every source text:

1. **Acceptance agrees.** `whence.parser.parse(src)` raises if and only if
   the guest's `parse_whence(src)` returns a miss — modulo an enumerated set
   of host-only checks (below), each of which must stay load-bearing.
2. **On rejection, the position agrees.** Both messages end in
   `at line L, col C`, and the two `(L, C)` are equal.
3. **Wording is still not a contract**, deliberately. A position is a fact
   about the program under analysis; a sentence is a choice about how to
   describe it. v0.22's five parse-error hints are host-only and this
   version does not change that.

Rule 2 required the guest lexer to have columns at all, which is where the
version's findings come from.

### The guest gets columns, and derives them

`lex` gains one parameter, `bol` — the index of the current line's first
character — and every token's column is `i - bol + 1`. Nothing is tracked;
the column is computed from the index the lexer already has. `lex_str_body`
gains `q`, the opening quote's index, and its failure record now carries
`at`: the absolute index the host's `LexError` reports, which is the QUOTE
for an unterminated string and the BACKSLASH for a bad escape.

```
fn lex(s, i, stack, acc, line, bol) {
  if i >= len(s) { push(acc, @{t: "eof", v: "", line: line, col: i - bol + 1}) }
  ...
```

### Finding 1 — the host's column stopped at every comment

`whence/lexer.py` INCREMENTS a `col` counter per character consumed. Its
comment branch advanced `i` to end of line and left `col` where the `#` was:

```python
if c == "#":
    while i < n and src[i] != "\n":
        i += 1        # col not touched
    continue
```

A comment runs to end of line, so the only tokens it can precede are the
NEWLINE that ends that line and, at end of file, EOF — which is exactly why
this survived 359 rounds. No test had ever asked for either one's column,
and until this version there was no second implementation to disagree with.

Measured before the fix: **10 of the 16 git-tracked `examples/*.lang` files**
held at least one token whose recorded column was wrong. It is user-visible:

```
let x = (1 # comment
                    ^ end of input is column 21
expected ), got None at line 1, col 12        <- v0.23: the `#`
expected ), got end of input at line 1, col 21 <- v0.24
```

`tests/test_v24.py` adds the oracle that would have caught it without any
guest: a token's `(line, col)` must point at the token's own first character
in the source. That is what a column *means*, and nothing in this repo had
ever said so. It runs over a hand corpus and all 16 tracked examples.

### Finding 2 — `col 0`

`stmt_list`'s no-rebinding error passed a literal `0`:

```python
raise ParseError("'%s' is already bound in this block (line %d); "
                 "Whence has no rebinding" % (name, bound[name]),
                 s.line, 0)          # every other column here is 1-based
```

An AST node carries a `line` and no `col`, so there was nothing to pass. The
fix is one line earlier: `start = self.peek()` before `self.statement()`, so
the error points at the token the statement begins with. An indented
rebinding now reports its own column instead of column 0.

### Finding 3 — `None` is not a token the author wrote

The EOF token's `value` is Python `None`, and two sites rendered the
offending token with `%r`:

```
unexpected None at line 1, col 10        (`let x = (`)
expected ), got None at line 1, col 11   (`let x = (1`)
```

`_show(tok)` returns `"end of input"` for EOF and `repr(tok.value)`
otherwise, so a string is still quoted and a number still is not. It is
deliberately NOT `_spell`, and the two must not be merged: `_spell` quotes a
token back at the author inside a v0.22 HINT, where a string literal keeps
its own double quotes because the hint is telling them how to write it;
`_show` names the token that stopped the parse. `_spell` has no EOF case
because a hint is never about end of input.

No test in 359 rounds asserted either message. That is the finding, not the
`None`.

### Finding 4 — the guest permitted a trailing comma in six constructs

Six list-like constructs in the shared guest parser wrote their
closing-bracket test as the after-a-separator test as well:

```
fn parse_args(toks, pos, acc) {
  if is_op(toks, pos, ")") { @{args: acc, pos: pos + 1} }    # also reached
  else { ... if is_op(toks, a.pos, ",") { parse_args(toks, a.pos + 1, acc) } }
}                                                            # after a comma
```

so `f(1,)`, `[1, 2,]`, `@{a: 1,}`, `fn f(a,) {}`, `shape P = @{a: num,}` and
`effects [io,]` all parsed on the guest and are all refused by the host. The
fix splits each into an entry function (which may see the closer) and a
`_rest` function (which requires an element) — the shape `whence/parser.py`
already has. Whence has no trailing-comma tolerance anywhere, and now says so
twice.

### Finding 5 — a miss in a record field is not a failure

```
let label = if k.t == "str" { k.v } else { miss "expected a string label..." }
@{kind: "check", label: label, expr: e.node}
```

`check 1: 1 == 1` produced a well-formed `check` node whose `label` happened
to be a miss, and `parse_whence` returned success for a program the host
refuses. A miss propagates through *operations*, not through *containers* —
which is correct language semantics and is a trap for a parser whose total-
error discipline is miss propagation. The fix makes the miss the result.

### Finding 6 — a lex error reported as a token

The guest's `bad` token fell through to `parse_primary`'s catch-all:

```
guest (v0.23): unexpected token 'unterminated string' at line 1
host:          unterminated string at line 1, col 9
```

— the lexer's own sentence wedged into the slot where a token's text goes.
`whence/lexer.py` raises before `parse` is ever called, so the host says
nothing about tokens. `parse_whence` now checks for a `bad` token first.
This is the one error class where host and guest wording is byte-identical,
because there is nothing to mirror except `LexError`'s own message.

### The host-only exemptions

Two host checks the guest parser does not have, each pinned in
`test_parse_error_differential.py::HOST_ONLY` with its reason and each
asserted still-firing in both directions (`skills/measured-exemption`):

| check | why the guest does not have it |
|---|---|
| `MAX_NESTING` | a host RESOURCE guard (`_enter` counts Python recursion so a deep expression is a ParseError and not a RecursionError), not a rule of the grammar. The guest runs on the trampoline. |
| effects (2 raise sites) | parse-time in the host, absent in the guest: `parse_effects_clause` SKIPS `effects [...]` without recording it (round 164). Implementing it needs six scope stacks the guest has no mutation to carry. |

### What this deliberately does NOT do

**It does not unify wording.** Rule 3 is asserted as a fact, not left as a
comment: `test_wording_is_still_not_a_guest_contract` requires at least ten
cases with equal positions and different sentences, so a future round cannot
make rule 3 vacuous without noticing.

**It does not remove the implementation coordinate from guest parse errors.**
All 43 of them still end in `(line N)` — a line in `self_eval.lang`, not in
the program being parsed — because `miss <string>` appends the line of the
`miss` EXPRESSION. That is right for an ordinary program and wrong for a
program that is itself a parser. Round 350 removed the guest LEXER's one
instance by returning an `@{err: ...}` record instead of a miss; the parser
cannot do the same, because miss PROPAGATION *is* its total-error discipline
— roughly forty functions rely on a miss flowing up through record
construction, and Whence has no `raise`. Fixing it is a LANGUAGE change with
two candidate designs, recorded in the round-360 knowledge file. The count is
pinned so it can only go down.

**It does not give AST nodes a column.** Only the two host sites that had a
token in hand and threw it away were changed; `Node` still carries `line`
alone, and widening it is a separate change with its own blast radius.

### Measured

```
languages/whence  pytest -m "not whence_slow"        1400 passed, 3 skipped
                                                     (356 baseline 1253)
                  tests/test_parse_error_differential 147 passed, 3 skipped
                  tests/test_v24.py                   49 passed
                  tests/test_lexer_guest_parity.py    82 passed
                  run.py examples/self_host.lang      133 passed (was 112)
                  run.py examples/self_eval.lang      142 passed, 0 failed
host/guest acceptance divergences        9 of 47 -> 2 (both pinned host-only)
host/guest position divergences          43 of 43 agree
tracked example files with a wrong token column   10/16 -> 0/16
host `raise ParseError` sites the corpus reaches  20/20
```

## v0.25 (round 362, language C) — a message names types; only a value slot renders a value
- **The question no round had asked.** `examples/self_eval.lang` does not
  only re-implement Whence's VALUES; it re-implements its MESSAGES.
  `check_contract`, `guest_mismatch_reason`, `guest_match_why` and
  `guest_spec_name` exist to reproduce the host's sentences word for word,
  and round 338's tests say so in their names. Nothing had ever checked
  more than three of them. The guest-differential oracle
  (`harness/swe/guest.py`) compares payloads and **exempts miss REASONS** —
  its oldest exemption, round 17, and correct for its purpose — so both
  sides missing was rated `ok` however differently they explained it. The
  only wording comparison in the tree was `test_self_eval.py`'s
  `SHAPE_MISS_CASES`: **three** hand-written cases against a host surface
  with **15** message sites.
- **What made this round look.** Round 361's slow-tier read-scope
  instrument found `harness/tests/test_swe_guest.py::
  test_no_shape_declaration_reaches_the_guest_generator` RED. Its stated
  reason — "the guest parser has no `shape` support at all" — had been
  false since round 338, in the files it was talking about. Round 347
  taught `ProgramGen` to emit `shape` declarations and inverted the
  fuzz-side twin of that pin; `GuestGen` inherits `program()` by design, so
  shapes reached the GUEST differential in the same commit, and the pin
  failed the day it was written. Fourteen rounds ran with it red because
  `harness/tests/test_swe_*.py` is the slow tier.
- **First measurement: 141 of 400 generated guest programs (35.2%) carry a
  `shape` declaration and 84 name one in an annotation; 141/141 parse on
  the host; the guest differential rates 138 `ok`, 1 mismatch (a `guess`
  divergence, unrelated to shapes) and 2 OOM-killed.** The values agree.
  That is what the oracle can see, and it is not the interesting half.
- **Decision 35 (new): a message has NAME slots and VALUE slots. A name
  slot holds a name — a string — or says the thing is anonymous. A value
  slot renders the offending value, and BOTH implementations must be able
  to render it.**
  - `_type_match`'s `__shape` is a name slot. `shape Name = …` always binds
    a Str, but a hand-built spec can carry any payload there, and round 335
    rendered a non-string through `show_payload` (to stop `%s` leaking a
    Python repr with a heap address, which had made one program produce a
    different message on every run and fired three oracles). That fixed the
    leak and left two problems. `typed(1, @{__shape: 5, a: "num"}, "L")`
    answered `expected 5, got num`, which reads as if `5` were a type. And
    it made the message depend on `show_payload`'s CAPS — a rendering
    policy no Whence expression can reach — so the guest said `expected
    record`. **An unnamed spec is anonymous and reads as `record`**, which
    is what the guest already said and what the no-`__shape` branch has
    always said. `_spec_ok` still ignores `__shape`, so a record that fits
    still fits: this is about the message, not about matching.
  - The value slots (`typed`'s spec and label, `sure`'s threshold, `get`'s
    key, `apply`'s non-callable) now go through ONE guest renderer,
    `show_val`, mirroring `show_payload`: a miss is a bare `miss`, a
    callable is `<fn>` / `<fn name>` / `<builtin name>`, a string is
    QUOTED. Two properties of the host renderer are deliberately NOT
    mirrored and are enumerated as load-bearing exemptions — its caps (40
    chars, 12 per nested element, 6 list items, 4 record fields, 3 levels)
    and `_quote`'s escaping.
- **Four guest defects, each invisible to every oracle for the same
  reason.**
  1. **A propagated miss lost its cause.** `typed`'s and `sure`'s guest
     branches answered `typed: a propagated miss` / `sure: a propagated
     miss` where the host's `_propagate` returns `merge_miss`, carrying the
     argument's own reasons (`num: cannot parse "x"`). A fresh sentence
     that destroys the cause, in a language whose decision 2 is that a miss
     can tell you *why*. Both now delegate propagation to the real host
     builtin on stripped arguments, so the merge cannot drift.
  2. **`typed` had one guard where the host has two, and no `_spec_ok`.**
     Round 335 recorded "mirroring the host's `_spec_ok` walk here would
     buy no observable agreement" — true of the ORACLE, and it cost more
     than a sentence: `typed(@{a: @{b: 1}}, @{a: 5}, "L")` fell through to
     `guest_match_why`, which walked the malformed spec and leaked the
     guest's own internal miss, **`keys needs a record, got 5`**, to the
     user. `guest_spec_ok` (round 344) already existed.
  3. **The guest's own closure record leaked into a message.** A shape name
     shadowed by a function made `check_contract` render the spec with
     `str`, dumping `@{__tag: "closure", body: …, env: […], param_specs:
     …}` where the host said `<fn>`. `show_callable` (round 156) has
     answered exactly this since round 156 and was never called from here:
     the "a guest closure is an ordinary record" hazard that
     `guest_spec_ok`/`guest_spec_match` already guard for MATCHING, left
     unguarded for SHOWING. The same `str` also left a string unquoted —
     `let f = "hi"\nf(1)` read `hi is not callable`, and the old
     `show_spec`'s own comment cited that site as its evidence that "every
     other payload agrees between the two".
  4. **`get`'s key guard was one branch where the host has two**: a MISSED
     key answered `get field name must be a string` (not true of a miss)
     instead of propagating, and a non-string key named neither the value
     nor v0.22's order hint — so the one message v0.22 exists to produce,
     *swap your arguments*, never reached a guest program through `get`.
- **Round 354's enumeration was wrong, and this is the general lesson.**
  `self_eval.lang` said "only the four builtins this evaluator
  re-implements need a [v0.22 order-hint] mirror". It re-implements
  **seven** with an `_order_hint`-bearing host message: `map`, `filter`,
  `fold`, `find`, and also `typed`, `sure`, `get`. The three missing ones
  are fixed here and `sig_names`/`sig_kinds` name them.
- **One finding measured and NOT fixed, with its repro in the corpus.**
  `push` is DELEGATED, and `apply_host_builtin` passes the pushed element
  as a guest BOX (a guest list holds boxes). The host then computes
  `_order_hint` over (payload, box-record), a record never fits
  `push(xs:list, x)`, and the hint silently disappears: `push(1, [2])`
  says `push needs a list, got 1` on the guest and `… (arguments fit
  push(xs, x))` on the host. **Delegation is not automatically parity** —
  it is parity only where the host's message does not depend on the SHAPE
  of an argument the guest boxed. Fixing it means the guest stops
  delegating `push`'s guard and builds the message on the hot path of its
  own interpretation loop; that is a design call, handed forward with
  `exempt-push-order-hint` as the repro.
- **The instrument: `tests/test_contract_message_differential.py`.** Round
  360's refusal-set method one level down, from PARSE errors to CONTRACT
  errors — with the opposite verdict on wording, because here the two
  implementations were built to agree. Three rules: missed-ness agrees;
  the wording agrees except for the enumerated `EXEMPT` set, each entry
  asserted load-bearing in BOTH directions; and the corpus reaches every
  host message SITE, derived from `whence/interp.py`'s AST and captured by
  wrapping `mk_miss`/`merge_miss` and walking the stack — because one
  generic site can absorb a dozen cases and look like coverage. One site is
  declared UNREACHABLE with its reason (`_check_contract`'s `_UnboundType`
  branch: v0.18 made `parse_type` scope-aware, so no source text reaches
  it), and a separate test fails if that branch is ever deleted out from
  under the exclusion.

### Measured

```
host/guest WORDING divergences, 1152-case typed/matches matrix   204 -> 0
host/guest WORDING divergences, 436-case annotation matrix        52 -> 0
host/guest divergences, 30-case order-hint builtin sweep     10 -> 1 (push,
                                                          enumerated above)
guest differential over the 141 shape-carrying programs   138 ok, 1 mismatch
                                             (guess, unrelated), 2 OOM-killed
languages/whence  tests/test_contract_message_differential  10 passed
                  run.py examples/self_eval.lang            142 passed, 0 failed
host contract-message sites the corpus reaches            14/15 (1 declared
                                                              unreachable)
```

## v0.26 (round 366, language C) — a runaway tail loop is a miss, not a hang

Two lines of this spec contradicted each other for thirty rounds, and rule 8
held both:

> **(a)** Tail position changes space, never meaning (round 336). Lifting any
> tail call out of tail position with a `let` must not change the value, the
> miss, which `-> Type` contract is blamed, or the line the miss reports —
> only the frame count.
>
> **(b)** Tail loops are unbounded by default.

Take any function whose recursion does not terminate:

```
fn tl3(p4) { if p4 == 0 { 0.5 } else { tl3(p4 - 1) } }
let v7 = tl3(0.5)
```

`0.5` decrements past a `== 0` base case it can never equal. Out of tail
position — the same function with `let r = tl3(p4 - 1)` and `r` — that is a
`recursion too deep in tl3 (depth 50)` miss in 0.07 s. In tail position, (b)
said it ran forever. "No value, ever" versus "a miss" is the largest
difference in meaning two forms of one function can have, so (a) was false
for every non-terminating program, and had been since v0.3 introduced tail
merging.

**`max_depth` cannot cover this, and that is not a bug.** A tail call spends
no frame — that is what rule 8 is *for*. The bound a tail loop needs is a
bound on ITERATIONS, and `max_iter` was exactly that bound, already
implemented, already tested (`test_v03.py::
test_max_iter_turns_an_infinite_tail_loop_into_a_miss` has passed since
v0.3), and defaulted to `None`. Nothing was missing but a number.

Why no test caught it: `test_v13.py::
test_tail_and_lifted_chains_agree_exhaustively` drives the whole
`f0 -> f1 -> …` family through both forms and requires byte equality, and
every chain it builds terminates. A non-terminating one would have hung the
suite rather than failed it, so the differential could not be written until
the bound existed. It is `tests/test_v26.py` now.

### Sizing the default — the first answer was measured, principled and wrong

The tempting rule is memory parity: give a tail runaway the same ceiling a
depth runaway gets. `bench/runaway_cost.py` (new here; one run per process,
because `ru_maxrss` is a process-wide high-water mark that reports the
previous run's peak if you reuse one) measures both sides:

| shape | retained |
|---|---|
| non-tail `1 + spin(n+1)` / `let` / `let` inside `if` | 1337 / 1560 / 2084 B per frame |
| tail `spin(n+1)` / seed 31 / `if`-spin / two-arg `if` | 258 / 419 / 499 / 768 B per iteration |

That also retires the `DEFAULT_MAX_DEPTH` comment's "~6 KB" per frame, which
had stood since v0.2 and which no round ever re-executed: at the worst of the
three shapes, 20000 frames is ~40 MB, not the ~125 MB the comment claimed.
Parity then gives 20000 × 2084 / 768 = 54270, i.e. 50000 — and 50000 breaks
four of this repo's own examples, because a tail loop is the only loop Whence
has and real programs run long ones.

The corpus is the authority. Uncapped `interp.peak_tail` over
`examples/*.lang` is 200001 (`deep.lang`), 100002 (`tco.lang`), 60005
(`meta.lang`), 50001 (`shapes.lang`), then a 150× gap to 331. The 200000 is
deliberate: `deep.lang` asserts it as a language property —
`check "a tail loop runs 10x past max_depth"` — so 10 × `DEFAULT_MAX_DEPTH`
is a pinned contract the default must clear. Applying
`skills/measured-budget-sizing`'s margin of 3 gives 600003, so **1000000** is
the round number above it. Measured cost of that ceiling: a runaway is a miss
after 9.3 s / 748 MB at the worst shape, 3.7 s / 412 MB at seed 31's. Both
finite; the previous default was unbounded in both, and round 362 measured 2
of 141 guest seeds OOM-killed.

`test_v26.py::test_every_example_stays_under_the_default_with_margin`
re-derives that maximum from the tracked examples on every run, so the
constant cannot silently drift away from the corpus that justifies it.

### `peak_tail`

`interp.peak_tail` is the tail analogue of `peak_depth`: the most frames any
SINGLE tail loop merged. `tail_calls` is a run-wide total and cannot answer
"how close did this program come to the cap" — two loops of 300 give
`tail_calls == 600` and `peak_tail == 301`. Sizing the default needed the
per-loop maximum and nothing reported it. Updated once per call in the
`finally` that already unwinds the frame, not per iteration.

### Found from the fuzz side first

Round 365 minimised guest seed 31 to `state/swe/round-365/seed31_hang.lang`
and left three suspects: field access on a number (`10.x`), a `-> num`
contract, and `reasons()` over a Miss chain. All three were wrong — a
13-statement prefix bisect puts it on line 7, `tl3(tr5)` where `tr5` is
`0.5`. Nothing about the program is exotic; any non-terminating tail
recursion did this. Round 365's other observation, that hand variants
recursing on a RECORD argument terminate at every `max_depth` 50–800, is
correct and was the misleading part: a record argument makes `p4 - 1` a
miss, so `p4 == 0` is a miss, so the `if` takes neither branch and the loop
stops after two calls. It takes an argument that keeps *working* — a float —
to recurse forever.

Re-running round 365's 400-seed shape sweep under the new default turns both
of its `timeout` seeds (31 and 224, the latter mutual recursion:
`odd(-100) → even(-101) → …`) into `ok` — comparable differential data
instead of discarded hangs.

## v0.27 (round 368, language C) — a value has a size, and a size nothing bounds is a hang

v0.26 closed the last entry in "Limits that are errors, not crashes" that was
neither: a runaway tail loop. It closed it along the axis the section already
understood — **how many times** a program goes round. This version is about
the axis that section never had. `max_depth` bounds how DEEP a program goes,
`max_iter` bounds how MANY TIMES it goes round, and **nothing bounded how BIG
one value gets.**

Five host exceptions were reachable from ordinary source, and none of them
needed a big machine or a long run:

```
fn sq(n, x) { if n <= 0 { x } else { sq(n - 1, x * x) } }
let big = sq(15, 3)          # 3**32768 — 51937 bits, 2 KB, 0.04 s
```

| what you write | what happened |
| --- | --- |
| `print(big)` | `ValueError` traceback, exit 1 |
| `big + "x"` | `ValueError` — building the MISS MESSAGE |
| `check "c": big < 10` | `ValueError` — reporting the FAILED CHECK |
| `range(big, big + 2)` | `ValueError` — a **two**-element range |
| `[1,2,3][big]` | `ValueError` — the index-out-of-range message |
| `num(dbl(13, "1234"))` | `ValueError` — `int(t)` on 32768 digits |

The cause is one CPython rule: `int.__str__` raises past
`sys.get_int_max_str_digits()` (4300 by default since 3.11), and Whence's
integers are unbounded on purpose (see "v0.4.1" above, which made *overflow*
a miss and never considered *size*). The consequence is the sharp part. In a
language whose rule 2 is "no exceptions, no null — every runtime error yields
a `miss`", and whose one idea is that a failure can explain itself, **the
explanation is what crashed.** `show_payload` is called by `print`, by every
`mk_miss` that names its operands, by a failing `check`'s report and by
`why`; a value that could not be rendered poisoned the entire diagnostic
surface, and the miss about the bad value could not be constructed.

Every one of those exited **1**, which is the "some check failed" code — so a
caller could not tell a program whose checks failed from a program that
killed the interpreter. That is the third recorded instance of this class,
after `run.py`'s uncaught `LexError` (v0.21, round 350) and the two above it.

And three shapes that were hangs rather than crashes:

```
fn go(n, s) { if n <= 0 { s } else { go(n - 1, s + s) } }   # MemoryError at ~40
fn go(n, x) { if n <= 0 { x } else { go(n - 1, x * x) } }   # no return in 60 s
let r = range(100000000000)                                 # OOM killer
```

### Integers were the only payload kind `_show` rendered in full

Strings are cut by `_quote`'s `limit`. Lists are cut by `SHOW_NEST` and
`head(6)`. Records by `SHOW_NEST` and `items[:4]`. Integers went to `repr()`.
`values.show_int` now renders `<integer, N bits>` past **`SHOW_INT_BITS =
13287`**, which is at most 4000 decimal digits (13287 × log10 2 = 3999.8) and
therefore strictly under the host's 4300 — so the host limit is never the
thing a user meets, and the cap is Whence's own. Bits and not digits, because
`bit_length()` is O(1) and bits is the unit the integer budget charges in.

`num()` refuses numeric TEXT past the same boundary
(`SHOW_INT_DIGITS = 4000`), so **`num` and `str` stay inverses**: Whence never
accepts digits it could not print back. That limit is tighter than
`max_int_bits` and deliberately so — it is about the round trip, not about
cost.

### The six growth sites

A growth site is a place where a value can come out BIGGER than the sum of
its inputs' sizes. There are exactly six, and no other builtin or operator in
the 36-name table can do it:

| site | grows by | charged in |
| --- | --- | --- |
| `+` on two strings | doubling (`s + s`) | characters → bytes |
| `+` on two lists | doubling (`xs + xs`) | elements → bytes |
| `push(xs, x)` | one element | elements → bytes |
| `range(lo, hi)` | **a number** | elements → bytes |
| `join(xs, sep)` | list length × part length | characters → bytes |
| `*` on two integers | doubling (`x * x`) | bits |
| `+` / `-` on two integers | one bit | bits |

`range` is the outlier that makes the whole class visible: it is the only
builtin whose output size comes from a NUMBER rather than from the size of a
value argument, so a five-character call can ask for 100 GB. `join` is the
subtle one: a list of 20 shared pointers to one 1280-character string weighs
160 bytes, and joining it materialises 25600 — only the sum of the parts can
see that.

**Why `max_iter` could not simply be re-tuned.** Every site above except
`push` and `+`/`-` is MULTIPLICATIVE, so a doubling loop crosses any budget
in log2(budget) steps — 29 for the shipped default, never more than 60 for
any figure this machine can hold. A ceiling of 1 000 000 iterations cannot
see a loop that kills the host on iteration 40. And `range` crosses it in
ONE. The corpus says the same thing empirically: `deep.lang` merges 200001
tail iterations and peaks at a **20-byte** value, while `self_eval.lang`
peaks at **15700 bytes** with a longest loop of 143. Neither budget predicts
the other.

### Two budgets, and why not one

`Interpreter(max_value=…, max_int_bits=…)`, CLI `--max-value N` /
`--max-int-bits N`, `0` meaning unbounded on both — the shape v0.26 settled
on for `--max-iter`.

**`max_value = 500000000`** (bytes). The corpus does not set this one: any
figure above ~0.5 MB clears every example, so `corpus_max × 3` would be
arbitrary. What binds is **coherence with `max_iter`**. Whence has no
`while`; the two ways to say "do this a million times" are a tail loop
(allowed — `DEFAULT_MAX_ITER` is exactly 1000000) and `map(f,
range(1000000))`. Refusing one spelling and permitting the other would be
incoherent, and that floor is `1000000 × 157 B/elem = 157000000`.
`skills/measured-budget-sizing`'s margin of 3 gives 471000000; 500000000 is
the legible figure above it — 3.18× the floor, 31847× the examples corpus,
1062× the largest `range` anywhere in this repo (`range(3000)`).

**`max_int_bits = 8000000`** (bits = 1 MB). The first draft charged integers
into `max_value` at their memory cost, 8 bits to the byte, so that one budget
covered every kind. That is principled, it is measured, and it is wrong for
exactly the reason round 366's memory-parity `max_iter` was wrong: **the cost
model is not the same across kinds.** String concatenation is linear — a
500 MB `s + s` runaway is refused in 0.55 s. CPython's bigint multiply is
Karatsuba, ~n^1.58 (`bench/value_size.py --ints`):

```
 3.3 M bits  0.49 s      13.3 M bits   3.97 s
 6.6 M bits  1.39 s      26.6 M bits  12.77 s
```

At `max_value`'s 500 MB an integer may reach 4×10^9 bits, and the last
permitted multiply there extrapolates to **hours** — the hang this section
exists to remove. So the two numbers cannot be one: the byte budget needs a
floor of 157 MB and the integer budget needs a ceiling near 1 MB. Sized from
TIME: a doubling runaway is refused having spent ~2.2 s, the same order as
the 0.55 s string case and inside round 366's 9.3 s worst case for a
`max_iter` runaway.

The per-unit byte costs are MEASURED, not guessed, and
`bench/value_size.py --bytes` re-measures them: a `str` is 1.000 B/char, a
list element copied by `+`/`push` is 8.00 B (a shared pointer — the element
`Prov` already exists), and a `range` element is **157.01 B** because `range`
allocates a fresh `Prov` leaf *and* a decimal detail string per element,
~20× a shared pointer. That is why `range` gets its own constant rather than
one blended figure.

`interp.peak_value` and `interp.peak_int_bits` are `peak_tail` for size: the
largest value the run ASKED for at a growth site, recorded whether or not it
was refused, because the refused number is the one a future round needs to
re-size a default.

### One check on the numeric hot path, and it is a constant

`f_mul` (and now `f_add` / `f_sub`) test operand magnitude against the module
constant `_MUL_FAST_CUT = 1 << 64`: two operands strictly inside ±2^64 make a
product under 2^128, so the inline multiply stays inline for every realistic
program, and CPython compares integer digit COUNTS first, so the test is O(1)
even against the threshold. Anything bigger goes to `binop`, which does the
exact `bit_length` check and owns the wording — `_compile_binop`'s own
docstring rule, that the closure never decides a miss, kept intact.

It must be a constant. Two drafts proved it: derived from `max_value`, the
threshold is `1 << 2000000000` — a 250 MB integer built by every
`Interpreter()` constructor; read from the live interpreter, it costs an
`Env` walk per numeric operation. The price is `MIN_MAX_INT_BITS = 128`, the
floor `max_int_bits` is clamped to, without which `fast=True` and
`fast=False` would disagree below 128 bits.

**`_compile_binop` also stopped capturing `binop`.** It had captured the
compiling interpreter's bound method since v0.10, which was harmless while
`binop` was effectively pure. v0.27 gave `binop` state — two budgets and two
peak counters — so a captured method would charge one interpreter's
`peak_value` for another's run and decide its misses against the wrong
budget. It now resolves the live interpreter from the `Env` chain
(`_live_interp`), the same v0.7 shared-AST determinism rule `d_call` and
`_compile_builtin_call` already followed.

### The oracle: no host exception, from any value the language allows

`tests/test_v27.py` section 1 drives one 51937-bit integer through **every
builtin in the live registry, at every arity in its range, in every argument
position**, through every binary operator against seven other operand kinds
on both sides, and through indexing / field access / `why` / `snip` / `note`
/ `rescue` / a failing `check` — then forces `full_show`, `show_payload` and
`report_checks` over each result. It asserts nothing about meaning: only that
no host exception escapes. That is deliberate. Each of the five crashes was
raised while BUILDING A MESSAGE, so any test that checked wording would first
have had to know which call sites to look at, and the whole problem was that
nobody did.

It earned itself on its first run by finding a sixth site **in v0.27's own
new code**: `_size_miss` formatted the element count with `%d`, and
`range(1, big)` asks for a number of elements that is itself a 51937-bit
integer — so the miss about a too-large range crashed while saying so. A
seventh turned up writing the tests: `@pytest.mark.parametrize` builds test
ids with `str(val)`, so parametrising on a 13286-bit integer makes **pytest**
raise the same ValueError during collection.

### What is NOT covered

- **Records.** `put`/`merge` add one field per call, bounded by `max_iter`,
  and a record's fields are shared pointers. Not a growth site; not guarded.
- **`str()` of a large list.** `full_show` renders every element, so a list
  at the budget renders a string larger than the budget. Bounded (the list is
  bounded) but not itself charged.
- **Time, in general.** These budgets bound SIZE. A program can still spend a
  long time inside `max_iter` iterations of a cheap operation; that is what
  `max_iter` is for, and it is a coarser instrument than this one.

## v0.28 (round 372, language C) — a message names the kind that stopped it, and both implementations say it

**Decision 36.** A miss carries reason strings, and a reason string is a
CONTRACT — the same one v0.25 (round 362) settled for contract messages,
now stated over the whole miss surface. Two halves:

1. **A message names the kind that actually stopped the computation**, not
   a kind that plausibly might have.
2. **`examples/self_eval.lang` produces the same sentence**, except where an
   enumerated exemption says it cannot, and each exemption must still
   DIVERGE or be deleted.

### Why nobody had checked it

Round 362 asked question 2 for CONTRACT messages. Its `TYPE_FNS` tuple names
five host functions and its coverage assertion is `len(declared) >= 12`. An
AST census of the same file finds **126** `mk_miss`/`merge_miss`/`_propagate`
sites in **46** enclosing functions. The arithmetic, the operators, the call
path, the two size budgets and 30 of the 36 builtins were outside it — and
outside everything else too, because the guest-differential oracle's oldest
exemption (miss REASONS, round 17) means every campaign that ever ran rated
these `ok`: both sides missed, and the oracle does not read what they said.

### The corpus is keyed by SITE, and that is not enough

`tests/test_miss_message_differential.py` builds one case per site by
instrumenting `mk_miss`/`merge_miss` and greedily set-covering the census
across all three engines: **124 of 126 sites reachable**, 114 cases. Two
sites are genuinely unreachable and both are named with a reason —
`_check_contract`'s `_UnboundType` branch (round 362's entry, unchanged) and
`f_bcall`'s `fnv is None` branch, which is DEAD CODE and whose own source
comment says so (`# unreachable while builtins are global`; `f_bcall` is
only compiled for a name that resolved to a builtin, and Whence cannot
unbind a name).

Site coverage bounds the HOST side and only SAMPLES the guest side. One host
site can be reached by operands the guest words differently from each other:
the cover kept one case for `binop`'s `==` guard, on which the guest agreed,
while `len == len` — same site — disagreed (`cannot compare functions` vs
`cannot compare functions with ==`). The `EXTRA` list in that file exists for
exactly that reason and the finding is recorded here rather than in a
comment, because it is a property of site-keyed differentials in general.

### Host vs host: three engines, four copies of every call guard

Whence has three engines (`direct` / `direct=False` / `fast=False`) and the
call guards are QUADRUPLICATED: `_builtin_inline`, `_closure_inline`,
`_call_direct` and `_call_gen` each carry their own `%s expects %s args, got
%d`, `recursion too deep in %s (depth %d)`, `tail loop too long in %s (%d
iterations)` and `%s is not callable`. Nothing compared the sentences those
copies produce.

**They agree** — over the corpus and over a 23 997-case mechanical sweep
(every builtin at every arity against 16 argument atoms, every binary and
unary operator, indexing, field access, calls, `if`, plus hand-written
closure-arity / depth / tail-loop / unbound-name / rebind cases). Zero
divergences in wording, reason count or missedness.

This is a PIN on a negative result, and it is deliberately less novel than
it looks: `oracles.oracle_fast_slow` and `oracle_direct` already covered it
incidentally, because `behaviour_ex`'s `vals` field renders a Miss through
`full_show` and that includes its reasons. What v0.28 adds is that the
coverage is now site-keyed and deliberate instead of program-keyed and
accidental. Reaching two of the four depth-guard copies needs a NON-DEFAULT
`max_depth` (the default 20000 is far past the direct engine's host-frame
budget, so `_call_gen`'s copy answers first); those two cases are `HOST_ONLY`
in the test file.

### The host defect: `==` named a kind that was not there

`deep_eq` returns `None` for four opaque payload kinds — `Closure`,
`Builtin`, `Explanation`, `Miss` — and `binop` turned that into one sentence:

```
why 1 == 1              # miss: cannot compare functions with ==
[1 / 0] == [1 / 0]      # miss: cannot compare functions with ==
```

Neither program contains a function. A top-level miss never reaches here
(`binop` merges it first), so the second case is specifically a miss NESTED
where a top-level one would have propagated. `_incomparable_kind(l, r)` now
finds the first opaque payload — **left operand depth-first (list elements in
order, record fields by sorted name), then right**, a fixed order chosen so
the guest can mirror it rather than `deep_eq`'s own stack order — and the
message names it: `cannot compare explanations with ==`, `cannot compare
misses with ==`, `cannot compare functions with ==`. It falls back to the
pre-v0.28 wording if no opaque payload is found, so a fifth opaque kind
cannot make it raise.

This is decision 34's principle (a message names types) applied one level
out from the type system: it is not enough for the named type to be a type,
it has to be the one that stopped the program.

### The guest defect: a compound guest value is made of BOXES

A guest list holds `@{op, v, ins}` boxes, not elements. `apply_host_builtin`
hands the host builtin the guest's payload, which for a scalar is what the
host would have seen and for a list or record is not. On the SUCCESS path
that is load-bearing and correct — the boxes carry guest provenance. On the
MISS path the host words the message around what it was given:

```
num(@{a: 1})       host  num of @{a: 1}
                   guest num of @{a: @{ins: [], o…}
```

**The fix costs nothing on the success path.** Delegate exactly as before;
only if the answer is a MISS, delegate a SECOND time with deep-stripped
arguments, and keep that miss's wording. Three guards make it safe:
`print`/`rand` are excluded (a second call repeats the EFFECT), the
re-rendered result is used only when it is also a miss (so a strip that
changes the ANSWER cannot change what the evaluator returns), and the three
slots that hand the host a box ON PURPOSE (`push`'s element, `put`'s value)
switch to the bare payload only on the re-render.

The same shape fixes the guest's own operators — `apply_binop` (factored
through `raw_binop` so the dispatch can run twice), `eval_and`/`eval_or`'s
non-bool left operand, `eval_unary`'s `-`/`not`/`miss`, and `eval_index` —
all of which delegate their wording to a real host operation.

**Round 362's exemption E3 is retired.** It read: "a design call handed to a
future language(C) round with this case as the repro", and predicted the fix
would mean the guest "stops delegating `push`'s guard and builds the message
itself, on the hot path of its own interpretation loop". That prediction was
wrong in a useful way — the hot path is untouched, and the fix closes the
whole class rather than `push`. Its own
`test_each_exemption_is_load_bearing` went red the moment the divergence
stopped existing, which is exactly what round 362 wrote it to do.

E3's mirror image was in the same class and nobody had seen it: the box
SUPPRESSED an order hint for `push(1, [2])`, and it INVENTED one for
`put("", [], 1)` — a box is a record, a record fits `put`'s untyped `r`
slot, so a permutation "fits" that does not. A false hint is worse than a
missing one.

### Four more guest fixes

- **Closure arity.** The guest said `fn expects 1 args, got 2` for every
  closure. The host says `g expects 1 args, got 2` / `<fn> expects 1 args,
  got 2` — the `p.name or "<fn>"` substitution the guest ALREADY computed,
  as `op_name`, for the node label and then did not use in the message.
- **Builtin arity.** The guest said `len arity mismatch: got 2 args`, a
  sentence the host never produces anywhere. It now mirrors `_arity_str`.
- **`merge` of a function.** The guest said `merge of a function`; the host
  says `merge needs two records` whichever operand is the function. `merge`
  is the ONE of the five callable-piercing guards whose host message renders
  nothing, which is why it is a fix and the other four are exemption E2.
- **`strip` is not idempotent** and the re-render is what proved it:
  `strip(b)` is `strip_raw(b.v)` and `strip_raw` maps `strip` over a list, so
  a list of already-bare payloads makes it read `.v` on a number. It
  regressed `join([1, 1 / 0], ",")` from the host's `join: element 1 is not
  a string` to a guest-only `cannot access .v on 1`.

### The three exemptions, each asserted load-bearing

- **E1 — `why` is REIFIED in the guest.** The host's `why x` is an opaque
  `Explanation`; the guest's is a record, because guest code must be able to
  READ a history (SPEC's own "history is data"). Every message that renders a
  `why` value therefore differs, and `@{} == why 1` is a miss on the host and
  a plain `false` on the guest — the corpus's ONE missedness divergence, and
  a consequence of the design rather than of a bug.
- **E2 — a callable cannot be rebuilt.** The host renders `<fn>`, `<fn
  NAME>` or `<builtin NAME>`; a guest function is a tagged record. v0.28
  tried to close this the way it closed the box-leak class — substitute, on
  the miss path only, a host value that renders the same — and **it cannot
  be done**: `<fn NAME>` needs a host closure constructed with a chosen name
  at run time, and Whence has no expression that does that (`fn NAME(..)` is
  a statement with a literal name). Closing it needs a LANGUAGE change (a way
  to name a value) or a decision that `show_payload` stops printing a
  closure's name. Half a fix — mapping the guest's builtins through a
  name-to-value table and leaving closures broken — would have been worse
  than a named exemption.
- **E3 — the budgets differ in KIND.** `recursion too deep in g (depth
  20000)` vs `guest recursion too deep in g (guest depth 400)`. Round 371
  established this is not a difference of degree: the host charges a tail
  call NOTHING (rule 8) and the guest's `apply_closure` charges one guest
  frame per CALL. The guest's wording says "guest" on purpose, so it cannot
  be mistaken for agreement.

### Numbers

| | before | after |
|---|---|---|
| corpus cases agreeing | 86 / 114 | 103 / 114 |
| divergence classes | 7 | 3 (all named, all exempt) |
| host sites with wording ever compared | 15 of 126 | 124 of 126 |

## v0.29 (round 374, language C) — a rendering is part of the language, and a differential is keyed by the operand

**Decision 37.** Two halves of one finding, and the second is the reason
the first was invisible.

### The question this round asked

v0.28 (round 372) reported that the host and `examples/self_eval.lang` word
**103 of 114** miss cases identically, with the remaining 11 covered by
three named exemptions. Its corpus is keyed by HOST SITE — one case per
reachable `mk_miss`/`merge_miss` site, chosen by greedy set cover — and its
own module docstring records what that does not measure:

> Site coverage bounds the HOST side and only SAMPLES the guest side. One
> host site can be reached by operands the guest words differently from
> each other.

Round 372 patched that hole by hand, with a 10-case `EXTRA` list found by
noticing. This round replaced noticing with a cross product.

### The sweep

`tests/test_v29.py` builds an ATLAS of **26** source expressions, one per
renderable payload SHAPE — not per type: `[1, 2]`, `[len]` and `[1 / 0]`
are all `list` to `_kind` and are three different things to `show_payload`,
to `deep_eq` and to the guest's boxing. The atlas is crossed against every
binary operator, every unary operator, indexing, field access, three call
arities, `if`, `rescue`, and every argument slot of every builtin, one slot
at a time: **11 326 cases** (11 354 once `show` itself joined the table).

It is affordable because the guest side is one interpreter run per 500-case
batch — round 362's trick — at ~21 ms/case, ~240 s for the sweep against
~3 s for the host side.

### What it found: a fix inherits the shape of the coverage that verified it

**54 wording divergences no exemption covered**, so v0.28's "every
remaining divergence is one of three named, load-bearing exemptions" was
true of its 124-case corpus and false of the language. All 54 have the same
cause, and it is not a slip — it is what site-keying does to a FIX:

| site | what v0.28 did | what a second operand shows |
|---|---|---|
| `eval_and` / `eval_or` | re-render the LEFT operand | `true and [1, 2]` fails on the RIGHT and leaks boxes |
| `eval_index` | gate the re-render on `is_compound(INDEX)` | `@{a: 1}[1]` words the miss around the OBJECT |
| `eval_field` | untouched | the cover's case was `(true).a`, a scalar |
| `eval_if` | untouched | same reason |
| `apply_builtin` | gate on `any_compound(args)` | `put(1, "b", 2)`: every arg scalar, and `put`'s `v` slot is a box ANYWAY |

The last row is the sharpest. v0.28's cost gate exists because re-rendering
unconditionally took the guest's fast tier from 40 s to 87 s. It asks "is
some operand compound?", which is one way a box reaches the host and not
the only one: `push`'s element and `put`'s value are handed over boxed
whatever the operands are. So `put(1, "b", 2)` reached `_order_hint` with a
record in the `v` slot and INVENTED `(arguments fit put(r, name, v))` — a
hint naming the order the call was already in. v0.28 found this exact shape
for `put("", [], 1)` and fixed it *through* the compound gate, which that
case happened to pass. **A cost gate that also narrows a correctness fix
has to enumerate every way the leak can happen, not one of them.**

### The language change: `show`

The other class the sweep found is not a box leak. Where the guest
DELEGATES an operation it can re-render from stripped arguments; where it
RE-IMPLEMENTS one it must render the value itself, and it had two
hand-rolled copies of `show_payload` to do it with:

* `show_callable`'s fallback was `str(v)`, i.e. `full_show` — so
  `filter(fn(a) { true }, "ab")` read `filter needs a list, got ab`
  against the host's `... got "ab"`.
* `show_val` quoted a string by concatenation, with **no escaping and no
  truncation**, and fell back to `str` for everything else.

Neither could be fixed by trying harder. `show_payload`'s caps — 40 chars,
12 per nested element, 6 list items, 4 record fields, 3 levels — and
`_quote`'s escapes are host constants that **no Whence expression could
reach**. Round 362 had already met this and written it down as two
permanent exemptions in those words.

So v0.29 adds the 37th builtin:

```
show(v)     # the SNAPSHOT rendering: one line, bounded
str(v)      # the FULL rendering: no cap, a miss lists its reasons,
            # a `why` renders its tree, a string is itself
```

`show` is `show_payload` and nothing else. The argument for it is not "the
guest needs it": **a language whose one idea is that a failure can explain
itself should not keep the renderer its explanations are made of out of
reach of the programs it explains.** `str` and `show` are now the two
documented renderings, and the difference between them (bounded vs full) is
the same distinction v0.27's size discipline already draws elsewhere.

Adding it retired round 362's two rendering exemptions immediately —
`test_contract_message_differential.py`'s `EXEMPT` is now EMPTY, and both
cases moved to the required-agreement list. That file's
`test_each_exemption_is_load_bearing` is what forced the edit, going red
the moment the divergences stopped existing, which is the third time that
assertion has done its job (v0.28 retired E3 the same way).

### The fourth exemption, and it is the largest one in the language

Sweeping `at`/`steps`/`blame` over the atlas exposed something no
message-wording test could have: **the guest answers the provenance-query
family from the wrong history.**

```
let x = 1 + 2
len(steps(x))     # host: 4     guest: 284
blame(1 / 0)      # host: one step, `division by zero`
                  # guest: that step, plus `cannot add 1 and []`,
                  #        plus `cannot access .__tag on 1`, ...
```

Those extra steps are `self_eval.lang`'s OWN execution — its line numbers,
its local names (`a0`, `p0`), its internal probe misses. `apply_host_builtin`
calls the host `steps` on the guest's PAYLOAD, and that payload's host
provenance is the evaluator's, not the program's. Round 218 introduced the
delegation with the comment "`a0`'s real host provenance is already there
for free"; the provenance that is there belongs to the wrong program.

The evaluator is not missing the data. It BUILDS a correct guest history —
the `@{v, op, ins}` box graph that `why`/`reify` walk, and that
`tests/test_self_eval.py`'s guest-level provenance tests already compare
against the host DAG label by label. The query builtins simply do not read
it.

**Why it is an exemption here rather than a fix.** A host step record is
`@{op, detail, line, show, depth, inputs, count, value}` and a guest box is
`@{v, op, ins}` — no line, no op/detail split, no count. Making the family
correct means widening `mkb` and every one of its several hundred call
sites, and `walk_steps` additionally dedups shared nodes BY IDENTITY, which
Whence has no operator for (`==` is structural, so two distinct nodes that
happen to be equal cannot be told apart). That is a whole round's work and
a design decision — most likely "the guest's `steps` may over-report a
SHARED node, and says so" — not a patch. Recorded as E4, with
`tests/test_v29.py::test_the_provenance_family_is_still_exempt_and_still_wrong`
pinning it as an inequality rather than prose so it cannot quietly rot.

### The two exemptions that were bigger than they read

Keying the classifier on the CASE rather than on the host's wording also
corrected the size of E1 and E2. Both have a MISSEDNESS half v0.28 did not
state, because its corpus had one case each:

* **E1.** A guest `why` is a record, so every operation that accepts a
  record accepts one: `keys(why 1)`, `has(why 1, "a")`,
  `merge(why 1, @{})` and `@{} == why 1` all miss on the host and SUCCEED
  in the guest. 108 such cases, not one.
* **E2.** A guest callable is a record, so it is not opaque to `deep_eq`:
  `len == guess(1, 0.5, "s")` misses on the host and returns a value in
  the guest. And `_incomparable_kind` searches left-operand-first for the
  first opaque payload, so `[len] == [1 / 0]` finds the FUNCTION on the
  host and the MISS in the guest — the two name different kinds and each
  is right about its own value space. That ORDER divergence is a
  consequence of v0.28's own fixed search order, not a defect in it.

### Numbers

| | v0.28 tree | v0.29 |
|---|---|---|
| cases | 11 326 | 11 326 |
| agreeing | 6 789 | **6 857** |
| divergences with NO exemption | **54** | **0** |
| E1 (`why` is reified) | 1 796 | 1 796 |
| E2 (a callable is a record) | 2 684 | 2 670 |
| E4 (provenance family) | 3 | 3 |
| exempt share of the surface | 39.6% | **39.5%** |

The last row is the other half of the finding. The site-keyed corpus
reported **11 exempt cases in 114 (9.6%)**; the operand sweep finds **4 469
in 11 326 (39.5%)**. Nothing about the language changed between those two
numbers. E1 and E2 are not edge cases, and a corpus that visits each site
once is guaranteed to under-report any divergence that lives in the
operands rather than in the code.

### A methodological rule, stated so it can be reused

**A coverage criterion drawn from the implementation's structure produces a
fix with the same structure.** Site coverage is a good criterion for "is
every branch exercised" and a bad one for "does every branch AGREE", because
agreement is a property of the (site x operand) pair. Whenever a
differential's cover is keyed by one side's code, expect its fixes to be
keyed the same way, and cross-product the other side before publishing a
rate.

## v0.30 (round 378, language C) — a query about a history is answered from that history, and where it cannot be, it says so

**Decision 38.** v0.29 closed its own § with a new exemption and called it
"the largest one in the language":

> Sweeping `at`/`steps`/`blame` over the atlas exposed something no
> message-wording test could have: **the guest answers the provenance-query
> family from the wrong history.**

```
let x = 1 + 2
len(steps(x))     # host: 4     guest: 284
```

Those 280 extra steps are `examples/self_eval.lang`'s OWN execution — its
line numbers, its locals `a0`/`p0`, its internal probe misses. Round 218
introduced the delegation with the comment "`a0`'s real host provenance is
already there for free". It is there. It belongs to a different program.

v0.29 recorded it as E4 rather than fixing it, on this reasoning:

> A host step record is `@{op, detail, line, show, depth, inputs, count,
> value}` and a guest box is `@{v, op, ins}` — no line, no op/detail split,
> no count. Making the family correct means widening `mkb` and every one of
> its several hundred call sites …

**Two thirds of that estimate was wrong, and finding out cost one grep
each.** `mkb` was not widened. Not one of its call sites changed.

### The two recoveries

**`Prov.label()` is invertible.** A label is `op + " " + detail`
(`values.py`), and the guest box already stores the composed label. If no
host `op` contains a space, splitting at the FIRST space recovers both
halves exactly. It does not: over every node of four representative
programs, zero ops contain a space, and the inversion is exact on every
label collected. `tests/test_v30.py::
test_the_label_split_is_exact_for_every_non_miss_op` asserts it against the
HOST's vocabulary, so widening the host is what makes it red.

**A miss node's `detail` IS its reason.** The split's one blind spot is a
miss: `mk_miss` stores the whole reason sentence as the detail (host label
`/ division by zero`) while the guest box is labelled `/` alone, so `detail`
came back `""`. But the guest box's *payload* is the miss, and the reason is
one `reasons()` call away — separated from the detail only by the
` (line N)` suffix `mk_miss` appends, which for a guest miss is a
self_eval.lang line and is this evaluator's oldest documented divergence.
Drop the suffix and the detail agrees. This is sound only because
`mk_miss(reason, line, op, detail="")` is never called with a `detail`
argument anywhere in the tree — `detail=` appears zero times in
`whence/interp.py`, and the test asserts that rather than assuming it.

### The design decision: no identity

What could not be recovered is the one thing v0.29 named correctly:

> `walk_steps` additionally dedups shared nodes BY IDENTITY, which Whence
> has no operator for (`==` is structural, so two distinct nodes that
> happen to be equal cannot be told apart).

Three options, and the reason for the choice matters more than the choice:

| | what it does | why not |
|---|---|---|
| add `same(a, b)` | reference identity as a builtin | makes the evaluator's own sharing — shared literal nodes, `MergedProv` runs, any future hash-consing — **observable, and therefore frozen** |
| dedup structurally | merge equal subgraphs | the opposite error: merges distinct-but-equal steps, an UNDER-report, and costs a deep comparison per node |
| **no dedup** | visit a shared node once per path | over-reports a shared node; the count is an **upper** bound |

The first is the interesting rejection. Whence's subject is transparency of
DERIVATION. An identity predicate would buy a small amount of that with
transparency of ALLOCATION, and allocation is exactly the thing every
optimization this language has shipped (v0.2 retention, v0.3 lazy `show`,
v0.6 `MergedProv`, v0.10's raw constructor, `WList`'s shared tip) is allowed
to change. `skills/optimization-transparency-differential/` exists in this
program because that boundary is easy to cross by accident; v0.30 declines
to cross it on purpose.

No dedup makes the walk exponential in a shared history's depth. So it
carries a budget, and over the budget `steps`/`blame` **miss and name the
number**:

```
let x0 = 1 + 2
let x1 = x0 + x0
... 24 levels ...
len(steps(x24))
# host:  52
# guest: guest steps gave up: history has more than 5000 steps
#        without identity dedup
```

A short list returned silently is the one failure mode here that would look
like an answer. This is the same instinct as v0.26 (a runaway tail loop is a
miss, not a hang) and v0.27 (a size nothing bounds is a hang), one level up.

### The three divergences that remain, and their tests

| | what the host does | what the guest does | test |
|---|---|---|---|
| identity | each shared node once | once per path — an upper bound | `test_a_shared_node_is_over_reported_never_under_reported` |
| line | the real source line | `0`, always | `test_every_guest_step_reports_line_zero` |
| count | a merged run has `count > 1` | never merges; `count` is always 1 | `test_the_guest_never_merges_a_tail_loop` |

Each is asserted as a RELATION, not as a number: the identity one asserts
`guest > host` on a sharing program and `guest >= host` over the whole
agreement corpus, and the merge one asserts `max(host counts) > 1 and
set(guest counts) == {1}` — so a change to how many steps the loop takes
does not make any of them red for the wrong reason.

### What `diverge` and `contrast` still do, and why they are still E4

They still delegate, and they are still wrong for exactly the reason they
were:

```
let x = 1 + 2
let y = 1 + 3
contrast(x, y)
# host:  origin 1 of 1 (value):
#          3 ← let x  (line 1)       │   4 ← let y  (line 2)
#            3 ← +  (line 1)         │     4 ← +  (line 2)
#            ▶ 2 ← literal  (line 1) │     ▶ 3 ← literal  (line 2)
# guest: origin 1 of 1 (step):
#        ▶ 3 ← let a0  (line 2893) │ ▶ 4 ← arg p  (line 1743)
```

`diverge` decides sameness by `na is nb` and memoises on
`(id(na), id(nb))` — the identity the language declines to expose, used
twice — and `render_contrast` lays two rendered histories into
width-matched columns. Neither is a rule a Whence expression can state.
E4 survives, narrowed from five builtins to two.

**And no case in `tests/test_v29.py`'s atlas reaches the remainder.** Its
104 `diverge`/`contrast` cases are argument-SHAPE cases and all 104 agree.
So E4 joins E3 in that file's declared exclusion from
`test_each_exemption_is_load_bearing`, and is carried live by
`tests/test_v30.py::test_diverge_and_contrast_still_answer_from_the_wrong_history`,
which builds two histories that actually diverge. An exemption a corpus
cannot reach is not evidence, and pretending otherwise is how a retired
divergence reads as coverage.

### Numbers

Measured on the 234-case provenance-family subset of v0.29's atlas — the
only cases whose guest side this round could change — with the OLD library
and the NEW one, against the same host outcomes:

| | v0.29 | v0.30 |
|---|---|---|
| family cases agreeing | 204 / 234 | **208 / 234** |
| E4 (provenance family) | 3 | **0** |
| E1 (`why` is reified) | 9 | 8 |
| E2 (a callable is a record) | 18 | 18 |
| `len(steps(1 + 2))`, guest | 284 | **4** (host: 4) |
| `len(blame(1 / 0))`, guest | 9 | **1** (host: 1) |
| whole atlas agreeing | 6 857 | **6 861** (derived, +4) |

The whole-atlas figure is DERIVED from the subset, not swept: nothing
outside the provenance family reaches the code this round changed. It is
stated that way on purpose, so a later sweep can falsify the derivation
rather than merely disagree with a number.

The one surprise in that table is the E1 row. Fixing `steps`/`at`/`blame`
also converged one case that was classified E1, because `at`'s
"no step named 'x' in the history of …" clause used to render the guest's
payload and now renders `show(strip(root))` — v0.29's own new builtin, used
by the first caller outside self_eval.lang's internals. A fix and a
rendering exemption met in the same sentence.

### The methodological rule

**An estimate of a fix's size, made from the shape of the data, is a
prediction and should be checked before it is banked as a reason not to
try.** v0.29's "several hundred call sites" was a real reading of a real
constraint — a guest box has three fields and a step record has eight — and
it was wrong about two of the three missing fields, because both were
recoverable from fields the box already had. Round 377 found the same shape
in its own file (a docstring's "would dominate the campaign" overstated by
15x, and one sub-10-second measurement would have said so). The rule:
**when a design note explains why something was not done, the explanation
is a claim with a cost, and the cheapest ones should be re-run before the
next round inherits them as fact.**


## v0.31 (round 380, language C) — the exemption that was two claims, and the precondition that was a grep

**Decision 39.** Round 378 closed v0.30 with a methodological rule of its
own — *"when a design note explains why something was not done, the
explanation is a claim with a cost"* — and left two items behind that both
turned out to be instances of it, one of them written by that same round.

### E4's remainder: `diverge` / `contrast`

v0.30 fixed `steps`/`at`/`blame` and left the other two delegating, with
this reason:

> `diverge` memoises on `(id(na), id(nb))` and short-circuits on
> `na is nb`, and `render_contrast` column-aligns two rendered histories —
> neither is a rule a Whence expression can state.

Three claims. Priced one at a time:

* **`na is nb` is an optimisation, not a rule.** Comparing a node with
  itself structurally reaches the same verdict by construction: the ops
  match, every input pair is a child against itself, the payload is the
  same object. Identity buys the host `O(1)` where the guest pays
  `O(subtree)`; it buys no *answer*. Pinned live rather than argued:
  `len(diverge(v, v))` is 0 on both sides for five shapes including a
  miss, a nested list and a call result.
* **The memo is load-bearing, and only for MULTIPLICITY.**
  `origins.append` runs once per DISTINCT node pair, so a pair reachable by
  two lockstep paths is reported once. Without identity the guest reports
  it once per PATH. That is the *same* upper-bound relation decision 38
  already accepted for `steps`, applied to a second query — not a new
  concession.
* **Column alignment is `ljust`,** and `ljust` is
  `s + spaces(w - len(s))`.

So: **option (b), a structural approximation honest about what it
approximates.** Measured over a 15-program corpus, 12 answers agree with
the host BYTE FOR BYTE — the `│` column rule, the `▶` origin marker, the
`origin K of N (kind):` headers — and the other 3 differ only in the
`(line N)` suffix of a miss reason, the language's oldest documented
divergence. E4, which v0.29 called "the largest known guest divergence in
the language's signature feature", is **retired**.

Divergences (1)–(3) are inherited from § v0.30. Two are this feature's own,
and both are stated as measurements:

| # | divergence | measured |
|---|---|---|
| 4 | no `count` origin: the host merges a tail loop and reports a `step` origin when two counts differ; the guest never merges, so that clause cannot fire. It does **not** follow that the guest reports fewer origins — the unmerged runs differ in *length*, so the guest finds shape mismatches instead. | `go(5)` vs `go(7)`: host **3** origins, guest **7** |
| 5 | every route, not the shortest: `_pair_path` is breadth-first, so the host renders the SHORTEST lockstep route to an origin, once; the guest descends once per path and renders every route, including the shortest. | a value shared at two depths: host **1** block of 5 rows, guest **3** blocks (6, 6, 5), **the host's block among them character for character** |

Divergence 4's row is worth reading twice. The first draft of this table
said the guest "under-reports exactly this one kind of origin"; the
measurement said 7 against 3, and the comment in `self_eval.lang` now
records that it was corrected and why. *Neither side is silent about a
real difference* — the divergence is in WHERE and HOW MANY, not in
WHETHER.

### The precondition that was a grep

v0.30's second recovery was that a miss node's `detail` *is* its reason, so
`reasons()` can recover the half the guest's label does not carry. It
proved that like this:

```python
assert "detail=" not in src, "a mk_miss call now overrides `detail`"
```

`mk_miss(reason, line, op, detail="", inputs=())`. `detail` is the **fourth
positional parameter**, and 21 of the 87 `mk_miss` call sites in
`whence/interp.py` pass it positionally — 14 `call`, 3 `name`, 4 `typed`.
The grep is true. The property it stood for is false 21 times.

It bit twice, because the guest re-implements `call` itself and delegates
the other two:

```
let r = nosuch + 1              host detail: nosuch    guest: unbound name 'nosuch'
let r = typed("s","num","p")    host detail: p         guest: p expected num, got str
```

A third divergence surfaced from the same investigation and is a plainer
bug: `apply_host_builtin`'s curated inputs for `put` and `note` describe
the host's `derived` node and were being applied to its `mk_miss` node too,
where the host passes *every* argument. `note(1 + 2, "m")` had **3** guest
steps where the host has **6** — the whole derivation of `1 + 2` simply
absent from the history.

Observable `steps(r)` agreement over a 56-call corpus, comparing
`[op, detail, depth, inputs]` for every step: **45/56 → 49/56**. The seven
that remain are one named class — a DELEGATED builtin's *success* detail
(`note m`, `put b`, `has a`, `range 0..2`, `guess s`, `diverge 1 origins`)
plus one input-order case in `get` — measured, recorded, not fixed.

### The budget was unfalsifiable, not wrong

`GUEST_STEPS_BUDGET = 5000` was v0.30's one unmeasured quantity.
`skills/measured-budget-sizing` step 1 is *find a cheap proxy and validate
it*: the guest walk visits a node once per root-to-node PATH, so
`paths(n) = 1 + sum(paths(c))` over the host DAG is the same number without
running the guest at all. Validated against the real
`len(guest_walk_steps(...))` on a 10-program sample — and the first run
disagreed on one case, which is how the `note` bug above was found. A proxy
that has to be validated is a differential.

Swept over all 526 top-level bindings of every parsable example:

```
                min   p50   p90   p95        p99          max
guest paths       1     1    24    43   ~3.06e8   uncountable (24 bindings)
```

The distribution is **bimodal with nothing in the middle**. The ordinary
mode tops out at **123** paths; the next value anywhere in the corpus is
**71 552**. So a budget of 100 and a budget of 50 000 refuse the same
programs to within 2 bindings of 526 (0.4 percentage points), and no value
in `[369, 71 551]` changes a single verdict. 5000 is not a tuned number and
it is not a wrong one: it sits in the middle of a band two and a half
orders of magnitude wide over which the constant has **no observable
effect**. It is kept, and it now carries its evidence plus two pins — at
least 10x the measured corpus max, and inside the insensitive band — so a
future example with a 6 000-path history fails a test instead of silently
turning `steps` into a refusal.

### Two corrections carried from round 210 and round 335

* **`GUEST_MAX_DEPTH`'s justification.** Round 210 wrote "no example or
  self-hosting test corpus this project has ever run comes close to 400
  real guest-level call frames". Re-bisected from scratch: the guest
  answers `go(399)` and refuses `go(400)`; the host answers `go(200000)`.
  Four contracts pinned in this project's own examples demand 10 001 to
  200 000 frames, and they went unnoticed because they are all TAIL calls,
  which SPEC rule 8 says cost the host nothing and which the guest charges
  one frame each. The number stays (a graceful miss at a predictable depth
  still beats depending on where the host's guard lands); the ceiling is
  now a **declared divergence** in `self_eval.lang`'s module header, where
  it had never been.
* **`show` was not in the fuzz grammar.** Round 335 closed exactly this
  gap by diffing `BUILTIN_ARITY`'s keys against
  `interp._make_builtin_table()` and recorded that it had. Nothing re-ran
  the diff, so v0.29's 37th builtin re-opened it six rounds later. The diff
  is now a test, and `examples/show.lang` gives the builtin the example it
  never had.

### The methodological rule

Round 378's rule was about *reasons*. v0.31 generalises it to *evidence*:

**A proxy is admissible only once something has compared it against the
thing it stands for.** A grep for `detail=` stands for "nothing overrides
the detail"; a substring `else if name == "diverge" {` stands for "the
guest still delegates" (that one *also* failed this round — it kept passing
after the delegation was deleted, because the new dispatch line spells the
same nine characters); a path count over the host DAG stands for the guest
walk's length. The third was validated, disagreed on one case, and found a
bug. The first two were not, and both were quietly false. The cost of
validating is one comparison; the cost of not validating is a test that
reports coverage it does not have.

## v0.32 (round 384, language C) — the miss nobody looked at

**Decision 40.** *A miss in statement position is unobservable by
construction, so the run reports it.*

### Where this came from

Fourteen machine-written Whence programs sit untracked in `examples/` — the
output of a system that is not this research program (allowlisted in
`state/known-standing-dirty-paths.json`; v0.22 measured ten of them, there
are fourteen now). They are the only field data this language has. Ten still
fail to parse. Of the four that run:

| program | what it prints | exit |
| --- | --- | --- |
| `test_simple.lang` | `Result: 150` | 0 |
| `expense_tracker.lang` | *nothing at all* | 0 |
| `mini_agi_guardian.lang` | its banner, then nothing | 0 |
| `prod_showcase_final.lang` | `Prices: `, `Subtotal: `, … four labels with empty values | 0 |

Three of the four are silently wrong and every one of them exits 0. The
mechanism is one mechanism: `println` is not a Whence builtin (`print`
already ends the line), an unbound name is a miss, a miss is a first-class
value, and a value that is a whole statement is discarded. Nothing was
printed and nothing was said.

And the second half is worse. `expense_tracker.lang`'s discarded value is

```
fold needs a list, got <fn add_item> (arguments fit fold(fn, acc, xs))
```

which is **v0.22's clause, written thirty rounds ago for exactly this
program's bug**, sitting inside a value the language threw away without
rendering. The operator report v0.22 answered ("`fold()` returns Miss
instead of calculated values") was answered as *language* in round 354 and
the answer never reached the person who filed it. Decision 2 promises a
failure "can tell you *why*"; it can only keep that promise where somebody
asks, and this is the one position in the language where nobody can.

### What counts as a drop

A miss is **observable** when it reaches a name (`let x = f()`), a `check`,
an operand of another expression, or `print`. It is **dropped** when it is
the value of an expression statement whose value is discarded — three sites,
all of them in `whence/interp.py`:

- `Interpreter.run`'s top-level loop, **including the last statement**:
  `run` returns the `Env`, not a value, so a program ending in a bare
  `total` has nowhere to put it either. (This is `expense_tracker.lang`.)
- `eval_Block`'s non-tail statements, and
- the compiled `f_block`'s non-tail statements. A one-statement block
  short-circuits to its closure and can never skip a drop, because its only
  statement is its tail.

`exec_stmt` does **not** record. That is what keeps the REPL correct with no
REPL change: the REPL prints every expression statement's value, so nothing
there is unobserved, and it drives statements through `exec_stmt`.

Records are keyed on `(reasons, birth line, op, death line)` with a count —
a drop inside a recursion is one defect twenty times, not twenty defects —
and capped at `DROP_CAP = 100` distinct sites, with `dropped_total` counting
past the cap so the report can say what it is not showing.

### `print` is observation — and the corpus is what said so

The first run of the recorder over the 17 tracked examples reported **four**
drops, and all four were the same shape:

```whence
let runaway = loop(0)
print(runaway)          # deep.lang: the miss IS the subject of the example
```

`print(x) is x` (a pass-through, so provenance is not disturbed), so
`print(<a miss>)` is a statement whose value is a miss — and it is the one
statement in the language where that is the point rather than the defect.
`b_print` now remembers the node when its payload is a `Miss`, and
`_note_drop` skips it. With that rule the tracked corpus drops **0**, which
is the property that makes the report readable: a green corpus is a silent
one.

Two honest edges, both kept deliberately:

- `1 + print(y)` still reports the SUM as dropped. `print` showed `y`; it
  did not show the sum, and crediting it with observing a value it never saw
  would be the false negative this feature exists to prevent.
- The observed set is capped like the record. Past 100 printed misses the
  recorder errs toward REPORTING, because a false drop is visible and
  arguable and a silent one is not.

### The report, and why the exit code did not move

```
$ python3 run.py examples/expense_tracker.lang
dropped: 1 miss value computed and discarded — nothing can ask it why
  line 35 (let final_total, from line 20) — fold needs a list, got
  <fn add_item> (arguments fit fold(fn, acc, xs)) (line 15)
```

Two lines are named because they are two different facts: where the value
was **made** and where it stopped being anybody's. `run.py`'s exit contract
(0 / 1 / 2) is **unchanged** — 1 has meant "a check failed" since v0.1 and a
caller grepping for it must keep working — so `--strict-miss` is the opt-in
that makes a dropped miss exit 1. Everything else about the two runs is
byte-identical, which `tests/test_v32.py` pins.

**Decision 41.** *`unbound name 'x'` names the cure, from a table with an
entry rule — and NOT from edit distance.*

v0.22 taught the argument half of a builtin miss to name its own fix. The
unbound-name miss is the same message at the same half strength, and it is
the most common runtime miss in the field corpus: `println` appears **34
times across 9 of the 14 programs**. It now reads

```
unbound name 'println' (Whence has no `println`; `print` already ends the line)
unbound name 'return' (Whence has no `return`; a block's value is its last expression)
```

`_FOREIGN_NAMES` has 13 entries and an **entry rule**, so it cannot grow by
taste. A name qualifies only if (a) it is attested as an unbound identifier
in the field corpus — frozen in `state/whence/round-384/field-names.json`,
so the rule is checkable against a tracked file rather than against another
system's working tree — or (b) it is the keyword of a construct a numbered
decision names as deliberately absent (decision 2 "No exceptions, no null";
decision 3 "All iteration is recursion / `map` / `filter` / `fold`"); and the
sentence must name what to write in Whence instead. `printf`, `def`,
`lambda`, `elif`, `size` and `length` fail the rule and are absent.

### The rule that was built, measured and deleted

A nearest-builtin "did you mean" by edit distance was written first. Three
measurements killed it, and they are recorded because the machinery is
cheap to rebuild if the evidence ever changes:

1. **The field corpus contains no typo of a builtin.** Every name in it that
   needs help is a foreign idiom — `println` ×34, `catch` ×6, `Miss` ×6,
   `return` ×4, `for` ×2, `then` ×1. The distance rule's entire population
   was hypothetical. (`length` is not even reachable: `length`→`len` is
   distance 3.)
2. **Suggesting from names in scope is wrong in THIS language.** 17 of the
   31 programs in `examples/` (54.8 %) bind two names within distance 2 of
   each other — `a`/`b`, `d1`/`d2`, `q1_status`/`q2_status` — because a
   single-assignment language names a *series* where an imperative one
   reassigns one variable. A near-miss between user names is evidence of a
   series, not of a typo. In fuzz-generated programs it is 30.6 % of all
   name pairs.
3. **The builtin set is ambiguous with itself.** 18 of its 666 pairs are
   within distance 2 (`at`/`put`, `str`/`sure`, `find`/`fold`, `rand`/
   `range`), and `add` is distance 2 from three builtins at once. Requiring
   a unique nearest fixes that, but only by making the rule silent exactly
   where a typo is most likely.

A length guard (`len(name) >= 3 and d <= len(name) - 2`) was needed on top,
without which the rule proposes `at` for `x`, `q`, `v1` and `f6`; it fired
on 12 of a 20-name probe corpus unguarded and 7 guarded. A hint that needs
two tuning constants to stop lying is not a hint. Deleted.

The fourth cost is the one that settles it: `examples/self_eval.lang`
re-implements name lookup, so **it would have had to re-implement
Levenshtein in Whence** to keep saying what the host says — the host/guest
divergence class round 380 spent a whole round closing. A record lookup it
mirrors in four lines:

```whence
fn name_hint(n) {
  if has(foreign_names, n) { " (" + get(foreign_names, n) + ")" } else { "" }
}
```

Guest and host now word the clause identically; the full 125-case
host-vs-guest miss-message differential is green.

### Structure this forced, and what it cost

`unbound name '%s'` was **three copies of one literal** — the compiled
`f_name`, `eval_NameRef`, and `f_bcall`'s dead `fnv is None` floor — so a
clause added to one of them would have been added to one of them.
`_unbound(name, line)` is now the single constructor, which moves round
380's `mk_miss` census from 87 sites to 85 and its `name`-op detail sites
from 3 to 1. Both numbers are pinned in `tests/test_v31.py` and both were
updated with the reason; the property they guard (`detail` is positional and
says nothing about itself) is unchanged.

Cost, `bench/minof.py -n 3` against a `git archive` of the previous HEAD:
`meta direct` 4.924 → 4.754 s, `fib20 fast` 0.182 → 0.147 s, `tail100k
direct` 0.629 → 0.599 s, `self_eval direct` 2.620 → 2.643 s. Four of five
faster, one 0.9 % slower: the change is inside measurement noise, because
`f_block` pays one precomputed truth test per statement and `_note_drop`
returns on an `isinstance` unless the value is already a miss.

### What v0.32 deliberately does NOT report

- **A `let` that is bound and never read.** `expense_tracker.lang` binds
  `division_result = safe_divide(100, 0)` on purpose, to demonstrate a
  first-class error, and never uses it. That value is observable — it has a
  name — and reporting it would make the report a style checker. Whether an
  unread binding is worth its own report is a separate question with a
  separate answer.
- **A miss inside a list or a record that nothing reads.** The container was
  observed; the element was not. Reaching that needs a traversal at drop
  time and a policy for how deep, neither of which the field corpus asks
  for.
- **`print` as the only observer.** It is the only builtin whose purpose is
  to show a value to a human. If a future version adds a second one, it
  belongs in the same place, and `tests/test_v32.py`'s
  `test_print_of_a_non_miss_records_nothing_at_all` is the pin that will
  notice it being added carelessly.

## v0.33 (round 386, language C) — a cure named is not a cure followed

Decision 42, and the measurement that produced it.

### The number nobody had taken

v0.22 (round 354) built decision 32's parser half and measured itself
honestly: of the ten machine-written Whence programs a separate system
leaves in `examples/`, **one** named a cure before v0.22 and **nine** did
after; v0.23 took it to **ten**. That figure has stood, correctly, for
thirty rounds. It counts **cures NAMED**.

Nobody had counted **cures FOLLOWED**. The claim "an error that can name
the fix, names it" had been true-as-written and untested-as-used since the
day it was made — which is round 385's class exactly, one level in: *a rule
whose effect is to stop measuring something cannot be checked by the thing
it stopped measuring.* Here the unmeasured thing is what happens next.

`curecheck.py` takes the number, under a strict operational definition:

> A cure is **MECHANICAL** if the error message — body, parenthetical hint,
> line and column — determines a unique edit to the source text, with no
> appeal to knowledge of Whence the message does not itself contain.

Operationally: a program that reads the message and edits the file, whose
only licence is the transformation the hint's own example demonstrates.

### The answer: 3 of 8 cures, and 0 of 10 programs

| cure | determinacy | what the message does not carry |
| --- | --- | --- |
| `unexpected '='` | **mechanical** | — (`let name = value` shows where `let` goes) |
| `unexpected ':'` | **mechanical** | — (`@{a: 1}` beside `{a: 1}` is one `@`) |
| `two statements on one line` (separator) | **mechanical** | — ("start `X` on the next line") |
| `expected '{', got X` | under-**extent** | where the block ENDS. One position given, two needed. |
| two names in a row | under-**choice** | WHICH of the two named edits. `print(Calculating total)` wants quotes; `f x` wants parens; the message is word-for-word identical. |
| `` `rescue` is infix `` | under-**extent** | where `risky` and `fallback` begin and end |
| `'if' requires 'else'` | under-**content** | WHAT the else branch evaluates to |
| foreign word (v0.33) | under-**extent** | what to REWRITE — a construct swap, not an edit |

Three failure modes, and they are not one failure. Then the corpus:

```
$ python3 curecheck.py corpus
14 file(s): 4 parse, 4 reach a value (rc=0), 3 mechanical edit(s) in total
```

**Zero of the ten programs whose first error names a cure are fixed by
following it.** Eight stall on the *first* error. The two that move —
`nano_reasoner.lang` and `whenceguard_auditor.lang` — stall on the second.
Only **3 mechanical edits exist in the whole corpus**.

And one of those three is worse than a stall. `nano_reasoner.lang:31` is
`risk_status = "HIGH_RISK"`; the message says, correctly, *write `let name =
value`*; doing exactly that yields

```
block must end with an expression at line 32, col 5
```

— an error that names **no cure at all**. Following the cure moved the
program from a diagnosed error to an undiagnosed one, because the mistake
was never the missing `let`: it was a mutation, and Whence's answer is an
`if` *expression*.

### The other half: a reader, and 45 edits

`state/whence/round-386/cure-ledger.json` records what a reader who applies
each cure's *intent* has to do, one literal search/replace per entry,
annotated with the cure it answers and the information the message did not
carry. `curecheck.py replay` re-applies it and re-parses between every
edit, so the number is re-derivable rather than remembered:

```
10 file(s): 10 reach a value, 2 clean under --strict-miss
45 edit(s); 45 parse-error observation(s) on the way, 32 of them distinct
7 edit(s) fixed text the grammar ACCEPTS — no message about them was ever available
determinacy of the 45: under-extent 22, under-choice 16, mechanical 4,
                       no-cure 2, under-content 1
```

Three things fall out of it.

**Reaching a value is not working.** All ten run; **eight drop a miss** and
fail `--strict-miss`. `nano_reasoner.lang` cured prints its banner and
nothing else — every output line was a `println`, and every one is a
dropped miss.

**The first parse error is not the first mistake.** Seven of
`whenceguard_v2.lang`'s nineteen edits fix text the grammar *accepts*:
`[Engineering, Marketing, Operations]` is a list of unbound names, `let
transaction_id = TXN-2026-8842` is three-term arithmetic, `miss
BUDGET_VIOLATION` parses. The file's first *reported* error is on line 9;
its first *mistake* is on line 6, and the two are the same mistake class.
The claim is tested per-edit rather than asserted: put that one edit back
into the cured file and ask whether it still parses.

**The disjunctive cure is not merely unresolved, it is sometimes wrong.**
`prod_demo_v3.lang:22` needs quotes; `prod_demo_v4.lang:31` needs
parentheses; both get the identical sentence. And `prod_demo_v4.lang:8`,
`let tax_rate = zero_point_zero seven`, needs **neither** — the author
meant `0.07`, which is not among the two spellings offered.

### Decision 42: the table the parser could not see

The corpus named the fix for its own diagnosis. Two of the stalls are
foreign *keywords* — `then`, `for` — and Whence already had the right
sentence for both, in `interp.py`, reachable only from a RUNTIME unbound
name, which a program that does not parse never becomes.

```
nano_reasoner.lang:35   if risk_status == "HIGH_RISK" then
  v0.32   expected '{', got 'then' (blocks are always braced: …)
  v0.33   expected '{', got 'then' (an `if` needs no `then`: `if c { a } else { b }`)

whenceguard_auditor.lang:19   for d in approved_departments {
  v0.32   two statements on one line (two names in a row: … a call is `f(x)`
          and text must be quoted)
  v0.33   two statements on one line (Whence has no loops; iterate with
          `map`/`filter`/`fold` or recursion)
```

The table moved to `whence/foreign.py` — forced, not preferred:
`interp.py` imports `parser.py`, so a table the parser can read cannot live
in the interpreter. `interp._FOREIGN_NAMES` is an alias, so round 384's
`tests/test_v32.py` keeps testing the live table with no edit and there is
still exactly one.

**Two names added, under rule (a) unchanged.** `zero_point_zero` is the
*second* most attested unbound identifier in round 384's frozen census — 11
occurrences across 5 of the 14 field programs, against `println`'s 34 — and
round 384 entered the first, third, fourth, fifth and sixth while stepping
over it, because a number spelled in words does not look like a foreign
keyword. It meets the written rule exactly. `one_hundred` (2) joins it. A
general English-number *decoder* was considered and rejected: that is a
PATTERN rule, the shape round 384 deleted when it deleted edit distance.

**Three constraints, each measured.**

1. *Silent about a name the file binds.* `meta.lang` and `self_eval.lang`
   both write `let then = parse_block(…)` — three bindings across two
   tracked files — because an interpreter written in Whence names an
   if-node's then-branch `then`. Without the suppression, decision 42 would
   have printed "an `if` needs no `then`" on a parse error in this
   language's own self-interpreter. `bound_anywhere` is a whole-file TOKEN
   scan: token because the file does not parse (that is the situation), and
   whole-file because over-suppressing costs a hint while under-suppressing
   prints advice that is wrong about the reader's own code.
2. *Only when the foreign word created the adjacency.* An earlier draft
   tried the offending token as well as its predecessor, and made
   `safe_divide one_hundred, zero_point_zero` — a paren-less call, round
   354's tenth case — report "Whence has no spelled-out numbers; write the
   literal `100`", shadowing the juxtaposition hint that described the
   actual mistake. The corpus caught it: the counterfactual sweep said 15 of
   45 errors changed, and one of the 15 was a regression. The rule is now 14
   of 45, all improvements, at 4 distinct sites.
3. *In `miss` position the miss-reason clause wins.* Round 384's next-step
   1: `miss DEPT_NOT_APPROVED` reported `unbound name 'DEPT_NOT_APPROVED'`
   and the atom the author wrote as the reason survived only as the subject
   of a complaint about scope. Decision 41's own clause covers it — *a miss
   reason is a string* — and the census says the guard must be ORIGIN +
   `op == "name"`: `miss reason` over a BOUND name is the idiomatic
   spelling and the tracked corpus uses it **14 times**. `miss null` takes
   the miss-reason clause, not "Whence has no null; a missing value is
   `miss <reason>`", which is advice to write what is already written.

### Measured

```
languages/whence  run_tests_fast.sh          1699 passed, 3 skipped,
                                             81 deselected (1670 baseline, +29)
                  tests/test_v33.py          23 passed
                  run.py examples/self_eval.lang   159 checks, 0 failed
                  run.py examples/self_host.lang   133 checks, 0 failed
                  run.py examples/meta.lang         25 checks, 0 failed
curecheck.py      corpus                     0 of 10 fixed mechanically
                  replay cure-ledger.json    10 of 10 reach a value,
                                             2 clean under --strict-miss
                  counterfactual sweep       14 of 45 hints improved by v0.33
```

### What v0.33 deliberately does NOT do

It does not make any under-determined cure mechanical. The braced-block
hint still cannot say where a block ends, the juxtaposition hint still
cannot choose between quoting and calling, and `'if' requires 'else'` still
cannot know what value belongs in the branch — and the round's own finding
is that *naming the right construct is not the same as determining the
edit*, which is true of decision 42's clause too. It does not add a
recogniser for `expected (, got 'sum_lines'` (a `fn` EXPRESSION may not be
named — a real no-cure error the corpus hit twice) or for `block must end
with an expression`; both are named as next steps with corpus counts rather
than fixed on one sighting. It does not touch the `9/10 -> 10/10` figure:
that was a true statement about naming and this is a different property
measured beside it. And it repairs none of the field programs — they belong
to another system; every cure in this round was applied to a copy.
