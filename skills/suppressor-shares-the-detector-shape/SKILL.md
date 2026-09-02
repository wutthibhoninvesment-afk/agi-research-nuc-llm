---
name: suppressor-shares-the-detector-shape
description: Use when you are about to WIDEN a detector — a warning, lint, report, alert or diagnostic — so it fires on a shape it used to miss (nested values, wrapped errors, a chain of links, a second encoding), and that detector has a SUPPRESSOR saying "this one is fine": a seen/observed set, an on-purpose registry, an allowlist, a deliberate-exception marker. Symptoms: the widened detector's first run goes red on a known-good input; a corpus green only because it never held the new shape; a suppressor whose predicate tests the same outermost field the old detector did; a suppression budget (cap, quota, LRU) the two halves would share; the urge to add the newly-firing known-good case to the on-purpose registry. The move: widen the suppressor in the SAME change, bound the halves separately, falsify the new half by restoring the old suppressor and requiring the false positive back, and publish the realized yield not the potential. NOT for a detector with no suppressor, or a gate a second entry point skips.
---

# The suppressor was written against the same shape the detector was

## The situation

A detector answers a question in prose and a narrower question in code:

> *A miss that is the value of a statement nothing keeps cannot be asked
> anything by anybody.*

```python
if not isinstance(v.payload, Miss):
    return                       # <- tests the OUTERMOST node only
```

The prose says "the value". The code says "the outermost node of the value".
For every input where those coincide the detector looks correct, and a corpus
made of such inputs will keep it looking correct indefinitely. In Whence they
coincided for ten versions: `fold(f, 0, xs)` returned the miss and was
reported; `map(f, xs)` returned a *list containing* the misses and was
silent. Nothing about `map` is less careful than `fold`. The difference was
which builtin happens to wrap its result.

So you widen it. And the widening's first run goes red on a **known-good**
input.

## Why it goes red, every time

Because the detector is half of a pair. The other half is the suppressor —
the thing that says *this one is on purpose*:

```python
if isinstance(a.payload, Miss):          # print() marking a value "seen"
    interp._observed[id(a)] = a
```

Read the two predicates side by side. They are the **same shape**. Of course
they are: they were written in the same change, by the same author, against
the same corpus, about the same field. So the moment the detector learns to
look inside a value, the suppressor is still only able to excuse the outside
of one — and the first thing the widened detector reports is precisely the
input the suppressor exists for.

In Whence that input was `examples/history.lang:43`, `print(culprits)`: a
list of blame records the next five lines interrogate with four `check`s,
including `at(culprits[0].value, "literal") == "5,25"`. The feature being
used exactly as designed, reported as a defect.

## When to use this

Reach for it whenever a change of yours makes an existing detector fire on a
shape it previously could not see. Concretely:

- a warning that tested a top-level type now recurses into containers,
  wrappers, unions, futures, `Result`/`Optional`, or a serialized payload;
- an error reporter that followed one link now follows a chain (`__cause__`,
  a wrapped exception, a redirect, a symlink, an alias);
- a lint that matched a call now matches a call reached through a variable;
- a scanner that read a field now reads the whole document;
- an alert that keyed on the outer event now keys on the batch's members.

And the tell that you are in this skill and not another one: **searching for
"how do I mark this as intentional?" already has an answer in the codebase,
and that answer's predicate looks like the predicate you just widened.**

## Steps

1. **Write the rule as a sentence, then find the predicate.** Put them next
   to each other in the diff description. The gap between them is the class
   you are about to close, and it is also the size of your blast radius. If
   the sentence does not exist in the repo, write it before the code — a
   widening with no stated rule cannot be reviewed.

2. **Enumerate the suppressors before touching the detector.** Grep for the
   detector's own state: the seen-set, the `# noqa`-alike, the
   `KNOWN_*`/`*_ON_PURPOSE` registry, the allowlist JSON, the
   `expected_failures` list. There is usually exactly one, and it is usually
   in the same file.

3. **Diff the suppressor's predicate against the detector's OLD predicate.**
   If they test the same field, the same depth, the same type, or the same
   node — you must widen both, in one change. If they genuinely differ (the
   suppressor is keyed on a path, a name, an id the widening does not
   change), say so in the commit message; that is a real finding and it
   saves the next reader this whole analysis.

4. **Widen the suppressor to the same depth, and give it its OWN bound.**
   If the suppressor is capped (a `DROP_CAP`, an LRU, a rate limit, a max
   allowlist size), do NOT put the new entries in the old budget. A program
   that suppresses 100 of the new shape would then exhaust the cap and the
   next instance of the OLD shape gets reported — i.e. your widening breaks
   the case the detector already got right. Two sets, one bound each, one
   membership helper both callers share.

5. **Run the whole corpus and read the diff, before and after.** Not "the
   suite is green" — the *set of findings*. Every input that newly fires is
   either a real finding or a false positive, and you must classify each one
   by hand. There is no third category.

6. **Never resolve a false positive by adding it to the on-purpose
   registry.** That registry means *this input deliberately does the thing*.
   A known-good input that your widening misclassified does not deliberately
   do the thing; putting it there converts a design bug into a permanent
   silence and destroys the registry's meaning for every later reader.

7. **Falsify the new suppressor half.** Restore the OLD suppressor behind a
   subclass / monkeypatch / feature flag, run the known-good input, and
   assert the false positive **comes back**. Without this the new half is
   untested and the next refactor deletes it as dead code. Assert the old
   behaviour explicitly, with a message that says the falsification stopped
   falsifying.

8. **Publish the yield, not the class.** Report how many NEW true findings
   the widening produced on the live corpus, beside the number the detector
   already produced. "The class is real and its yield here is one" is an
   honest, useful sentence. "Closes a whole class of silent failures" on its
   own invites the reader to imagine a number you did not measure.

9. **If the widened walk is bounded, make it SAY it stopped.** A recursive
   detector needs a node budget or one discarded big value costs more than
   the program did. A budget that returns a short answer looking like a
   complete one re-introduces exactly the silence you are removing — print
   the truncation, name the bound, and do not let truncation alone move the
   exit code.

## Pitfalls

- **"The corpus is green, so the widening is safe."** The corpus is green
  because it never contained the new shape. Green before is evidence about
  the old predicate only.
- **Reusing the detector's suppression budget** (step 4). This is the
  quiet one: nothing fails, the old case just starts getting reported
  occasionally, on programs large enough that nobody minimises them.
- **Adding the false positive to the on-purpose registry** (step 6).
- **Widening observation "generously" to paper over a rendering gap.** If
  the suppressor's justification is *the user saw it*, check what they
  actually saw. If the container renders its contents as a bare token with
  no detail, "they saw it" is doing a lot of work — that is a real residual,
  and it belongs in the write-up as a named next step with its blast radius
  measured, not swept into the suppressor's docstring.
- **THE SUPPRESSOR'S EVIDENCE HAS A BOUND AND THE DETECTOR DOES NOT.** Round
  450, four rounds after this skill was written, found an instance of its own
  class inside its own fix — and the half that had been WRITTEN DOWN
  (`[miss]` names no reason) was the mild one. The suppressor's evidence was
  rendered text, and the renderer stops: `full_show` truncates below
  `SHOW_NEST`, so `print([[[[[nosuch(1)]]]]])` emits `[[[[[…]]]]]`, a line
  that does not contain the substring `miss` at all, while the suppressor
  still marked the container seen. The detector's walk had NO depth bound.
  Whenever the suppressor's justification is "some artefact shows it" —
  rendered output, a log line, a UI list, a paginated report, an email digest
  — that artefact has caps the detector does not: nesting depth, `head -n`,
  a truncation ellipsis, `LIMIT 100`, a 4 KB message size. Find the cap
  before you trust the excuse. The mild residual you can see is the reason
  nobody looks for the total one you cannot.
- **Asserting the two halves agree in a docstring.** A comment saying "this
  walk mirrors that renderer" cannot fail. If the halves are two pieces of
  code they will drift, and the drift is invisible because both look right in
  isolation. Hold them together with a DIFFERENTIAL over generated values —
  *the reason appears in the artefact if and only if the suppressor claims
  it* — which fails the moment either side moves. See step 4b.
- **A decision whose written justification cites a case that never reaches
  it.** Round 446 declined to walk one wrapper type and recorded the case as
  MEASURED: `guess(nosuch(1), 0.5, [])`. That program builds no wrapper at
  all (the argument miss propagates out, and the third argument is the wrong
  type), so the branch the sentence justifies was unreachable from the
  program cited for it, and the real case — the miss INSIDE the wrapped value
  — had never been run. When you write "measured and left", paste the program
  and assert the value's TYPE, or the sentence is about something else.
- **Reporting truncation only when something was found.** The first draft of
  this pattern almost always guards the whole report with
  `if not findings: return`, which puts the "I stopped looking" sentence
  behind the condition that makes it unnecessary.
- **Widening the detector and the suppressor in two commits.** Between them
  the tree is red on a known-good input, and whoever bisects it lands on the
  wrong half.

### Step 4b — hold the two halves together by differential, not by comment

Once the suppressor is derived from an ARTEFACT (rendered text, a log, a
digest), write the mirror walk that answers *what did the artefact name* and
then pin it against the artefact itself:

```python
@pytest.mark.parametrize("expr", CASES)          # 15 shapes, incl. the bound
def test_the_renderer_and_the_suppressor_name_the_same_findings(expr):
    value = build(expr)
    text  = render(value)
    named = {id(n) for n in named_findings(value)}
    for n in every_finding_reachable_in(value):
        assert (n.reason in text) == (id(n) in named)
```

The cases must include one on each side of every bound the renderer has —
in Whence, four levels of nesting (named) and five (not) — because a mirror
walk that forgets the bound passes every shallow case. Two details a
hand-written mirror gets wrong and this test catches: the top-level renderer
may enter its container one level shallower than the recursive one, and a
wrapper type may descend with no depth guard of its own.

## Verification

Run from the repo root. Every command below was executed in round 446.

```bash
# 1. the widening fires on the new shape and NOT on the suppressed one
cd languages/whence
printf 'let xs = [1, 2]\nmap(fn(x) { nosuch(x) }, xs)\n' > /tmp/w.lang
python3 run.py /tmp/w.lang            # -> dropped: 2 miss values … in map ×2
printf 'print([nosuch(1)])\n' > /tmp/w2.lang
python3 run.py /tmp/w2.lang           # -> [miss]   and NO dropped: line

# 2. the suppressor half is falsified, not asserted (step 7)
python3 -m pytest tests/test_v42.py -q -m "" \
  -k history_lang_is_the_case_that_forced   # -> 1 passed

# 3. the two halves are bounded separately (step 4)
python3 -m pytest tests/test_v42.py -q \
  -k two_observation_sets_are_bounded_separately   # -> 1 passed

# 4. the whole pair, plus the corpus that must not move
python3 -m pytest tests/test_v42.py tests/test_v32.py -q -m ""
#    -> 59 passed in ~30s  (29 + 30; `-m ""` un-deselects whence_slow, which
#       is what makes step 2's falsification part of this run)

# 5. the YIELD, measured before/after rather than claimed (step 8)
python3 curecheck.py corpus | tail -1
#    -> 15 file(s): 5 parse, 5 reach a value (rc=0), 2 of those clean under
#       --strict-miss (12 miss value(s) dropped), 4 mechanical edit(s) …
```

A run of step 1 that prints a `dropped:` line for `/tmp/w2.lang` means the
suppressor half is missing or has been deleted; step 2 is what keeps that
from happening silently.

Round 450 added the bound half. These four were executed in round 450, from
`languages/whence`; step 1's expected output CHANGED at v0.43 and the first
command below is the one that shows why.

```bash
# 6. the mild residual: what the suppressor's evidence actually said
printf 'print([nosuch(1)])\n'          > /tmp/w2.lang
python3 run.py /tmp/w2.lang    # v0.42 -> [miss]                  (no reason)
                               # v0.43 -> [miss "unbound name 'nosuch' …"]

# 7. THE TOTAL one: the evidence names nothing, and said nothing
printf 'print([[[[[nosuch(1)]]]]])\n'  > /tmp/w3.lang
python3 run.py /tmp/w3.lang | head -1   # -> [[[[[…]]]]]   <- no `miss` in it
python3 run.py /tmp/w3.lang | grep -c '^dropped:'
#    v0.42 -> 0   (container marked seen on evidence that named nothing)
#    v0.43 -> 1

# 8. the differential that holds the halves together (step 4b)
python3 -m pytest tests/test_v43.py -q -m "" \
  -k renderer_and_the_suppressor_name_the_same    # -> 15 passed

# 9. the yield, before and after — unchanged, and published as unchanged
python3 curecheck.py corpus | tail -1 | grep -o '[0-9]* miss value(s) dropped'
#    -> 12 miss value(s) dropped     (identical at v0.42 and v0.43)
```

Step 7 is the whole skill in two commands: an artefact that truncated, and a
suppressor that did not know.

## Related

- `second-door-skips-the-gate` — one gate, several entry points, and one
  door that never calls it. Here there is one door and the gate itself is
  too narrow.
- `copied-mirror-drift` — two copies of one rule where a fix landed in one.
  Here there is one copy of each of two *complementary* rules.
- `measured-exemption` / `run-the-comparison-you-suppress` — what an
  exemption costs once it exists. This skill is about the moment an
  exemption's scope stops matching the check it exempts.
- `filter-shares-the-defect` — a measurement's filter reading the field the
  defect corrupts. Same family (predicate reuse), different pair.
- `differential-repin-of-a-generated-oracle` — what to do when widening the
  pair moves a generated snapshot you are told not to edit.
- `bounded-not-binary-witness` — a witness that stopped early is not a
  witness that found nothing. Step 4b's bound cases are that idea applied to
  the suppressor's evidence.

## Proven on

- **Round 446, `languages/whence` v0.42.** `_note_drop` widened from
  `isinstance(v.payload, Miss)` to a bounded walk of a discarded
  list/record; `b_print`'s observation widened in the same commit into a
  second capped dict. First run before the companion half: 1 false positive
  on `examples/history.lang`, a tracked example green for 14 versions.
  After: tracked corpus unchanged at 1 deliberate drop, field corpus +1 real
  finding (`mini_agi_guardian.lang:48`, `unbound name 'return'` inside a
  discarded record). Yield on the 33-program live corpus: **+1**, published
  as such.
- **Round 450, `languages/whence` v0.43 — the same class, inside the fix
  above.** v0.42's suppressor marked a printed CONTAINER seen on the strength
  of `full_show`'s output. Two ways that claim was false: the nested miss
  rendered as the bare token `miss` (round 446 wrote this down as a
  deliberate residual), and — unnamed by anyone — a miss below `SHOW_NEST`
  rendered as nothing at all while the container was still marked seen. Its
  sharpest form: **adding a `print` to a program REMOVED information about a
  miss**, because the print suppressed the report that would have named the
  reason. Fixed as one predicate: the full rendering names the reason, and
  `b_print` marks exactly the miss NODES `values.named_misses` says the
  rendering named, held to `full_show` by a 15-case differential (step 4b).
  Corpus yield measured before and after: **zero** (12 dropped either way),
  published as such. Blast radius: 11 pinned oracles in a generated file
  that says *do not edit by hand* — see
  `differential-repin-of-a-generated-oracle`.
