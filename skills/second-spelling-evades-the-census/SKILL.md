---
name: second-spelling-evades-the-census
description: Use when a static census of source call sites reports a capability as undemonstrated, under-used or test-only and someone is about to close the gap by writing the missing artefact. The failure is a SECOND SPELLING; the capability also has a syntactic form -- an annotation, a decorator, an operator, a framework route, a desugaring -- the census cannot see, so the number is a fact about the counter, not the system. Symptoms; one identifier with a wildly outlying use count; a feature everyone knows is used showing 0-2 uses; docs describing a desugaring in the present tense inside a section named for an OLD version; a gap that survives every attempt to reproduce it by reading. The move is to name the census's exact predicate, enumerate the other spellings, follow each to the runtime function it reaches, then measure at the shared DISPATCH point with each spelling counted separately and never merged. NOT named-is-not-invoked, NOT liveness-is-a-claim-about-a-level.
---

# The census counts one spelling; the compiler chose the other

A source census is honest and cheap: parse every program, walk the AST,
count the call sites of name `N`. It answers *how often is `N` written*.

Readers hear *how often is `N` used*. Those are the same number only while
`N` has exactly one spelling. The moment a capability also has a **syntactic
form** — and mature systems accumulate them — the census stops being able to
see the majority of the traffic, and it reports the shortfall as a coverage
gap in the *corpus* rather than a blind spot in *itself*.

```
The iron law:  a count of call sites is a count of ONE SPELLING.
               Before you close the gap it reports, find the others
               and find out what each one actually executes.
```

The trap has a second jaw. Docs are usually written when the first spelling
is the only one, and the sentence that describes the routing is rarely
revisited when the routing changes — so the doc *confirms* the wrong model,
in the present tense, and the investigation stops there.


## When to use — trigger conditions

Any ONE of these is enough:

- A census, coverage report or usage sweep names a capability as
  undemonstrated / unused / test-only, and you are about to write the
  artefact it asks for.
- One identifier's count is an order of magnitude off what you expect, and
  the surrounding counts look sane.
- The capability you are counting ALSO has a syntactic form: a type
  annotation, a decorator, an operator, an implicit coercion, a route or
  handler registration, a macro, anything the parser desugars or lowers.
- A doc sentence explains the routing in the present tense and sits in a
  section named for a version older than the current one.
- You are about to add a runtime counter and its reset path rebinds a
  collection the hooks close over.

Do NOT reach for this when the question is whether a whole FILE or COMMAND
is reached (`named-is-not-invoked`), or which LEVEL a dispatch happens at
(`liveness-is-a-claim-about-a-level`). Here the level is settled and the
question is which of two syntaxes carries the traffic.

## The measured instance (rounds 504-506)

A language census counted builtin call sites across a language's own example
programs. One builtin stood out by an order of magnitude:

```
typed        1 use in examples/,  47 in the test corpus
             -- the widest ratio of any of the 37 builtins
```

`typed(value, spec, label)` is the type-contract builtin. The next round was
told to *either write an example demonstrating it, or say why not*. The spec
appeared to settle which:

> `fn f(a: num, b: Point) { … }` **desugars, in the parser**, to one leading
> `let a = typed(a, "num", "parameter 'a' of f")` per annotated parameter

Read as current, that says the annotation IS a `typed` call — so the census
was undercounting and the fix was a doc note, not an example. That was the
hypothesis this instance was banked with, and it was wrong.

**Four versions earlier the routing had changed.** The parser now stores the
contract on the function node and a host function applies it; the builtin is
not on the path at all. The doc bullet sat inside the section named for the
OLD version, where it is history, and had never been marked past-tense — the
neighbouring bullets in the same file all had such markers.

So the census's 1 was correct, the spec was misleading, and the real state of
affairs was a third thing neither had said: the *feature* was demonstrated
(three example programs applied 100,021 contracts) and the *builtin* was not.

### What settled it: measure at the dispatch point

Wrap the one attribute every call path reaches through and run the corpus.

| level | question | instrument |
|---|---|---|
| source | is `N` **written**? | AST census |
| **runtime** | is `N` **invoked**? | counter at the shared dispatch slot |

```
builtin      run     writ     gap   verdict
get        99245       30  +99215   run_and_written
len        83734      180  +83554   run_and_written
...
typed          0        1      -1   WRITTEN_NEVER_RUN     <-- the only one
```

**One of 37.** Every other builtin written in an example is a builtin that
example runs; `typed` was the single exception, and the single written site
turned out to sit behind a guard (`if missed(value) or …`) that no shipped
program ever reached. The gap was real, it was one line wide, and it was not
where the ratio pointed.

Counting at the dispatch slot also buys the thing the AST cannot express: a
builtin passed as a **value** (`map(str, xs)`) is three invocations through
zero call sites naming it.

## Steps

1. **Write down the census's predicate as a sentence with a verb.** Not "uses
   of `N`" — "*call sites spelled `N` in successfully-parsed source*". If you
   cannot write it that precisely, read the counter's loop until you can.
2. **Enumerate the other spellings of the same capability.** Annotations and
   type syntax; decorators; operators and coercions; framework routing
   (routes, DI, signals, middleware); anything the parser or compiler
   *desugars*, *lowers*, or *stores on a node*.
3. **Follow each spelling to the function it actually reaches.** Grep the
   parser/compiler for the syntactic form, not the runtime name, and read
   forward. `grep -n "param_specs\|_check_contract" parser.py interp.py`
   settled the instance above in one call.
4. **Date every doc sentence you rely on.** If it lives in a section named
   for a version, treat it as history until the code agrees. A present-tense
   verb in a historical section is the highest-yield defect in this family —
   correct it in place, with the marker style the file already uses.
5. **Measure at the shared dispatch point.** Find the single slot all paths
   reach (a dispatch table entry, a `__call__`, a registry's function
   attribute), wrap it, run the corpus, restore it in a `finally`.
6. **Count each spelling separately and publish both.** Never fold spelling B
   into spelling A's number.
7. **Then decide the original question** — with the gap now stated in terms
   of the thing that is actually missing.

## Pitfalls

- **Merging the spellings to make the gap go away.** "Annotations count as
  `typed` uses" answers the question by redefining its noun. If the two
  spellings reach different code, they are different coverage.
- **Believing the doc over the parser.** The doc was true once. The parser is
  true now.
- **A counting instrument that resets by REBINDING.** This instance shipped,
  for one run, a `reset_program` doing `self.calls = {}` where the installed
  wrappers close over the *original* dict. Every wrapper then wrote somewhere
  nobody read and the census reported **zero invocations for all 37
  builtins** while the corpus ran perfectly and 515,728 contract entries were
  counted by a sibling field. `.clear()`, not `= {}`.
- **An all-zero census reads exactly like a real finding.** "37 of 37 never
  run" is *coherent*, internally consistent, and publishable. No consistency
  assertion catches it. Pin a **hand-counted non-zero** input; see below.
- **Leaking the wrapper.** Dispatch tables are usually process globals shared
  by every instance. Restore in `__exit__`/`finally` or the next thing in the
  process runs instrumented.
- **Recomputing derived flags when you wrap.** If the object caches something
  about the function (`is_gen`, arity, a signature), wrapping must not
  disturb it.
- **Assuming the outlier ratio points at the defect.** Here it pointed at a
  doc error; the actual gap was a guarded branch with no reaching program.

## Verification

Run these; each should print the quoted shape.

1. The two levels, side by side, over the real corpus:

   ```
   cd languages/whence && python3 builtinlive.py --no-tests | tail -3
   cd languages/whence && python3 runlive.py | tail -6
   ```
   The second prints `the two levels disagree on 0 of 37 builtin(s)` and
   `annotation contracts: … and NONE of them is a 'typed' call` — the two
   spellings, counted separately, both non-zero.

2. The hand-counted non-zero pin, which is what makes every other number in
   the census trustworthy:

   ```
   cd languages/whence && python3 -m pytest tests/test_runlive.py -c pytest.ini \
       -k "hand_counted or reset_between or as_a_VALUE" -q
   ```
   `3 passed`. Delete the `.clear()` in `runlive.Counter.reset_program` and
   re-run: `test_the_counts_reset_between_programs` fails. That is the
   falsifier for the all-zero census.

3. The second spelling really does bypass the builtin:

   ```
   cd languages/whence && python3 -m pytest tests/test_runlive.py -c pytest.ini \
       -k "annotation_invokes_typed_zero or builtin_spelling" -q
   ```
   `2 passed` — an annotated program invokes `typed` 0 times with
   `contract_checks >= 3`; the same contract written as a call invokes it
   once with `contract_checks == 0`.

4. The doc correction is present and dated:

   ```
   grep -n "Stale-note correction (round 506)" languages/whence/SPEC.md
   ```
