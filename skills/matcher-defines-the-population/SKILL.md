---
name: matcher-defines-the-population
description: Use when a rate, base rate, attribution, coverage figure, bound or "nothing else was running" claim rests on a population something else chose. Three choosers: a PATTERN (regex over logs, grep, JSON filter, WHERE clause, event-type allowlist); a REACHABILITY walk (root set, GC-style trace, "everything the graph retains") standing in for everything that existed; or a PREFIX ("the first K", head, LIMIT, stop-after-K-matches), which samples generation order, not the population. Symptoms - a denominator never audited against the source's own vocabulary; a docstring justifying why a verb, PID, tag or section is excluded, or naming a residual class nothing sizes; a cap or budget justified by "nothing reaches it"; a large "no matching event" fraction reported as a property of the system; a file cited by NAME nobody has opened; a source concatenating two views of the same records. Covers enumerating the vocabulary, proving excluded classes empty, and removing a residual by instrumenting the source.
---

# The population you counted is whatever your matcher admitted

## When to use

Trigger this whenever a number depends on a set of events that a *pattern*
produced, and the pattern is not itself under audit:

* a base rate, coverage figure, attribution or "nothing else was running"
  claim whose denominator came from a regex, `grep`, `WHERE` clause or
  event-type allowlist;
* a parser whose docstring or comment explains why some verb, PID, tag, log
  level, section or file is deliberately excluded;
* a large residual class — "N of M observations have no matching event" —
  about to be reported as a property of the system;
* a source file or table cited by NAME across many reports that nobody has
  opened;
* counts that jump by roughly a factor of two at one instant, or an archive
  that concatenates a filtered view of its own earlier text;
* a population defined by REACHABILITY — a root set, a GC-style walk, "every
  node the graph retains" — standing in for "everything that existed";
* a bound, threshold, cap or budget justified by "nothing reaches it";
* a scan bounded by "the first K" whose result is then quoted as a rate.


An attribution, a base rate, a coverage percentage and a "nothing else could
have caused it" all rest on the same thing: a set of events, extracted from a
source by a pattern. The pattern is written once, early, usually with a good
reason, and then it stops being visible. Every number downstream is a
statement about *the events the pattern admits*, and gets read as a statement
about *the events*.

The failure mode is not a bug in the regex. It is that **the excluded class is
never enumerated**, so nobody ever learns that it is the interesting one.

## The instance this came from

Round 436 of this program. Four hundred rounds of memory-perturbation
attribution on one machine rested on this parser:

```python
def parse_unit_starts(text):
    """Matches only `systemd[1]: Starting <unit>.service` ... The narrower
    match is deliberate: `Started` fires for the same unit and would double
    every count, and a user-manager line (`systemd[1057]:`) is not a
    housekeeping timer."""
```

Both exclusions are defended in the docstring, and both are wrong in the same
direction:

* **`Started` is not a duplicate of `Starting` for every unit.** systemd emits
  `Starting` only for a unit with a startup phase to announce; a `Type=simple`
  unit logs `Started` alone. On this box **6 units** — including
  `unattended-upgrades` — never say `Starting`, so **40 fires** were not
  half-counted, they were *absent*.
* **The user manager was not the uninteresting one.** Its journal held
  `qwen36-colibri.service` — the 35B-parameter inference engine, restarted 13
  times in the window, at **30.0 GiB memory peak and 3.9 GiB swap peak** on a
  31.2 GiB box. The largest memory consumer on the machine was outside the
  population by two independent exclusions at once.

The consequence, measured: the graded population's fires covered **19 of 52**
costly buckets and **26.7 %** of all swap-out bytes in the window. The events
the matcher excluded covered **53.2 %** on their own. Five rounds had reported
"33 of 52 costly buckets hold no named fire" as a fact about the *box*. It was
a fact about the *regex*.

And the same round's `supported: []` — the verdict that no unit's cost could
ever be established — became `supported: ["engine:chat-completion"]` at
`p_family 4.5e-32` the moment the excluded class was admitted.

## The second instance: the matcher was a ROOT SET

Round 456 of this program, on the Whence language. `depthcensus.py` measures
how deep the values a program builds are, by walking provenance and structure
edges from a root set: the top-level environment, every discarded statement
value, everything printed. No regex anywhere. The docstring even names the
excluded class in so many words — *"a value that is neither bound, nor a
discarded statement's value, nor printed, nor an input to any of those …
nothing here measures the residual class"* — and the language's rendering cap
was set against the resulting number with the sentence *"24 leaves ten levels
of headroom over the deepest value any example builds."*

Measured directly, by counting at CONSTRUCTION instead of walking from roots:

| | root walk | every value built |
|---|---|---|
| max depth | 14 | **1201** |
| nodes | 3 587 551 | **7 418 398** |

The deepest values in the corpus were built, consumed and dropped, so no root
could reach them. **A reachability choice is a matcher.** "What the program
retains" is a population; "what the program builds" is a different one; the
cap's justification was a sentence about the second, resting on a measurement
of the first.

The move that settled it is step 3 done properly: the residual was not
argued about, it was **removed** — hook the constructor and there is no root
set, so there is no excluded class to enumerate. When a population is defined
by traversal, ask whether the thing being traversed can be instrumented at its
source instead.

## The third: a prefix is not a sample

The same round bounded an expensive per-value check at "the first 400
candidates" and reported **0 of 400**. Exhaustively, the answer is **2813 of
15 178 — 18.5 %**. A uniform 400-sample from an 18.5 % population returns zero
with probability about 1e-35, which is how the bias was caught: the 400 were
the first 400 *in construction order*, and the property correlated with that
order (the early candidates were narrow-and-deep, the late ones wide).

**A `head -K`, a `[:K]`, a `LIMIT K` and a "stop after K matches" all sample
the generator's ORDER.** They are sound only for a property independent of it,
and generation order is rarely independent of anything. If you cannot afford
the whole population, sample it *uniformly* — and either way, print how many
you skipped. Reporting `0` beside a silent `sampled 400 of 15178` is the
shape this whole skill is about.

## Steps

1. **Find every matcher that builds a population.** Regexes over log text,
   `grep` pipelines, `WHERE` clauses, event-type allowlists, `--filter` flags.
   Write down, for each, the axis it discriminates on: verb, actor/PID, tag,
   severity, section, file, time window.

2. **Enumerate the source's own vocabulary on that axis** — do not reason
   about it. For a journal:

   ```sh
   grep -oE 'systemd\[[0-9]+\]: [A-Z][a-z]+' JOURNAL | sed 's/.*: //' \
     | sort | uniq -c | sort -rn        # every verb, with counts
   awk '{for(i=3;i<=NF;i++) if($i ~ /\[[0-9]+\]:$/){print $i;break}}' JOURNAL \
     | sed 's/\[[0-9]*\]:$//' | sort | uniq -c | sort -rn   # every actor
   ```

   The output is the population you *could* have had. Your matcher's count
   goes next to it.

   Do this even when you are not building a population — just reading the
   vocabulary finds things. The same two commands surfaced `Failed with result
   'oom-kill'` in a capture ten rounds of analysis had treated as a memory
   record: the box had OOM-killed three times in the window, once killing the
   very process the whole investigation was about, and nobody had grepped for
   the word because nobody had listed the words.

3. **For each excluded class, prove it is empty or say what it holds.** The
   cheap version is a two-pass audit: which subjects appear ONLY under the
   excluded value?

   ```python
   only_started = set(started) - set(starting)   # not a duplicate of anything
   ```

   A non-empty answer is the finding. Round 436's was six units and 40 fires.

4. **Widen without moving a published number.** Do not loosen the original
   matcher — a silent widening re-derives every historical figure without
   saying so. Add a second function beside it and diff:

   ```python
   base, full = parse_unit_starts(t), parse_unit_starts_complete(t)
   assert Counter(e.label for e in full) >= Counter(e.label for e in base)
   ```

   Then report the delta as a number, including when it is zero.

5. **Check the source for concatenated views before counting anything.** A
   capture that appends a filtered view of its own earlier text inflates every
   count inside the view's time span and only inside it — so a totals check
   passes and the late window looks busier than the early one. Test per
   SECTION, never per line (two genuine events can share a timestamp):

   ```python
   for i, n in enumerate(names):
       for m in names[:i]:
           if set(lines(secs[n])) <= set(lines(secs[m])):
               redundant[n] = m
   ```

   Quote the per-EVENT inflation, not the per-line one. Round 436's file was
   **1.088x** over record lines and **1.99x** over the events any count would
   actually use, because the duplicated view held none of the file's 2774
   `sshd` lines.

6. **A section name records somebody's INTENT; the section holds a command's
   OUTPUT.** The one labelled `USER_MANAGER` in that capture contained zero
   `systemd[` lines — it was 329 lines of engine log, because the command
   under that heading asked for the engine unit's journal while the comment
   beside it said "the user manager". Six rounds cited the file by the
   comment's phrase. Read the first ten lines of anything you are about to
   cite by name, and read the command that produced it.

7. **Before extending the inference, look for the direct measurement.** The
   same journals carried systemd's own cgroup accounting —
   `fwupd.service: Consumed 3.661s CPU time, 209.7M memory peak, 6.2M memory
   swap peak` — a per-invocation figure with no bucket, no threshold and no
   confounder. Cross-check every inferred verdict against it; where the two
   disagree the inference loses.

## Pitfalls

* **"The exclusion is documented, so it was considered."** Round 436's was
  documented in a docstring, with a reason, and the reason was false for 6 of
  74 units. A stated justification is a hypothesis, not an audit.
* **Treating unexplained observations as a property of the system.** "33 of 52
  buckets have no named fire" is a coverage figure of your matcher until you
  have enumerated the vocabulary. Report it as `n_costly_unnamed` beside
  `n_units_tested`, never alone.
* **Widening the original matcher in place.** Every number ever published from
  it silently moves. Add beside; diff; report.
* **Deduplicating a repeated source line-by-line.** Two real events can share
  a second. Deduplicate the *view*, not the *record*.
* **Assuming a bigger population helps your case.** It usually hurts: more
  hypotheses means a tighter Bonferroni bar, and every incumbent unit's
  `p_family` rises. Round 436's went from 26 to 31 hypotheses and the new
  member won anyway — which is what makes the result worth something.
* **Counting lines when the source fans out.** One OOM kill emits "A process
  of this unit has been killed" against every cgroup *ancestor* of the victim,
  in both the system and user journals — 10 lines for 3 kills. Find the line
  shape that identifies the *event* (here `Failed with result 'oom-kill'`,
  which only the unit that died emits) and collapse the rest into it.
* **Reading "the population" off a traversal.** A root-set walk, a GC trace,
  a "reachable from the entry points" closure and a dependency graph all
  define a population by *what something keeps*, which is a matcher with no
  regex to review. Ask what would have to be true for a member to be missed,
  and then build the one instrument that cannot miss it.
* **A bound nothing reaches.** "666x the largest value the corpus produces"
  and "nothing exercises this except the tests written for it" are population
  claims wearing a safety-margin costume. Name the population before the
  factor: round 456's width bound was reached 2813 times by values the
  measured population had never included.
* **Quoting a rate from a truncated scan.** If the scan stopped early, the
  number is a rate over a prefix. Carry the truncation in the same record as
  the rate (`sample_complete: false`), never in a comment.
* **Admitting events whose timestamp semantics differ.** A `Starting` line is
  a start; an access-log line is a completion. Pooling them silently applies
  one boundary convention to both. Carry the semantics on the event and report
  the verdict at several placements.

## Verification

Run against this repo — the audit, the excluded class, and the duplicate-view
detector, all on the banked capture:

```sh
cd /home/pgain/agi-research-nuc-llm
python3 nuc/perturbation.py journal \
  --journal state/nuc-capture-r424/journal-user-full.txt
```

Expect `"redundant_sections": {"USER_MANAGER": "(unlabelled lead)"}`,
`"pid1_unit_starts_in_this_file": 0`, and an
`engine_inflation_if_not_deduped.factor_events` of ~1.99 against a
`factor_record_lines` of ~1.088.

Then the excluded-verb audit and the population delta:

```sh
python3 -c "
import sys; sys.path.insert(0,'nuc')
import perturbation as P
t=open('state/nuc-capture-r424/journal-pid1-full.txt').read()
a=P.unit_start_verb_audit(t)
print(a['units_started_only'], a['n_fires_invisible_to_parse_unit_starts'])
print(len(P.parse_unit_starts_complete(t)) - len(P.parse_unit_starts(t)))"
```

Expect the six `Started`-only units, `40`, and a delta of `40`.

The regression tests are
`nuc/tests/test_perturbation.py::test_six_pid1_units_only_ever_say_started`,
`::test_complete_starts_adds_the_missing_fires_and_doubles_nothing`,
`::test_the_section_labelled_user_manager_is_a_copy_of_earlier_text` and
`::test_the_line_level_inflation_hides_the_event_level_one`.

```sh
python3 -m pytest nuc/tests/test_perturbation.py -q
```

### For the reachability and prefix cases (round 456)

The paired demonstration that a root set IS a matcher — one program whose deep
value is consumed, one whose is not, same source but for one line:

```sh
cd /home/pgain/agi-research-nuc-llm/languages/whence
python3 -c "
import depthcensus as D, os, tempfile
def run(body):
    fd,p = tempfile.mkstemp(suffix='.lang')
    os.write(fd, ('fn deep() {\n let a = [[[[[[[1]]]]]]]\n %s\n}\n'
                  'let n = deep()\nprint(1)\n' % body).encode()); os.close(fd)
    try:  r = D.census_program(p)
    finally: os.unlink(p)
    return r['built_depth'], r['alloc_depth'], r['alloc_depth_reachable']
print('dropped ', run('0'))
print('returned', run('a'))"
```

Expect `dropped  (0, 7, False)` and `returned (7, 7, True)`. The root walk
reports depth **0** for a program that builds a 7-deep list.

The regression tests, including the prefix-is-not-a-sample pair, are in
`languages/whence/tests/test_depthcensus.py`:

```sh
cd /home/pgain/agi-research-nuc-llm/languages/whence
python3 -m pytest -c pytest.ini -q -m "not whence_slow" tests/test_depthcensus.py
```

Expect **45 passed, 3 deselected**. The three deselected are the corpus
readings; `::test_a_prefix_of_construction_order_is_not_a_sample` is the one
that runs the same scan twice, bounded and exhaustive, and asserts `0` against
`2813`.
