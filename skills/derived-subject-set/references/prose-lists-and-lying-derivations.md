# An empty derived set (round 395), prose lists (round 482), and two ways a derivation lies

Split out of `../SKILL.md` in round 488 for the 500-line body cap. Read this
when the "list" you are chasing is a sentence rather than a literal, when a
derivation returns fewer members than you expect, or when the rule set you
are auditing against came from a single known failure.

## The list is often in PROSE, and prose is where it is least checkable (round 482)

Every worked example above has the literal in *code*, where at least a
future reader is looking at an assertion. The most consequential ones are
not in code at all.

Round 476 of this program fixed one class's `__repr__`, wrote the general
rule into its spec registry, and closed with a next-step naming the
candidates for the sweep:

> The unrendered candidates a caller can reach: `Explanation`, `Closure`,
> `Builtin`, `WList`, `PMap`, `Record`, `Miss`, `Guess`. `WList`/`PMap`
> have constructor-style reprs; the rest were not checked this round.
> **Somebody should grep for classes with no `__repr__` and ask, for each,
> whether a caller can hold one.**

Best conditions a list ever gets: written by the round that found the
defect, one round after touching the code. Five rounds carried it. Run at
last by CRAWLING the object graph — 19 classes reachable, **11 in
violation against the remembered 8** — it was wrong in *both* directions:

- the two members it waved through as already fine (`WList`, `PMap`) were
  the two largest violations in the tree, at 156,787 and 22,986 characters;
- nine violators were on no list at all, two of them structurally
  un-listable by the proposed method: the engine class (a list of *value*
  classes cannot contain the object the caller constructs first) and a
  subclass that INHERITED a wrong repr (a grep for "classes with no
  `__repr__`" skips it, because it has one).

**A prose list is a measurement nobody took, and it is read as one.** The
tells: it lives in a document a future change uses as its work order; it
was written by the person who had just finished looking, which is exactly
when a list feels complete; it carries a judgement per member ("these two
are fine"), so acting on it inherits someone's verdict without their
evidence; and the METHOD named beside it is itself a filter — "grep for
classes with no `__repr__`" cannot see an inherited one. **When a
next-step names a method, audit that method's blind spots first**, because
everything it cannot see will be reported as absent.

The move is step 3 with a wider notion of artefact: crawl the live object
graph, walk the AST, query the schema — derive from the thing the claim is
about, and pin the derived SET (not its count) so a silent shrink fails.

### The derivation can silently return a SUBSET

Step 5's cross-check exists for this, and here are two concrete ways a
crawl shrinks with no error at all. Both were live in the same instrument
on the same day, and both made it report a clean sweep.

1. **`id()` is a key only for objects you are holding.** A `seen = set()`
   of `id()`s is correct only while every visited object stays alive. A
   lazily-built property —

   ```python
   @property
   def inputs(self):
       ins = self._ins
       return ins if type(ins) is tuple else (ins,)     # a FRESH tuple
   ```

   — makes the walk allocate, record the id, drop the object, and then skip
   a live object CPython hands the freed address to. Cost: one class,
   silently. Fix: retain every visited object (`keep.append(obj)`), which
   is not bookkeeping, it is correctness.

2. **A budget cap turns "did not finish" into "found nothing more".** Once
   the retention bug was fixed, the same crawl walked out of the subject
   graph through a public attribute into the host's module `__dict__`s and
   ran to its 60,000-step limit — reporting **13 of 19** classes and no
   violations for the six it never reached. Bound the walk by TYPE (descend
   the subject's own classes and plain containers, nothing else), and
   report the budget state as data:

   ```python
   return found, {"steps": steps, "exhausted": bool(queue), "limit": limit}
   ```

   then assert `not exhausted` in the test. A crawl that ran out is a
   different answer from a crawl that finished, and only one of them is a
   result.

Neither was found by reasoning about the crawl; both were found by a count
that looked wrong — 18 where 19 was expected, then 13 where 19 was. That
is the argument for pinning the derived SET rather than only asserting the
property over it: the property held, vacuously, over whatever survived.

### A rule set derived from one known failure finds that failure again

A related trap, same round. The sweep's rules were written from the defect
that prompted it (a heap address in a repr), giving R1 no-host-leak, R2
bounded, R3 deterministic. They found nine instances of R1 — and passed a
class whose inherited repr introduced it under the WRONG CLASS NAME and
dropped its only distinguishing field. That became R4, and R4 exists only
because the sweep ran.

Budget for the rule the sweep adds after it first runs, and treat the
first run's surprises as rule candidates rather than one-off fixes. A rule
set that gains nothing on first contact with the full population is
evidence the population was not enumerated.



## A derived set can go EMPTY, and that is worse than stale (round 395)

Deriving the set is necessary and not sufficient. The derivation reads an
**artefact**, and it is really reading a *proxy for a fact*; when the proxy's
meaning changes without the fact changing, the set does not go stale, it goes
**empty**.

Worked example. `curecheck.field_programs()` selected "the programs a separate
system leaves in `examples/`" with

```python
subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "examples"])
```

— untracked status, derived from git, with an explicit argument in its own
docstring for why a hand-written list would be worse. Three rounds later a
`git add -A` sweep tracked all fourteen files. Not one byte of any file
changed. The selector returned `[]`.

What that costs, and why it is worse than a stale list:

| | stale set | empty set |
|---|---|---|
| `assert all(P(x) for x in S)` | fails on the item it missed | **vacuously true** |
| `assert len(S) == N` | fails, naming the extra item | fails, naming `0 == N` |
| `S["known_member"]` | works | `KeyError`, naming the member not the cause |

Two of the four tests that broke here were the vacuous kind's siblings and
two were the loud kind, and **none of the four failure messages contained the
word "empty" or the name of the selector.**

The moves:

1. **Name the fact, then ask whether the artefact is the fact or a proxy for
   it.** "Written by another system" is the fact; "untracked" is a proxy, and
   proxies are what other people's commits change.
2. **Prefer a declaration the repo already has over a fresh proxy.** Here a
   frozen census (`state/whence/round-384/field-names.json`) had listed the
   fourteen names for eleven rounds and a *different* guard already trusted
   it. Reading it is not "a hand-written list": it is the existing
   declaration, read instead of re-derived from something weaker.
3. **Keep the live derivation as a REPORT, not as the source.** The original
   argument — "if the gateway adds a program tomorrow this picks it up" — is
   real and worth keeping. It became `field_corpus_drift()`, which returns
   `(undeclared, missing)`. The property survives; the failure mode does not.
4. **Assert non-emptiness at the derivation, not at the assertion sites.** A
   selector that can legitimately return zero should say so; one that cannot
   should raise there, where the message can name the selector.

