"""Token estimation, calibration, and history compaction invariants."""
import copy

import pytest

from agentloop.context import (ContextBudget, TokenEstimator, compact, ELIDED_STUB,
                               _steps)


def history(n_steps, obs_chars=1000, task="do the thing"):
    """system, task, then n steps of (assistant tool call, tool result)."""
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": task}]
    for i in range(n_steps):
        msgs.append({"role": "assistant", "content": "", "tool_calls": [
            {"name": "read_file", "args": {"path": "f%d" % i}, "call_id": "c%d" % i}]})
        msgs.append({"role": "tool", "content": "x" * obs_chars, "tool_call_id": "c%d" % i,
                     "tool_name": "read_file", "ok": True})
    return msgs


# ------------------------------------------------------------ estimator ---

def test_estimate_scales_with_chars_and_tools():
    est = TokenEstimator(chars_per_token=4.0)
    small = est.estimate([{"role": "user", "content": "a" * 400}])
    big = est.estimate([{"role": "user", "content": "a" * 4000}])
    assert 95 <= small <= 110 and 995 <= big <= 1010
    with_tools = est.estimate([{"role": "user", "content": "a" * 400}], [{"name": "t", "x": "y" * 400}])
    assert with_tools > small + 90


def test_calibration_converges_on_observed_ratio_and_is_clamped():
    est = TokenEstimator(chars_per_token=4.0)
    est.observe(3000, 1000)                 # first observation replaces the prior
    assert est.chars_per_token == pytest.approx(3.0)
    for _ in range(30):
        est.observe(3500, 1000)
    assert est.chars_per_token == pytest.approx(3.5, abs=0.01)
    est.observe(100, 1000)                  # absurd ratio -> clamped at min
    assert est.chars_per_token >= est.min_ratio
    est.observe(0, 5); est.observe(5, 0)   # ignored
    assert est.observations == 32


def test_bad_ctor_args_rejected():
    with pytest.raises(ValueError):
        TokenEstimator(chars_per_token=0)
    with pytest.raises(ValueError):
        ContextBudget(max_input_tokens=0)
    with pytest.raises(ValueError):
        ContextBudget(max_input_tokens=10, reserve_tokens=10)


# ------------------------------------------------------------ compaction ---

def test_under_budget_is_a_noop():
    msgs = history(3)
    before = copy.deepcopy(msgs)
    r = compact(msgs, ContextBudget(max_input_tokens=100_000), TokenEstimator(4.0))
    # compact()'s own size check caches each message's char cost on the dict
    # (`_chars`, round 13) so a later step doesn't re-serialize an unchanged
    # prefix. That is bookkeeping, not conversation content — strip it before
    # asserting nothing observable changed. content-visible fields must still
    # be untouched: no elision, no drop stub, no key deleted/renamed.
    without_cache = [{k: v for k, v in m.items() if k != "_chars"} for m in msgs]
    assert not r.changed and r.fits and without_cache == before


def test_stage1_elides_oldest_observations_first_and_keeps_recent():
    msgs = history(6, obs_chars=1000)
    est = TokenEstimator(4.0)
    # 6 obs * 250 tok = 1500; budget 900 forces ~3 elisions
    r = compact(msgs, ContextBudget(max_input_tokens=900, keep_recent_results=2), est)
    assert r.changed and r.fits and r.dropped_steps == 0
    tools = [m for m in msgs if m["role"] == "tool"]
    elided = [bool(m.get("elided")) for m in tools]
    assert elided[-2:] == [False, False]                    # newest two untouched
    assert elided[:r.elided_results] == [True] * r.elided_results  # oldest first, contiguous
    stub = tools[0]["content"]
    assert stub == ELIDED_STUB.format(tool="read_file", chars=1000)
    assert tools[0]["elided_chars"] == 1000
    assert len(msgs) == 2 + 12                               # nothing dropped


def test_compaction_is_monotonic_and_prefix_stable():
    msgs = history(6, obs_chars=1000)
    est = TokenEstimator(4.0)
    budget = ContextBudget(max_input_tokens=900, keep_recent_results=2)
    compact(msgs, budget, est)
    snapshot = copy.deepcopy(msgs)
    r2 = compact(msgs, budget, est)         # second pass: already fits
    assert not r2.changed and msgs == snapshot
    # a new step arrives: previously elided messages are byte-identical, and a
    # formerly "recent" observation may age into elision but never the reverse
    msgs += history(1)[2:]
    compact(msgs, budget, est)
    for old, new in zip(snapshot, msgs):
        if old.get("elided"):
            assert new == old
        elif new.get("elided"):
            assert old["role"] == "tool" and not old.get("elided")
        else:
            assert new == old


def test_stage2_drops_whole_steps_and_leaves_one_summary():
    msgs = history(5, obs_chars=1000)
    est = TokenEstimator(4.0)
    # even with all-but-2 elided, ~2 * 250 + stubs > 300 -> must drop steps
    r = compact(msgs, ContextBudget(max_input_tokens=330, keep_recent_results=2, min_steps_kept=1), est)
    assert r.dropped_steps >= 1
    assert msgs[0]["role"] == "system" and msgs[1]["content"] == "do the thing"
    stubs = [m for m in msgs if m.get("dropped_steps")]
    assert len(stubs) == 1 and stubs[0]["role"] == "user"
    assert "read_file" in stubs[0]["content"] and str(r.dropped_steps) in stubs[0]["content"]
    # pairing invariant: every assistant with tool_calls is followed by its results
    for s, e in _steps(msgs):
        calls = msgs[s]["tool_calls"]
        results = [m["tool_call_id"] for m in msgs[s + 1:e]]
        assert [c["call_id"] for c in calls] == results
    assert _steps(msgs) and len(_steps(msgs)) >= 1     # min_steps_kept honoured


def test_repeated_drops_merge_into_one_stub():
    msgs = history(4, obs_chars=1000)
    est = TokenEstimator(4.0)
    budget = ContextBudget(max_input_tokens=330, keep_recent_results=1, min_steps_kept=1)
    compact(msgs, budget, est)
    n1 = [m for m in msgs if m.get("dropped_steps")][0]["dropped_steps"]
    msgs += history(3, obs_chars=1000)[2:]
    compact(msgs, budget, est)
    stubs = [m for m in msgs if m.get("dropped_steps")]
    assert len(stubs) == 1 and stubs[0]["dropped_steps"] > n1
    assert stubs[0]["content"].count("read_file") == 1


def test_floor_reported_when_even_minimum_does_not_fit():
    msgs = history(2, obs_chars=1000, task="t" * 20000)
    r = compact(msgs, ContextBudget(max_input_tokens=100, keep_recent_results=0), TokenEstimator(4.0))
    assert not r.fits and r.after_tokens > 100
    assert msgs[1]["content"] == "t" * 20000              # task never touched
    assert len(_steps(msgs)) == 1                          # min_steps_kept default 1


def test_steps_helper_ignores_preamble_and_handles_text_only_turns():
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"},
            {"role": "assistant", "content": "thinking", "tool_calls": []},
            {"role": "assistant", "content": "", "tool_calls": [{"name": "a", "args": {}, "call_id": "1"}]},
            {"role": "tool", "content": "r", "tool_call_id": "1", "tool_name": "a"}]
    assert _steps(msgs) == [(2, 3), (3, 5)]


# ------------------------------------------------------- char-cost cache ---
# Round 13: chars_of() caches each message's cost on the dict (`_chars`) so a
# long-running loop doesn't re-serialize the whole transcript's tool-call
# args every step (round 6 measured 16ms/step at 2000 messages, dominated by
# json.dumps() over an unchanged prefix).

def test_chars_of_is_idempotent_and_matches_uncached_value():
    import json as _json
    msgs = history(4, obs_chars=1000)
    est = TokenEstimator(4.0)
    uncached_total = sum(
        len(m.get("content") or "") + 8 + sum(
            len(c["name"]) + len(_json.dumps(c["args"], sort_keys=True)) + 8
            for c in (m.get("tool_calls") or []))
        for m in msgs)
    first = est.chars_of(msgs)
    assert first == uncached_total
    assert all("_chars" in m for m in msgs)
    second = est.chars_of(msgs)          # cache hit path, same list, no mutation since
    assert second == first


def test_chars_of_cache_skips_reserialization_of_unchanged_messages(monkeypatch):
    import agentloop.context as ctx
    msgs = history(5, obs_chars=1000)
    est = TokenEstimator(4.0)
    est.chars_of(msgs)                    # populate every message's cache

    calls = {"n": 0}
    real_dumps = ctx.json.dumps

    def counting_dumps(*a, **kw):
        calls["n"] += 1
        return real_dumps(*a, **kw)

    monkeypatch.setattr(ctx.json, "dumps", counting_dumps)
    est.chars_of(msgs)                    # nothing changed -> nothing re-serialized
    assert calls["n"] == 0


def test_chars_of_cache_invalidated_by_elide_and_recomputes_correctly():
    msgs = history(3, obs_chars=1000)
    est = TokenEstimator(4.0)
    tool_msg = [m for m in msgs if m["role"] == "tool"][0]
    est.chars_of(msgs)
    assert tool_msg["_chars"] == 1008     # 1000 chars content + 8 overhead, uncompacted

    r = compact(msgs, ContextBudget(max_input_tokens=200, keep_recent_results=0), est)
    assert r.elided_results >= 1
    stub_len = len(ELIDED_STUB.format(tool="read_file", chars=1000))
    assert tool_msg["_chars"] == stub_len + 8    # recomputed from the stub, not stale


def test_chars_of_accounts_new_messages_only_after_first_pass():
    msgs = history(3, obs_chars=1000)
    est = TokenEstimator(4.0)
    before = est.chars_of(msgs)
    for m in msgs:
        assert "_chars" in m
    msgs += history(1, obs_chars=1000)[2:]     # one more step, appended
    after = est.chars_of(msgs)
    added = sum(m.get("_chars", 0) for m in msgs[len(msgs) - 2:])
    assert after == before + added
    # the original messages' cached costs are untouched by the append
    for m in msgs[:-2]:
        assert m["_chars"] > 0


def test_tools_chars_cached_by_identity_and_invalidated_on_length_change():
    est = TokenEstimator(4.0)
    tools_a = [{"name": "bash", "description": "run a command"}]
    tools_b = [{"name": "read_file", "description": "read a file, longer description here"}]
    ca = est.chars_of([], tools_a)
    cb = est.chars_of([], tools_b)
    assert ca != cb
    assert est.chars_of([], tools_a) == ca     # identity cache hit, still correct
    tools_a.append({"name": "grep", "description": "search"})
    ca2 = est.chars_of([], tools_a)            # same list object, different length
    assert ca2 > ca                            # cache invalidated, not stale


def test_raw_content_supersedes_content_and_tool_calls_in_chars_of():
    est = TokenEstimator(4.0)
    plain = [{"role": "assistant", "content": "hi", "tool_calls": []}]
    with_raw = [{"role": "assistant", "content": "hi", "tool_calls": [],
                 "raw_content": [{"type": "thinking", "thinking": "x" * 500, "signature": "sig"}]}]
    assert est.chars_of(with_raw) > est.chars_of(plain) + 400
