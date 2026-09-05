---
name: liveness-is-a-claim-about-a-level
description: Use when a dead-code / orphan / reachability audit reports that something is unreferenced, unused, test-only or "not live", and the answer is about to be believed or acted on. Symptoms; an audit naming a suspiciously large or round set (every handler, every route, every builtin); orphans arriving as a same-shape FAMILY rather than scattered; a report that nothing reaches the implementation of something you know runs on every request; a plan to delete code on a grep's say-so. The move; ask WHICH LEVEL the code is dispatched at - decorator, registry table, entry-point manifest, config string, template, interpreter builtin - and re-ask the reachability question in the language the call site is actually written in. Includes the two rules that make a static orphan detector trustworthy (a decorator is a use; ambiguity resolves toward live) and the separation of instrument failures from subject failures that stops a bug in the audit being filed against the code it audits.
---

# "Nothing references this" is a claim about a LEVEL, not about a program

Every reachability tool answers the question in one language. Real systems
dispatch across levels:

| the level the tool reads | the level the call actually happens at |
|---|---|
| Python identifiers | a decorator handed the function to a table |
| Python identifiers | `getattr(self, "_stmt_" + kind)` builds the name |
| Python identifiers | an entry-point / plugin manifest names it in TOML |
| Python identifiers | a template, a route string, a serialized workflow |
| Python identifiers | **the interpreted language's own source** |

When the two levels differ, the tool is not wrong about what it measured; it
is answering a different question, confidently, in the vocabulary of an
answer to yours.

```
The iron law:  an orphan verdict is only as good as the level it was asked at.
               Before you believe it, name the level the call site is IN.
```

## The measured instance (rounds 503-504)

A scope-reachability audit swept a whole repository and reported
**37 not-live defs in an interpreter's `interp.py`** — 31 of them
`unreferenced`, the strongest verdict it makes, meaning nothing anywhere in
the tree mentions the name at all.

37 was the entire builtin surface of the language. The implementation of
`print` was in the list.

Every one of them is registered by a decorator:

```python
@register("print", 1, "v")
def b_print(interp, args, line): ...
```

`register(...)` receives the function object at definition time and stashes
it in a table under the *guest language's* name. The Python name `b_print`
is never spelled again — which is precisely and only what the audit measured.

Two separate defects, and they need different fixes:

1. **The instrument was unsound at its own level.** A decorated def cannot
   honestly be called `unreferenced`: the decorator IS a reference. Adding a
   `decorator` reference kind moved that file from 37 not-live to 0, and
   moved the whole repository's `unreferenced` count from 103 to 23 — **78 %
   of the strongest orphan claim in the tree was this one shape.**

2. **The question was being asked at the wrong level, and fixing the
   instrument does not fix that.** After the fix all 37 read `live`, which is
   true and carries no information: the table is installed into every
   environment, so every builtin is equally reachable, always. The question
   that distinguishes `print` from `contrast` is *does any program in the
   guest language call it* — and it was answered by parsing 906 guest
   programs with the guest language's own parser.

The two levels' verdicts had no relationship. The 6 the Python-level audit
called `test_only` (rather than `unreferenced`) were **not** the least-used
builtins: they averaged 20 uses in shipped example programs against 34 for
the `unreferenced` ones. The signal was not weak, it was inverted — what the
Python audit had detected was which internals a test file happened to poke
at by name.

## When this triggers

* Any `unreferenced` / `unused` / `dead code` / `no callers` verdict you are
  about to act on, quote, or delete on.
* The orphans arrive as a **family** — same prefix, same decorator, same
  directory, same arity. Dead code accumulates unevenly; a tidy family is the
  signature of a dispatch the tool cannot see.
* The count is a round number, or equals the size of a public surface (all
  the routes, all the builtins, all the handlers).
* The subject is an interpreter, a plugin host, a CLI with subcommands, a web
  framework, a serializer registry, an ORM, or anything with a `register`.
* A coverage/mutation/scope report pools regions and nobody has asked whether
  each region has a caller **at the level its callers live at**.

## Steps

1. **Name the level the tool reads.** Usually: identifiers in one language's
   AST. Write it down. Everything below is about the gap between that and
   where calls really originate.

2. **List the dispatch mechanisms in the subject** before reading any
   verdict: decorators, registration functions, `getattr`/`setattr` with a
   constructed name, `__all__`, entry-point manifests, config or route
   strings, template names, serialized workflows, and the guest language if
   the subject is an interpreter. Each one is a level the tool is blind to.

3. **Treat a same-shape family as a dispatch until proved otherwise.** Do not
   audit the members one at a time; find the thing that enumerates them.

4. **Fix the instrument at its own level first, conservatively.** A decorated
   def is referenced. Attribute the decorator reference to the ENCLOSING
   scope, not to the def it sits on — a builtin registered inside a factory
   is live exactly when the factory is, and that is a true statement rather
   than a permissive one. Keep a SHORT inert list (`staticmethod`,
   `classmethod`, `property`, `overload`, `setter`, `wraps`): widening it to
   "any decorator" makes every method unfalsifiably live and the detector
   stops detecting.

5. **State the failure direction and honour it.** An orphan claim is strong,
   so every ambiguity resolves toward `live`. A rule that can only ADD
   liveness is safe to add; one that can remove it needs a proof.

6. **Now re-ask the question at the level that matters.** If the call sites
   are in another language, parse that language with its own parser. Do not
   grep — see step 8.

7. **Keep the populations apart.** "Used by something we ship" and "used only
   by the tests" are different verdicts with different consequences, and
   pooling them is the same error one level down. A third verdict, "used by
   nothing at all", is the only one that is actually dead surface.

8. **Resolve shadowing, and report the naive count beside it.** A local
   binding with a builtin's name makes later calls not-builtin-calls; the
   difference between the grep answer and the resolved answer is a
   measurement of how wrong grep would have been. It can only ever go one
   way — shadowing removes uses, never adds them — which is a checkable
   invariant, so check it.

9. **Separate an instrument failure from a subject failure, at the boundary
   where they are still distinguishable.** A census that catches every
   exception and files it under "the corpus could not be read" will report
   its own bugs as facts about the subject. Round 504 shipped exactly that
   for one run: a renamed method made all 23 readable example programs come
   back `UNPARSEABLE`, every count silently dropped, and nothing turned red.
   Give the two failures different names, print the instrument's own with a
   loud marker, and REFUSE to publish a verdict — or write a ledger — while
   any is outstanding.

10. **Land the result as a ratchet, not a paragraph.** "0 unused builtins" is
    a fact that expires the next time someone adds one. A pinned ledger plus
    a `--strict` verb turns the next regression into a red instead of a
    re-investigation.

## Pitfalls

* **Fixing the instrument and stopping.** After the decorator fix all 37
  builtins read `live` and the report was useless in a new way. A verdict
  that is the same for every member of a surface has zero discriminating
  power; that is the moment to change levels, not to declare victory.
* **Believing the split as well as the verdict.** It is tempting to read
  `test_only` as "less used than the `unreferenced` ones". Here it meant the
  opposite of nothing — it meant a test imported that internal by name.
* **Grep as the cross-level answer.** Guest-language call sites live inside
  string literals in test files, inside `.lang` files, inside templates. A
  name match cannot resolve shadowing, cannot tell a field access from a
  call, and cannot tell a comment from code.
* **Counting a comment or a docstring as a reference.** In the measured case
  the ONLY non-test mention of a dead function was a comment asserting it was
  live. Collect them, report them, never let them confer reachability.
* **Recursive descent over a corpus you did not write.** A visitor that
  recurses per AST node dies on a 3000-term operator chain that the
  interpreter itself runs fine. Walk the expression spine iteratively;
  recurse only on scope-opening nodes, whose depth is bounded by how the
  program is written.
* **Deleting on the first verdict.** Every fix in this skill only ADDS
  liveness. Nothing here ever proves code dead; it narrows the candidates.

## Verification

The instrument must (a) call a decorated def live, (b) not call
`@staticmethod` alone live, (c) attribute a decorator to the enclosing scope,
(d) resolve shadowing, and (e) distinguish its own failures from the
corpus's.

```sh
python3 -m pytest harness/tests/test_swe_scopecall.py -q
python3 -m pytest languages/whence/tests/test_builtinlive.py -q -c languages/whence/pytest.ini
```

Expected: all pass, including
`test_a_registering_decorator_makes_its_def_live`,
`test_a_decorated_def_inside_a_factory_is_live_iff_the_factory_is`,
`test_staticmethod_and_property_confer_no_liveness_of_their_own`,
`test_a_decorator_reference_is_never_a_self_reference`,
`test_a_bug_in_the_walker_is_a_walk_failure_not_a_corpus_defect` and
`test_the_census_refuses_to_publish_when_the_walker_failed`.

On the live corpus, the two levels, in order:

```sh
python3 harness/swe/scopecall.py audit --rel languages/whence/whence/interp.py \
        --search languages/whence
python3 languages/whence/builtinlive.py --strict
```

Expected: the first reports `0 test_only, 0 unreferenced` — the Python-level
question, now answered correctly and uninformatively. The second exits **0**
while every registered builtin's verdict matches the pinned ledger, and **1**
the moment one moves — including the case this exists for, a builtin added to
the registry that no shipped program calls.
