---
name: sanitiser-outgrows-its-noise
description: Use when a comparison harness normalises strings before comparing them — stripping timestamps, pids, line numbers, temp paths, request ids, durations, hostnames, ANSI codes — and the thing being compared has just started carrying a value of that same shape as REAL DATA. Symptoms: a regex like `\(line \d+\)` or `\d{4}-\d\d-\d\d` used with a global `sub`; a "strip the trailing noise" helper that scans back from the last delimiter; the same normaliser copy-pasted into several test files; a newly added field that reads correct by hand but the differential calls it a mismatch — or, worse, calls it a match. Covers finding every copy of the normaliser, proving which ones over-match, anchoring them to strip exactly one occurrence, and the case where the over-match produces a GREEN test rather than a red one. NOT for a value the corpus cannot distinguish from a constant (would-a-constant-have-passed) or a filter that excludes the interesting subjects (filter-shares-the-defect).
---

# The sanitiser outgrows its noise

A differential compares two strings that both contain incidental junk —
the pid, the timestamp, the temp path, the implementation's own line
number. So the harness strips the junk before comparing. That normaliser
is written once, against the junk that exists on the day it is written,
and then it is **never revisited**, because it is infrastructure and
infrastructure is where nobody looks.

Then the thing under test starts carrying a value of the same *shape* as
the junk — as real, load-bearing data. The normaliser cannot tell them
apart, because it never could: it matches a shape, and the shape is now
ambiguous.

Two failure modes, and the second is the dangerous one:

* **Red** — the normaliser deletes the new fact from one side only, and
  the harness reports a disagreement that does not exist. Annoying,
  self-announcing, fixed in ten minutes.
* **Green** — the normaliser deletes the new fact from *both* sides, or
  deletes it before a CLASSIFIER runs, and a real, unexamined difference
  is filed into a bucket labelled "understood". Nothing goes red. The test
  whose entire job is to surface unclassified differences reports that
  there are none.

Proven on `languages/whence` (round 404). A parser message gained a
trailing `(line N)` naming where a name was first declared. The test suite
defined

    LINE_SUFFIX = re.compile(r" \(line \d+\)")

**ten times across eight files**, nine of the ten unanchored, every
unanchored copy used with a global `.sub("", …)`. Each deleted *every* parenthesised line
number in a message, not just the implementation coordinate it was written
for. The raw guest error

    shape 'P' is already declared in this block (line 1) at line 2, col 7 (line 997)

normalised to `shape 'P' is already declared in this block` — the fact the
change added, gone, and the guest reported as disagreeing with a host it
agreed with byte for byte. A tenth copy in the same suite was already `$`-anchored and had been
pinned by a test one round earlier; that pin was about one of ten. **The
class is the pattern, not the file.**

And the first count was **seven**, not ten, because it came from grepping
the identifier `LINE_SUFFIX`. Two copies spelled the identical pattern
`LINE_RE` and a name-grep cannot see them. They were found by a 150-line
script that walks each module's AST for `re.compile` and decides
membership by RUNNING each pattern against the value's rendered form — so
two spellings of one hazard are one row, and a near-miss variant that
cannot reach the message is correctly not a row at all. One of the two was
**dead code**, which is worse than a live one: nobody will notice it is
wrong until they reach for it.

The same round found the green form. A helper that decided whether a
host/guest difference was "a host-only hint" scanned back from a trailing
`)` and called whatever it found a hint. A sentence ending `(line 3)` and
a sentence ending `(use a line break)` are the same six characters. Had it
not been guarded, a brand-new unclassified divergence would have been
filed as an already-understood one, `other` would have stayed `[]`, and
the census would have been green and wrong.

## When to use (triggers)

- You are adding a field, suffix, or clause to a message, record, or log
  line that a comparison harness normalises.
- The new value's *rendered shape* resembles something the harness strips:
  a number in parens, an ISO date, a `/tmp/...` path, a hex id, a
  duration, a `key=value` tail.
- You see `re.sub(pattern, "", s)` in a test helper — `sub` is global by
  default; the author almost always meant "the one at the end".
- A normaliser is defined in more than one file. Copies drift, and they
  drift in the direction of whichever file's corpus reached them.
- A differential's "everything else is understood" bucket is asserted
  `== []` and something new was just added upstream of the classifier.
- Somebody is about to say "the anchor is what saved us" about one copy.

**When NOT to use:** the corpus cannot tell a computed value from a
constant (`would-a-constant-have-passed`); the population being compared
was filtered by something that shares the defect
(`filter-shares-the-defect`); the message is not compared to anything at
all.

## Steps

1. **Write down the new value as it renders, in full, in context.** The
   whole raw string, both sides. Not the sentence you intend — the bytes
   the harness will see, position clause and implementation coordinate
   included. Most of this skill's work is done by looking at that string.

2. **Grep for the PATTERN, not for the test.** The normaliser's name is
   local; its regex is not. Search the *regex text*, escaped and
   unescaped, across the whole test tree:
   ```
   grep -rn 'line .d+' tests/ | grep -v Binary
   grep -rn 're\.compile' tests/ | grep -Ev '__pycache__'
   ```
   Count the copies before you fix any of them. In the whence round the
   count from the name-grep was seven; the real count was ten, in eight
   files, and the one already-fixed copy was the reason nobody had looked.
   **A grep for the identifier is not a grep for the pattern.** If the
   construct is worth a census, write the census as code (walk the AST for
   the constructor call, then decide membership by RUNNING each candidate
   against the real value) rather than as a grep — two spellings of one
   hazard must be one row.

3. **Prove the over-match, do not reason about it.** Feed the exact string
   from step 1 through each copy and print both results side by side:
   ```
   python3 -c "
   import re
   raw = '<the exact string>'
   for name, pat in [('unanchored', r' \(line \d+\)'), ('anchored', r' \(line \d+\)$')]:
       print(name, '->', repr(re.sub(pat, '', raw)))"
   ```
   A three-line script settles it. A reading of the regex does not — round
   402 read one correctly and generalised it to seven it had not read.

4. **Anchor to strip exactly one occurrence, and say why the anchor is
   safe.** `$` is right only if the junk is genuinely last. State the
   ordering fact that makes it so ("`miss` appends the raising line LAST,
   so the coordinate is the final token"), because that fact is what a
   future round will need to re-check. If the junk is *not* last, strip by
   position (`rsplit`, a captured index) rather than by shape.

5. **Ask what runs DOWNSTREAM of the normaliser.** A classifier, a bucket,
   a `== []` assertion. This is where the green failure lives. If a
   classifier decides "difference type" from string shape, hand it the new
   string and check the bucket it picks — by hand, once, before trusting
   any test.

6. **Prefer a representation the ambiguity cannot reach.** In the whence
   round, two censuses asked the same question — "is this message hinted?"
   One read the source AST for the hint-constructing call and was immune;
   one read the rendered string and was not. When you have the choice,
   classify from the structure, not from the render.

7. **Re-run every suite that owns a copy** — all of them, not just the one
   that went red. Anchoring is behaviour-preserving *only* if no corpus
   contained a non-final occurrence, and that is a measurement.

8. **Leave the full account in ONE copy and a pointer in the others.**
   Seven identical paragraphs rot into seven different paragraphs. One
   canonical explanation, six one-line references to it.

## Pitfalls

- **`re.sub` is global.** `re.sub(p, "", s)` with no `count` replaces every
  match. Almost every "strip the trailing X" helper in a test suite is
  written this way and is correct only by accident of its corpus.
- **The already-anchored copy is why nobody checks the others.** A pin on
  one instance reads, to the next round, as a pin on the class. Say
  explicitly which copy a pin covers.
- **The dangerous failure is green.** A red differential announces itself.
  A classifier quietly filing a new thing into an old bucket does not, and
  `assert other == []` keeps passing. Ask "what would this test look like
  if it were wrong?" before trusting it.
- **Two renderers, one shape.** `"%s (%s)" % (msg, hint)` and
  `"%s (line %d)" % (msg, n)` are indistinguishable downstream. If you
  control both, consider making one of them structurally distinct; if you
  do not, guard the classifier on CONTENT (`^line \d+$`) and keep the
  guard narrow.
- **Anchoring can be wrong.** If the incidental junk is in the middle
  (`worker-3 [pid 902] done in 4ms`), `$` strips nothing and you have
  replaced an over-match with a no-op. Verify with step 3 rather than
  assuming the fix.
- **Do not widen the normaliser to "be smarter".** Every added alternative
  is another shape it will one day over-match. Make it narrower and more
  literal, not cleverer.

## Verification

1. **The count is published.** State how many copies existed and how many
   you changed, in the same sentence:
   `grep -rn '<regex text>' tests/ | grep -v Binary | wc -l` before and
   after. A fix reported without the denominator is a fix to one file.

2. **Round-trip the real string.** For the exact raw message from step 1,
   assert the normalised result still contains the new value:
   ```
   assert NORMALISE(raw) == "<sentence with the new fact intact>"
   ```
   Do this as a test with the string written out literally, not built from
   the code under test — otherwise it moves when the bug moves.

3. **The over-matching form fails it.** Temporarily restore the unanchored
   pattern and re-run that one test. It MUST go red. An anchor whose
   removal changes nothing is guarding a case your corpus does not have.

4. **The downstream classifier is asserted directly.** One test that hands
   the classifier the new string and asserts the bucket, independently of
   any differential. In whence: `_strip_hint(host_sentence) == host_
   sentence`, plus a companion asserting every real hint IS still
   stripped, so the guard cannot be widened into a no-op.

5. **Every suite owning a copy has been run and its result recorded**, not
   just the one that surfaced the problem — with the pass counts, so a
   later reader can see the anchoring was measured rather than assumed.
