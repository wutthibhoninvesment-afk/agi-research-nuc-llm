# Pitfall history — full mechanism detail

Full "confirmed live" write-ups for `tiny-language-implementation`'s longer
pitfalls, moved here (round 315) to keep `SKILL.md` under the skill-lint
line-count warning as the list keeps growing round over round — the same
split `session-inheritance-audit/references/pitfall-history.md` used at
round 285. `SKILL.md`'s own Pitfalls section keeps a one-line gist + link to
the matching section below; read the section here before you need the full
round citations or the exact reasoning behind a fix — the gist alone is not
enough to re-derive them.

## Contents
- [A grammar-directed fuzzer silently feeds new host syntax to the guest parser too](#host-feature-fuzzer-guest-parity-gap)
- [Guest support for a value can be a straight host delegation, not a reimplementation](#guest-evaluator-in-host-language-delegation)
- [A self-hosted guest's builtin dispatch has two independent gates](#self-hosted-dispatch-two-gates)
- [A delegated builtin returning a raw unboxed record breaks boxed guest reads](#host-builtin-raw-unboxed-record)
- [A scope-mirroring analysis must record non-matches explicitly, not just skip the write](#scope-mirroring-must-record-non-matches)
- [Extending a scope-mirroring analysis into a branch construct often needs no new plumbing](#scope-mirroring-branch-construct-extension)
- [The hop-by-hop value-flow recipe, and its hard edge](#hop-by-hop-value-flow-recipe)
- [A flat scope-stack spanning every open fn can leak an enclosing fn's fact inward](#flat-scope-stack-cross-fn-leak)
- [Make a nondeterministic builtin reproducible instead of special-casing every oracle](#deterministic-nondeterministic-builtin)
- [A differential harness's two builders silently drifting on an unstated default](#differential-harness-default-value-mismatch)
- [A "gap" a design sketch describes can be the family's own founding, deliberately-tested boundary](#dynamic-call-graph-founding-boundary)
- [A self-hosted guest parser can byte-match the host on every success path while silently diverging on a rejection path](#parser-differential-rejection-path-gap)
- [Once one guard family has a success-path-only test gap, audit SIBLING guard families from the same era before assuming it was a one-off](#sibling-guard-family-audit)

<a id="host-feature-fuzzer-guest-parity-gap"></a>
### A grammar-directed fuzzer generating a new host syntax feature will feed it straight into the hand-copied guest parser too, unless told not to
The guest lexer/parser (self-hosting, step 10) is a snapshot of host syntax
at whatever round it was written; it does not automatically grow when the
host parser does. A shared program generator that emits the new construct
for both host and differential-guest runs turns "guest doesn't support this
yet" into a false divergence finding instead of an honest, tracked parity
gap. Give the generator's guest-facing path an explicit no-op override for
every host feature the guest doesn't parse yet, verify with a fuzz seed that
0 guest-generated programs contain the new construct, and track closing the
gap as backlog — twice in this program a feature's fuzz coverage (host-only)
and its real guest parity landed multiple rounds apart (`: Type`/`-> Type`:
round 134 fuzz-only to round 158 guest parity; an effect system repeated the
same two-step shape one round later, still open).

<a id="guest-evaluator-in-host-language-delegation"></a>
### When the guest evaluator is itself written IN the host language and runs as literal host source (self-hosting), a new builtin's guest support can be a straight delegation, not a reimplementation — but every existing "what type is this value" probe must be re-audited for it
Round 176's Whence guest (`self_eval.lang`) added guest support for `guess`/
`is_guess`/`confidence`/`sure` (an uncertainty-carrying value with
weakest-link confidence propagation through arithmetic) by having the
guest's `apply_host_builtin` call straight through to the REAL host
builtins — the guest program is executing as genuine top-level host source,
so `a.v + b.v` on a wrapped value already gets the host's own propagation
semantics for free, no guest-side reimplementation needed. This was expected
going in to be "a materially bigger lift" than the guest's earlier `: Type`/
`effects` parity work (both of which only needed parse-time clause-skipping)
— the delegation shortcut closed it in one round instead. The cost: every
guest helper that asks "is this value a number/bool/list" (`is_num`,
`is_bool`, `is_list`, a `kind` dispatcher) was written before the new value
existed, and the new value's arithmetic transparently succeeds on those same
probes (`missed(guess(5,...) + 0)` is false, so a naive `is_num` misreports
a guess as a plain number) — each such probe needs an explicit
`is_<newthing>(v)` guard added FIRST, or every downstream dispatch that
assumes "arithmetic succeeds implies plain number" silently misclassifies
the new value. Grep every `is_*`/`kind`/`show`-style probe in the guest for
this before declaring delegation-based parity done, don't just add the new
builtins.

<a id="self-hosted-dispatch-two-gates"></a>
### A self-hosted guest evaluator's builtin dispatch has two independent gates — name resolution, then arity/type dispatch — and a builtin missing from the FIRST gate fails as "unbound name", which reads like an unrelated bug
If guest calls resolve by looking the callee name up in an
environment/name table (seeded with builtin-ref bindings once at store-init
time) before the dispatcher ever runs, a builtin that already exists at the
host level — even with delegation code already written for it elsewhere in
the guest evaluator — can still be completely unreachable from guest
programs if its name was simply never added to that table. The symptom is
"unbound name 'x' (line N)" thrown from the guest's OWN lookup helper, not
an arity mismatch and not the generic "not implemented in the guest" stub a
missing-dispatch-branch bug would produce — don't debug it as either of
those. Confirmed twice on the same interpreter (Whence rounds 206/218): a
whole builtin family (`steps`, then `at`/`blame`/`diverge`/`contrast`) sat
outside `self_eval.lang`'s `builtin_names`/`arities` tables even though
nothing else about them was guest-incompatible. The fix each time was three
additive lines — the name in the name table, its arity, one dispatch branch
delegating straight to the real host builtin using the guest box's
already-real host-value payload (see the delegation pitfall above) —
closing a years-old gap in under an hour once diagnosed. Decide whether the
new dispatch branch belongs on the "propagating" (miss argument
short-circuits) or "total" (must still run on a miss, e.g. to inspect the
miss's own history) side by reading the HOST's own totality comment for
that builtin family, not by guessing or waiting for a test to fail — round
206 caught that `steps` needed to stay total from the host docstring alone,
before writing any test.

<a id="host-builtin-raw-unboxed-record"></a>
### A host builtin that returns a raw, unboxed record can silently break guest code that assumes every value is wrapped
If guest values are boxed for metadata (see the provenance-boxing step in
SKILL.md's own step 10) but a builtin you just delegated to returns the
host's own internal record shape (fields the box format doesn't have, no
wrapper field guest code expects first), then guest code that reads through
it — indexing into the result, then field-accessing an element — mismatches
the expected shape and reads as a miss, not a clear type error. Confirmed in
Whence (round 218): `steps(x)[0].op` misses because `steps` returns a list
of bare host `Record`s but the guest's list-element passthrough path
expects every element to already be a `{v, op, ins}` box. This is a second,
independent gap from the name-resolution one above — closing name
resolution does not by itself fix representational mismatches in what a
delegated builtin hands back; don't assume "it resolves and dispatches now"
also means "every consumer of its result is compatible."

<a id="scope-mirroring-must-record-non-matches"></a>
### A scope-mirroring static analysis (parse-time effect/alias/purity checks) must record NON-matches explicitly, not just skip the write when there's nothing interesting to say
If a per-scope tracking dict is only ever written to when a binding IS the
thing you're tracking (e.g. "this name aliases a known effectful builtin"),
then an ordinary, unrelated local binding that reuses the same name in an
inner scope writes nothing — and a lookup that walks outward from the inner
scope finds nothing there either, so it falls through to an OUTER scope's
stale match and misidentifies the unrelated local as the tracked thing. This
is the same bug shape as a cache that only writes on a hit and never on an
explicit miss: a later lookup can't tell "never computed" from "computed and
irrelevant here." Fix: write `None`/a sentinel for every binding in the
tracked namespace — not just interesting ones — so an inner scope's entry,
present but empty, correctly blocks fallthrough to an outer scope's real
match (Whence round 266, v0.14.2's `alias_scopes`: a `let p = print` then an
unrelated inner `let p = 5` would otherwise let a `p(...)` call in the inner
block wrongly resolve to the outer `print` alias).

<a id="scope-mirroring-branch-construct-extension"></a>
### Extending a scope-mirroring static analysis to recurse into a branch construct (`if`/`else`, `match`) often needs NO new scope-context plumbing — check whether the branch is itself a block whose own fact was already resolved while ITS scope was still open, before assuming you need to re-derive it after the fact
It's tempting to conclude "a tail that is itself an `if` can't be inspected
the same way a bare name can, because by the time we look at it the
branch's own scope has closed" — true only if you'd need to re-run the
ORIGINAL resolution (e.g. re-look-up a bare name against scopes that no
longer exist). If each branch is its own block, parsed via the same
recursive `block()`/`stmt_list()` that already computes and STORES a
per-block fact (e.g. a `tail_alias_tag` field) while that block's own frame
was open, then reading that already-resolved field back later is a purely
structural, scope-free walk — the same shape a separate boolean-only
structural pass (e.g. tail-call marking) already has. Confirmed in Whence
(round 276, v0.14.5): a fn body whose tail is `if c { print } else { print }`
was flagged three rounds earlier as "can't simply run after the fact" and
left as a documented, un-revisited gap — it turned out to need zero new
stacks, just reading `if_node.then.tail_alias_tag` and
`if_node.otherwise.tail_alias_tag` (recursing through an `else if` chain)
and requiring an EXACT match across every arm, not "any arm", to stay sound
(an approximate match would create a false negative that looks like a fix
but is actually unsound). Before writing off a branch construct as "needs
interprocedural analysis," check whether the per-block fact you need is
already sitting on the AST node from an earlier pass.

<a id="hop-by-hop-value-flow-recipe"></a>
### A scope-mirroring analysis can be extended hop-by-hop to track a value across function-call boundaries with the SAME repeatable recipe every time — but the recipe has a hard edge, and knowing where that edge is matters as much as the recipe itself
Validated identically across four consecutive rounds of the same feature
family (Whence v0.14.9: param called directly; v0.14.10: the anonymous-fn
variant; v0.14.11: a same-body rename of the param, then called; v0.14.12:
the param returned across a call boundary, then called by the caller) —
each landed in its own round with zero rework of the others: (1) add ONE
new scope-stack, pushed/popped at the IDENTICAL per-block/per-fn-definition
sites every EXISTING stack in the family already uses (never invent a new
push/pop site); (2) write a resolver that combines a fact recorded ONCE at
the callee's own definition (independent of any call site) with the ACTUAL
arguments at ONE specific call site, to decide whether that one call site is
sound; (3) once the resolved fact lands in the ordinary alias-tracking table
the check-site code already reads, the actual verdict dispatch needs ZERO
new branches — the same fact-producer/fact-consumer split makes 3 of the 4
rounds land with no changes to their own readers at all. Keep each hop
deliberately narrow (bare-NameRef only, no widening to `if`/`else` tails, no
crossing into an ancestor fn's own frames — see the next pitfall) and pin
its boundary with an explicit negative test, not prose.

The recipe's limit is just as load-bearing: three consecutive rounds (302,
306, 308) independently re-confirmed the SAME two remaining gaps — an
argument reaching the target through a SECOND function call, and a dynamic
call graph (a different, unrestricted fn performing the effect) — are NOT
another one-hop slice, because both need the verdict to depend on WHICH
call site you're checking (per-call-site specialization) rather than only
on the callee's own definition, or else an unsound over-approximation.
Don't spend a round trying to force either into this recipe without a real
design sketch first — every round in this family that considered it said so
explicitly rather than attempting a partial fix. Round 312 later closed the
first of these two gaps (second-function-call chaining) as a genuine
extension of the recipe once the missing piece — resolving through a SECOND
scope, not just one hop — was designed explicitly rather than forced. Round
314 attempted the second gap (the dynamic call graph) with an explicit
design sketch and found it is NOT closeable the same way even with one — see
[the founding-boundary pitfall below](#dynamic-call-graph-founding-boundary).

<a id="flat-scope-stack-cross-fn-leak"></a>
### A flat scope-stack that spans every open block AND fn (not just the currently-open one) can let an ENCLOSING fn's own recorded fact leak into an INNER fn's check via a coincidental name collision
If a resolver for a hop-tracking stack (the recipe above) walks the whole
stack innermost-first with no lower bound, and an inner fn happens to
redeclare a name the resolver would otherwise still find further out, the
walk can attribute a call inside the inner fn to the OUTER fn's own tracked
value — one that isn't even among the inner fn's own declared parameters.
Fix by locating the currently-open fn's own params frame by IDENTITY inside
the base scope stack first, and bounding the hop-stack walk to that index
and everything pushed after it, never crossing into an ancestor fn's own
frames (Whence round 306, v0.14.11's `_resolve_param_alias`). Write the
specific cross-fn-boundary misattribution case as its own test — it's easy
for this to look harmless (the misattributed name is dead data a later step
never visits) rather than prove it can't ever flip a verdict.

<a id="deterministic-nondeterministic-builtin"></a>
### Adding a genuinely nondeterministic builtin (`rand`, a clock, real I/O) to a total, differentially-tested language breaks every oracle that assumes a program's behavior is a pure function of its source text — fix this by making the builtin REPRODUCIBLE, not by special-casing the oracles
A three-way differential (three independently-constructed interpreters), a
guest/host self-hosting comparison, and a fast/slow reference-diff bench all
silently assume re-running the same source yields the same result; a
builtin that draws from OS entropy breaks that assumption for every one of
them at once, and the fix looks like it needs a special case in each.
Instead give the interpreter its own seeded stream at construction time
(`Interpreter(seed=0)` → `self._rng = random.Random(seed)`, a per-instance
field, not a module-global) and have the builtin draw from `interp._rng` —
two interpreters built at the same seed then draw the identical sequence, so
every oracle that already compares two interpreters' output keeps working
with ZERO code changes, because "same input source" now really does imply
"same output" again (the seed is part of the input). This is a deliberate
divergence from mainstream languages (most seed `random()` from OS entropy
by default) — the same value judgment deterministic-replay execution
environments make, and the only choice under which real randomness and
full-determinism testing coexist without a special case anywhere (Whence
round 294, v0.14.8's `rand()`: `Interpreter.__init__(..., seed=0)`,
`whence/interp.py`'s `rand` node reading `interp._rng.random()`). Decide
this BEFORE writing the builtin, not after an oracle starts flaking —
retrofitting a seed onto an already-shipped entropy-backed builtin means
every prior recorded oracle run is now unreproducible.

<a id="differential-harness-default-value-mismatch"></a>
### When a differential/self-hosting comparison's two sides are built by two different code paths, an unstated default-value MISMATCH between them silently reclassifies real bugs as expected divergence instead of causing a visible failure
If the comparison already has a named exemption bucket for "one side
legitimately has a lower resource ceiling than the other" (e.g. a guest
evaluator paying more host frames per guest call than the direct host path,
so it can exhaust a depth/step budget the host doesn't), then giving each
side's builder its own independent default for that ceiling — one
defaulting to `None` (resolves to the interpreter's own unrelated top-level
default, e.g. 20000) and the other defaulting to a much lower, deliberately
chosen comparison value (e.g. 2000) — silently WIDENS that exemption: a real
mismatch that would surface as a genuine divergence between a depth-2000
host and a depth-2000 guest instead gets swallowed as "expected depth skew"
between a depth-2000 host and an unrelated depth-20000 guest. This is a
coverage gap, not a crash or a false positive, so nothing in a green test
suite flags it — it only shows up as "this class of bug can no longer be
found," which is easy to miss for many rounds. Confirmed in Whence's
SWE-loop harness (round 289 flagged it, round 295 fixed it):
`GuestHarness.__init__` defaulted `max_depth=None` while `oracle_self_eval`'s
own host-side default was `2000`; the fix was making the guest builder take
the SAME `max_depth` the host side already uses as an explicit, threaded
parameter (and keying any cache on `(pkg, max_depth)`, not just `pkg`, so
two different depths for the same package never silently share one cached
instance) rather than letting each side pick its own default. When auditing
a differential harness, grep both builder call sites for every parameter
that has a *named* exemption bucket in the comparison logic and confirm
both sides pass the same value — an exemption bucket existing at all is
evidence a mismatch has bitten this comparison before.

<a id="dynamic-call-graph-founding-boundary"></a>
### A "gap" a design sketch describes can actually be the analysis family's own founding, deliberately-tested boundary — the only reliable way to tell the two apart is to implement the sketch in full and run the WHOLE suite, not to re-read the sketch a second time
The hop-by-hop recipe above ([link](#hop-by-hop-value-flow-recipe)) names
two gaps it can't reach without per-call-site specialization: an argument
reaching the target through a second function call (closed at round 312),
and the dynamic call graph — a different, unrestricted fn performing the
effect, checked by requiring the CALLER's own declared scope to be a
superset of every callee it calls (Whence's v0.14.13 design sketch,
"approach 1: declared-superset propagation"). Round 314 implemented
approach 1 in full — a new scope-stack, resolver, and call-site check,
mechanically identical in shape to every prior hop in the recipe — and it
worked exactly as the sketch's own worked example predicted. Then the full
suite (`tests/test_v14.py`) fell from 113 to 105 passed. Reading every
failure in full (not patching them to pass) showed 7 of 8 were TRUE FALSE
POSITIVES: previously-legal, already-tested, DELIBERATELY-DESIGNED programs
(a NAMED fn with its own sufficient `effects [...]` clause, called from a
more tightly-scoped enclosing fn) that this family has held as correct
since the effect system's own first round (round 146: "calling a different,
unrestricted function that itself performs an effect is untouched by the
caller's declaration," pinned by `test_nested_undeclared_fn_escapes_outer_
purity`, cited by that exact name in the ORIGINAL SPEC text) and reaffirmed
at round 300 (`test_check_uses_callees_own_scope_not_the_callers`: "the
check is against the callee's OWN declared scope, not the caller's"). The
8th failure was a diagnostic regression, not a false positive — the new
check preempted an existing check's own argument-dependent message with an
unconditional, earlier one, proving it didn't compose with the family's
existing mechanisms so much as race them. The new code was reverted in
full; the finding was written up as closing the backlog item, not as a bug
to fix, because the "gap" was the feature working exactly as designed since
its very first round.

The generalizable lesson: a design sketch that is mechanically identical in
shape to every other hop in an established recipe can still be UNSOUND
against the family's own founding tests, and manually probing only the
sketch's own worked example will not surface this — it takes a real
implementation plus a full-suite run to find a conflict with an ADJACENT,
already-shipped feature the sketch's own example never touches. Before
implementing an extension to an existing checker/analysis family: (1) grep
the test suite and the family's own original design text for tests whose
NAMES describe the opposite of what you are about to enforce (a test named
`..._escapes_outer_purity` or `..._not_the_callers` is a design boundary,
not an oversight); (2) if you implement anyway to find out for certain, run
the WHOLE suite, not just the new feature's own manual probes, before
concluding the sketch is soundly shippable; (3) if it breaks tests that
encode a deliberate, named decision, that is evidence the two questions the
family asks ("is the callee's own contract internally consistent" vs. "does
the caller need something it didn't declare") have been silently collapsed
into one — not a bug in the new code, and not fixable by adjusting the new
check's specifics; it needs an explicit, large, INTENTIONALLY BREAKING
redesign (updating the named tests to a new transitive semantics) or a
genuinely different mechanism (e.g. full bottom-up effect inference) scoped
as its own feature, never a quiet point release layered on top (Whence
SPEC.md's "v0.14.14," round 314).

<a id="parser-differential-rejection-path-gap"></a>
### A self-hosted guest parser can byte-match the host on every SUCCESS-path field spot-check while silently diverging on a REJECTION-path field no spot-check ever exercises — the fix is a canonicalized whole-tree differential across a corpus, not more spot-checks
Through round 319, Whence had two differential instruments, both at the
EVALUATOR layer: `test_self_eval.py` compares host-run vs. guest-run
*values*, and `harness/swe/guest.py`'s why-shape fuzzer compares host-run
vs. guest-run *derivation graphs*. Neither ever touches the PARSER's own
output shape — `self_host.lang`'s own 66-check test section hand-picks
ONE field at a time off a `parse_whence(...)` result and asserts on it
directly, a spot-check, not a systematic sweep. Round 320 built the first
whole-tree instrument for this layer: since a guest AST from `parse_whence`
run at host level (no `run_src`/boxing involved) is already an ordinary
Python `Prov`/`Record`/`WList` tree, both a real host `A.*` AST and a real
guest `@{kind: ...}` AST canonicalize cheaply into one shared plain-tuple
shape (built from a single `grep -n "kind:"` pass over the guest's own
literals to get the kind↔field mapping) and diff node-for-node over a
35-item corpus (22 hand-written per-node-kind snippets + 13 shipped
examples).

The first run found 4 mismatches, all one root cause, on code that had
been shipping and passing since round 158: a NAMED function's typed-
parameter guard label included `" of <fn_name>"` on the host
(`_apply_type_guards(body, params, types, fn_name)`) but never threaded
`fn_name` through on the guest side (`build_guards` always produced the
bare `"parameter 'x'"` form). This was invisible for 162 rounds because
the ONE real example that exercises this exact shape
(`examples/guess.lang`'s `fn needs_guess(g: guess) { confidence(g) }`)
only ever calls it on the SUCCESS path — the label text is data that only
surfaces inside a MISS's own reason string, on the REJECTION path, which
no existing check anywhere in the corpus ever triggered for a NAMED
function (the anonymous-fn case was accidentally fine, since the host's
own `fn_name=None` branch already omits the suffix on both sides).

The generalizable lesson: differential coverage keyed to *values a program
successfully produces* systematically misses fields that only exist in the
*shape of a rejection* — error message text, guard labels, diagnostic
wording — because a passing program never reads them and a hand-picked
field spot-check has to know in advance which field to ask about. A
canonicalized whole-tree diff needs no such foreknowledge: it compares
every field of every node kind, including ones nobody thought to name.
Before trusting a self-hosted parser/evaluator as "differentially
verified," check whether the existing corpus's error/miss programs
actually reach every field that differs only on the rejection path, or
build the whole-tree sweep instead of adding one more hand-picked
assertion (Whence round 320, `tests/test_parser_differential.py`).

<a id="sibling-guard-family-audit"></a>
### Once one guard family is found to have a success-path-only test gap, audit SIBLING guard families from the same version/feature era for the IDENTICAL gap shape before assuming the finding was a one-off
Round 320's fix (previous pitfall) closed exactly one guard family: the
v0.12 PARAMETER-type guard's guest label was missing the host's `" of
<fn_name>"` suffix for named functions. Round 326 asked the direct
follow-up question the fix itself never asked — "does the SAME bug
class recur in a SIBLING guard family?" — instead of treating round
320 as closed and moving to unrelated backlog. It does: the v0.13
RETURN-type guard has the mirror-image bug. Host `_closure_ret`
(`whence/interp.py`) only appends `" of %s" % name` when the closure
has a name at all (`name=None` for every anonymous fn); guest
`check_ret` (`examples/self_eval.lang`) built `"return value of " +
fn_name` UNCONDITIONALLY, using the guest's `"(anonymous)"` sentinel
string as `fn_name` instead of ever omitting the suffix. Invisible for
18 rounds (since round 158) for the exact same reason as round 320's
finding: the one example that exercises this shape only ever calls it
on the SUCCESS path, and no corpus program ever failed an anonymous
closure's return-type check to expose the REJECTION-path label text.
Confirmed live before fixing: host `let g = fn() -> num { "oops"
}\nlet result = g()` misses with `"return value expected num, got
str"`; guest, same source, missed with `"return value of (anonymous)
expected num, got str"` — a real, reproducible divergence, fixed by
branching on the `"(anonymous)"` sentinel the same way an existing
sibling helper (`show_callable`) already does.

The generalizable lesson: a fix for one instance of a bug SHAPE (not
just one bug) doesn't imply the shape was unique to where it was
found. When a family of near-identical guarded features shares a
version/feature era (here: v0.12 and v0.13's typed-parameter and
typed-return guards, added in adjacent rounds with near-identical
success-path-only guest implementations), a test gap discovered in
one member is evidence — not proof, but a strong prior — that sibling
members were built the same way and may carry the identical gap. This
costs nothing extra to check: no new tool, no new fuzz campaign, just
grepping the guest source for the sibling family's own guard-label
helper and asking the same "does this omit the anonymous case?"
question that closed the first instance. Do this as the LAST step of
closing any test-gap bug that came from a whole-tree/rejection-path
differential (see the pitfall above) or any other instrument that
found a bug by exhaustive sweep rather than by someone naming the
scenario in advance — those are exactly the bug shapes most likely to
recur silently in a sibling feature (Whence round 326, `check_ret`
mirroring round 320's `build_guards` fix in `_apply_type_guards`).
