---
name: declaration-scope-parity
description: Use when a language, DSL, schema or config system has DECLARATIONS that later text refers to by NAME — type/shape names, schema $refs, GraphQL fragments, macros, terraform locals, CSS custom properties, fixture ids — and the checker keeps its own table of those names. Symptoms: one user mistake produces different error messages depending on which position it is written in; some positions defer the error to run time, or fail silently with a null/empty value nobody notices; the declaration table is a flat dict with no push/pop while the system's ordinary bindings ARE scoped; an `Unbound…` sentinel exists to make a lookup that "cannot happen" safe; a comment says the table is "deliberately not scope-aware". Covers the one-mistake-N-outcomes audit, giving the static table the value namespace's own frames, splitting "unknown name" from "out of scope", and the late-binding capture check the fix makes visible. NOT for ordinary scope bugs on one lookup path, and NOT for type inference or name mangling.
---

# Declaration-scope parity

Two namespaces, one name. A declaration form (`shape P = …`, `fragment F on
…`, `locals { p = … }`) usually desugars to an ordinary binding, so the
RUNTIME already has a scope rule for its name. The checker that validates
references to it usually keeps its own table — and that table is very often
a flat, file-global dict, because it was written to answer "does this name
exist?" and nobody asked "where?".

The bug is not that the flat table accepts too much. It is that the
acceptance is *deferred*: the reference is admitted at the annotation and
fails later, somewhere else, in as many different ways as there are
positions the table is consulted from — including, in at least one position,
not failing at all.

## Trigger conditions
- A declaration form introduces a name that later text refers to by name,
  and the reference is validated against a table the checker owns.
- That table is a plain dict/set/list built during a single pass, with no
  push/pop, while the same system scopes its ordinary bindings.
- A sentinel type or "should never happen" branch exists specifically to
  keep a failed lookup from crashing (`_UnboundRetType`, `MISSING`,
  `UnresolvedRef`) — it is a marker for exactly this defect.
- The same user mistake is reported by two different messages, or reported
  in one position and silently absorbed in another.
- A second implementation (self-hosted parser, linter, LSP server, docs
  generator) had to reproduce the table and its author wrote down that it
  is not scope-aware.
- Proven on: Whence v0.18 (`languages/whence/`, round 342) — `shape`
  declarations, three annotation positions, three different outcomes, one
  of them silent.

## Steps
1. **Enumerate the consult sites, then write the SAME mistake into each
   one.** Find the lookup function and list its callers (`parse_type` had
   three: parameter type, return type, and a declaration's own field type).
   Write one minimal program per site with the identical error, run it, and
   record the outcome VERBATIM in a table. This is the finding; produce it
   before proposing anything.
2. **Read the table for two things: how many distinct outcomes, and how
   many are silent.** N > 1 means the check is at the wrong level — it is
   being made by each consumer instead of once at the reference. A silent
   outcome (a value built with a null/miss field; a "match" that quietly
   answers false) is the one to fix first and the one no
   grep-for-the-message test will ever find.
3. **Do not invent a scope rule — find the one the name already obeys.**
   If the declaration desugars to an ordinary binding, that binding's rule
   IS the answer, and it is already specified and already tested. Copying
   it is what makes the change defensible instead of a matter of taste.
   Write it down as a decision: "the X namespace is the Y namespace".
4. **Hang the frames on the function that already delimits scopes.** There
   is almost always one (`stmt_list`, `visit_block`, `enter_scope`) and it
   often already pushes/pops other per-scope stacks; add yours to that
   group so it can never be pushed without being popped. Look up
   innermost-out.
5. **Keep a never-popped "declared anywhere" set for DIAGNOSTICS ONLY.**
   It is what separates "unknown name `Nope`" (a typo) from "`L` is not in
   scope here" (a real declaration, in a block that has closed) — two
   genuinely different mistakes that deserve different sentences. It must
   not influence acceptance; if it does, you have rebuilt the flat table.
6. **Re-run step 1's enumeration.** Every site must now produce the same
   sentence, at the reference's own line, at the earliest phase that can
   see it. Keep the table in the commit message or spec: it is the proof.
7. **Enumerate what the fix makes LEGAL, not only what it forbids.** A
   scoped table admits sibling declarations of one name in disjoint scopes,
   and shadowing in a nested one, both of which a flat table refused for no
   reason. Test them, and test that the inner reference means the inner
   declaration while an outer one still means the outer.
8. **Then check the direction the fix newly exposes: does run-time
   resolution agree with the static decision?** Once the checker has an
   opinion about WHICH declaration a reference names, a late-bound lookup
   can disagree with it. Write the program where they could: declare the
   shadowing binding AFTER the reference but in a scope the reference's
   env still reaches at call time. If the two disagree, that is a separate,
   usually older bug — pin it with a test that says so rather than folding
   it into this change.
9. **If a second implementation exists, port the rule and compare WORDING,
   not just accept/reject.** A differential that compares only
   failed-vs-succeeded rates every one of these cases "agreeing" while one
   side has no idea what the construct means.

## Pitfalls
- **Making it a parse error before doing step 3.** You will invent a scope
  rule, it will be slightly different from the runtime's, and the next
  round finds programs where the two disagree.
- **Assuming the change only tightens.** Steps 7's sibling/shadowing cases
  are a widening; skipping them ships a fix that still refuses valid code
  and nobody notices, because the old error message was already there.
- **Deleting the sentinel because it is now unreachable.** If the failed
  lookup happens in a path that raises rather than degrades (a host-level
  resolution, not one that goes through the ordinary evaluator), keep the
  sentinel as the floor and exercise it directly in a unit test, since no
  source text can reach it any more.
- **Dropping a specific message in favour of a general one.** A duplicate
  declaration may now be caught by the system's ordinary rebinding rule.
  Keep the specific message anyway if it fires first and something compares
  it across implementations — a redundant check with a better sentence is
  not dead code.
- **Putting the declaration's file/line into the new message when a second
  implementation has to reproduce the wording.** The extra locator is worth
  less than the wording differential it puts at risk; say so in the spec
  rather than leaving it looking like an oversight.
- **Counting brackets to recover scopes without proving the count is
  exact.** If the second implementation recovers the frame stack from the
  token stream, note which bracket kinds it counts and why including a
  balanced one (a record/object literal) shifts every position inside it by
  the same constant and so never changes an answer.

## Verification
Run from the repository that owns the language/checker:

```bash
# 1. the enumeration itself, before and after (one program per consult site)
python3 run.py -  <<< 'fn g() { shape L = @{x: num}
1 }
fn f() -> L { 1 }
let r = f()'

# 2. the whole suite, including the differential tier
cd languages/whence && python3 -m pytest -q tests/

# 3. the second implementation, end to end
python3 run.py examples/self_host.lang      # guest parser
python3 run.py examples/self_eval.lang      # guest evaluator

# 4. the corpus differential, wording included
python3 -m pytest -q tests/test_self_eval.py -k shape
```

A pass is: one sentence per mistake, identical on both implementations;
sibling and shadowing declarations accepted; the sentinel test still green;
and the newly-exposed late-binding case pinned by a test that states it is
pre-existing.
