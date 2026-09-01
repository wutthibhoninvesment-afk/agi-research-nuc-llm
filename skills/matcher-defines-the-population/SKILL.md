---
name: matcher-defines-the-population
description: Use when a rate, base rate, attribution, coverage figure or "nothing else was running" claim rests on a population of events extracted by a pattern — a regex over logs, a grep of a journal, a JSON filter, a query with a WHERE clause, an event-type allowlist. Symptoms - a denominator built by one matcher and never audited against the source's own vocabulary; a parser docstring justifying why a second verb, PID, tag, level or section is excluded; a large fraction of observations with "no matching event" treated as unexplained rather than as evidence the matcher is narrow; a file or table cited by its NAME for six months with nobody reading what it contains; counts taken across a source that concatenates two views of the same records. Covers enumerating every verb/actor/section the source actually emits, proving the excluded classes are empty rather than assuming it, and detecting a section that is a duplicate view of another.
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
  that concatenates a filtered view of its own earlier text.


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
