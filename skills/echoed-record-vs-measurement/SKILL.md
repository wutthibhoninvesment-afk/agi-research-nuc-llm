---
name: echoed-record-vs-measurement
description: Use when a log line, status output, dashboard row or CI summary is your evidence for what a process DID — before inferring a mechanism from it, or when building something that prints a stored verdict next to a fresh one. Symptoms: a summary line whose numbers are byte-identical across runs; a PASS whose parenthetical names a failing test; a status command that prints the same text whether it just measured or is re-reading a ledger; a claim in a design doc or ticket of the form "the pipeline does X every run" sourced from a line rather than from the code that emits it. Covers finding a line's emitter, separating measured output from echoed records in one stream, marking the boundary, and re-deriving a corrupted archive from the logs it was written from.
---

# A line is not a measurement until you know who wrote it

A process prints what it measured. Later, someone appends a *recorded*
status to the same stream — the last run's verdict, a cached ledger row, a
"here is where we stood" summary — because it is cheap and useful next to
the fresh output. Anything downstream that reads "the last line", or a human
reading the tail, now sees a number that was true somewhere else, at some
other time, about something else, with nothing in the text saying so.

The failure is not that the record lies. Every echoed line is accurate about
its own past. It is that **provenance is carried by position**, and position
is not information.

## When to use (triggers)

1. You are about to state what a system does, and the evidence is a line it
   printed (a log entry, a CI badge, a status row) rather than the code path
   that prints it.
2. A summary line's numbers are identical across consecutive runs. Identical
   is the tell: real measurements of a moving tree move.
3. One stream carries both a fresh run's output and a stored verdict —
   `foo status`, `--report`, a wrapper that appends a cache summary.
4. A verdict word and the text beside it disagree (PASS next to a failing
   test id; "clean" next to a timestamp older than the change you shipped).
5. You are writing a `status` subcommand that re-prints a ledger, or a
   wrapper that echoes one after a real run.
6. A carried note, ticket or next-step describes a mechanism nobody has
   re-read the code for, and its author cites output as the reason.

Not this skill when the concern is that a status field records that a check
HAPPENED rather than what it FOUND — that is `freshness-is-not-outcome`.
This one is about two processes' output sharing one stream.

## Steps

1. **Grep the exact string, not a paraphrase.** `grep -F "<the line>"
   <log>` tells you how many times it has appeared. A line that repeats
   verbatim across rounds/builds/days is a record being re-printed, not a
   measurement being re-taken.
2. **Find the emitter.** Grep the distinctive substring across the source
   tree. You are looking for the `print`/`echo`/formatter, then for its
   CALLER. The question to answer is not "what does this say" but "which
   process ran, with what input, at what time".
3. **Check the mechanism the line implies actually exists.** If the line
   makes you believe the pipeline runs step X every time, grep the driver
   for X. One grep. This is the whole refutation in most cases, and it is
   cheaper than the paragraph you were about to write.
4. **Read the record's own provenance fields.** A ledger row usually stores
   `recorded_at`, a commit, a host. If the printer drops them, that is the
   defect — not the reader's inference.
5. **Mark the boundary at the producer.** Print a sentinel where the
   measured output ends. Define the string in the module that PARSES it,
   and pin it with a test that reads the file that PRINTS it, so a
   two-language pair cannot drift.
6. **Make the consumer compute from the measured region only** — the
   summary AND any derived flags. If the boundary has to be inferred for
   old data, report the inference (`source: "guess"`), never launder it
   into a confident value.
7. **Re-derive the archive.** The corrupted lines are usually downstream of
   intact source logs. A `replay` command over them recovers what each
   entry should have said, which is how you get numbers for the write-up
   instead of adjectives.
8. **Make `status` say it is a status.** Print when the record was made, how
   old it is, and — the load-bearing one — whether the world has moved since
   (HEAD, build id, config hash). That is a CHECK, not a caption, and it is
   what stops the next reader inferring a mechanism from it.

## Worked example (round 379)

`run_driver.sh` logs one health line per research round. For 38 consecutive
rounds it read:

```
round 378: health-check PASS (whence-slow clean live={...'passed': 70} ... 1014.6s)
```

- Step 1: `1014.6s` appears in six consecutive rounds' lines, byte-identical.
- Step 2: the emitter is `driver_health.health_log_line`, which quotes "the
  last non-empty line" of the health log; the log's last line comes from two
  `status` echoes the test script appends after its own pytest run.
- Step 3: the line implies the driver runs a pristine whence-slow
  differential every round. `grep -n pristine run_driver.sh` → **nothing**.
  The driver runs three fast suites on the live tree. 1 second.
- Step 4: the row is from a ledger written 5 rounds earlier at a commit the
  tree had already left; `recorded_at` and `resolved` were both in the JSON
  and neither was printed.
- Steps 5-8: sentinel + measured-region parsing + `health_replay` over 136
  archived logs (**38 lines wrong, 0 verdicts wrong**) + a `status` header
  that prints the age and `HEAD HAS MOVED SINCE`.

The cost of NOT doing step 3: one round inferred the mechanism from the
line, wrote it into the project's state file, and two later rounds carried
it forward as an open work item addressed to the team that owned the code.

## Pitfalls

- **Fixing the reader only.** The producer keeps emitting an ambiguous
  stream and the next consumer re-derives the same bug.
- **Special-casing the foreign format.** Teaching a pytest-shaped parser
  about a non-pytest tail is how the ambiguity became load-bearing in the
  first place. Report out-of-contract input as out of contract.
- **Trusting a boundary heuristic on data you have not looked at.** "The
  last count line ends the run" is true for one family of logs and false
  for any tool whose real verdict comes last.
- **Rewriting the historical log.** It was written once, live. Re-derive
  from the source logs and publish the derivation; leave the record.
- **Assuming the verdict word is wrong too.** Usually it is not — the exit
  code carried it. Measure that separately, and say so: it bounds the blast
  radius and keeps the report honest.

## Verification

You have applied this skill correctly when:

1. You can name the process, the time and the input for every line you cite
   as evidence.
2. The mechanism a line implied was checked against the code that would
   have to implement it, and the check is written down with its cost.
3. The producer marks its own boundary, and one test ties the printed string
   to the parsed constant.
4. The consumer's derived flags (not just its quoted text) come from the
   measured region.
5. Inferred boundaries are labelled as inferred in the output, not only in
   a comment.
6. The archive was replayed and the write-up says how many entries changed
   AND how many verdicts changed — two different numbers.

```sh
# step 1: is this line a measurement or a re-print?
grep -cF "1014.6s" logs/driver.log

# step 3: does the mechanism the line implies exist at all?
grep -n "pristine" run_driver.sh

# step 7: what should each entry have said?
python3 -m harness.driver_health health_replay logs/health_round_*.log
```
