---
name: agent-completion-guards
description: Use when an LLM agent loop (tool-calling harness, review/repair/kill campaign, sub-agent runner) records runs as "completed" whose final reply is unusable — a tool call written as plain text like `read_file(path=…)` or `tool call: search`, an empty reply, or an answer missing the JSON the scorer needs — and each such run still cost money. Symptoms: live campaigns with several "failed at step 1–3" results; a scorer reporting "no JSON found" on a run the loop called done; an agent that stops the moment it emits no structured tool call. Covers guarding the completion boundary (detect, recover read-only prose calls, nudge with the backend's exact call syntax, bound retries, a distinct stop reason), and building the detector from a corpus of recorded live failures. NOT for input validation of web APIs, prompt-injection defence, or output moderation; if no agent loop decides "done" from the shape of a reply, this skill does not apply.
---

# Guarding the completion boundary of an agent loop

## When to use (triggers)
- A run log shows `stop_reason: completed` at step 1–3 with a final text
  such as `read_file(path=a.py, start=1, end=40)`, `tool call: search`,
  `{"name": "read_file", "args": {…` followed by "wait, invalid JSON", or
  nothing at all.
- A downstream scorer (`extract_json`, a verdict parser) reports "no
  answer" for runs the loop reported as finished, and the bill for those
  runs is not zero.
- You are adding a new answer format to a task prompt and want the loop
  to *enforce* it rather than hope.

**When NOT to use:** validating user input to a service; moderating
content; retrying transport errors (that is the retry policy, not a
guard); a loop whose "done" signal is an explicit end-turn tool.

## Steps

1. **Build the corpus before the detector.** Collect every recorded final
   text from past live runs (result JSONs usually keep `final_text`) into
   one fixture file with an `expect_reject` flag set BY HAND from the
   run's known outcome. Checkable outcome: a fixture with ≥ 10 texts, of
   which ≥ 3 are known failures and the rest known-good answers.

2. **Make guards pure functions of (text, context).** `Guard.check(text,
   ctx) -> Rejection | None`; the context carries the tool specs, the
   registry (for a read-only marker), and the backend's tool-call syntax
   hint. No guard reads usage, cost, or the model. Checkable outcome:
   every guard is unit-testable with a string and a fake registry.

3. **Detect the observed shapes, not imagined ones.** Python-call style
   (`name(k=v, …)` as the whole reply or its last line), bare mention
   (`tool call: name`), JSON-ish (`"name": "<tool>"` where the enclosing
   object is the call itself, not an answer that nests a tool name), XML
   tags (`<tool_call>`, `<invoke name="…">`), and empty text. Require a
   REGISTERED tool name in every shape — that is what keeps ordinary
   prose that mentions tools from firing. Checkable outcome: the corpus
   test's rejected set equals the hand-labelled set exactly (0 false
   positives, 0 misses).

4. **Recover only when it cannot hurt.** Dispatch a prose call as a real
   call only if the tool exists, is marked read-only (`parallel_safe` or
   equivalent), every argument names a declared parameter, and every
   required one is present; coerce scalars to the schema (`"12"` → 12,
   unquoted paths stay strings). Everything else — write/bash tools,
   positional args, unknown keys — is a nudge. Checkable outcome: tests
   for `bash(command=rm -rf x)` and `search(query=a, b)` both nudge.

5. **The nudge carries the protocol.** Quote the offending reply, say
   NOTHING was run, and include the backend's exact call syntax
   (`llm.tool_call_hint` — a ```tool fence for a CLI backend; "the
   structured tool-use interface" for an API backend). For format guards
   (JSON answer with required keys), the message lists the keys and an
   example. Checkable outcome: a live run whose task never states the
   answer format still ends with a valid answer after one rejection.

6. **Bound rejections per RUN, globally.** `max_guard_retries` counts all
   rejections in the run (not consecutive — a model alternating two bad
   shapes must not loop); when exhausted, end with a DISTINCT stop
   reason (`rejected`) so drivers can tell "answered" from "gave up on
   the format". Persist the counters in the checkpoint (a resumed run
   must not get a fresh allowance) and in the result/trace. Checkable
   outcome: a checkpoint test where the resumed run is rejected at once.

7. **Recovered calls must be well-formed on the wire.** Add the
   synthesized call to the assistant message's `tool_calls` AND to any
   provider-native content blocks (`raw_content`) so the next request's
   `tool_result` has a matching `tool_use`. Checkable outcome: a test
   with `raw_content` present asserts the appended `tool_use` block's id
   equals the tool message's `tool_call_id`.

8. **Demand from the answer only what the scorer needs.** A kill task's
   scorer reads `verdict` and `program`; requiring the prompt's optional
   `argument` key too rejects a perfectly scoreable answer (a scripted
   test caught this on first run). Checkable outcome: the required-keys
   list is derived from the scorer, and a validator hook covers
   conditional needs (`program` non-empty when `verdict == killed`).

9. **Wire it where the money is lost and record the counts.** Campaign
   drivers pass `default_guards() + [answer_guard(kind)]` and store
   `guard_rejections` / `guard_recoveries` per run, so the next report
   can say how many runs the guards saved. Checkable outcome: result
   records carry both counters.

## Pitfalls
- Result JSONs often store `final_text[-N:]`; long good answers lose
  their opening ```json fence to the truncation and look like format
  failures in the corpus test — skip records without an opening fence
  and assert a minimum count checked instead.
- Do not guard the wrap-up answer after `max_steps`: there is no step
  left to retry with; document it instead.
- A "botched" JSON call frequently contains the model's own corrected
  retry object later in the same text; parse every `{` with
  `JSONDecoder.raw_decode` and take the first object whose `name` is the
  tool — two of four recorded failures were dispatchable this way.
- The cost of a nudge is one extra completion that is almost all
  cache-read — ≥ 0.95 only once the prefix is ≥ ~9 k chars; a toy test
  with a 5 k prefix reads 0.92 and fails a 0.95 assertion.
- Anchoring the corpus test on live result files under `state/` breaks
  when they move; copy the texts into the test tree.
- `<tool_call>` tags wrap a JSON body whose name is `"name": "x"`, not an
  attribute — extract both forms or the XML shape reports "a tool" with
  no name.

## Verification
```bash
cd harness && python3 -m pytest -q tests/test_guards.py          # unit + corpus + loop
python3 live_smoke.py cli-guards                                  # live: 1 rejection, then valid JSON
```
Expect: the corpus test passes with the exact hand-labelled set; the
live smoke prints `guard_rejections: 1`, `prose_tool_call events … : 0`,
and a parsed answer.
