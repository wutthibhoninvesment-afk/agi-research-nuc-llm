"""Round-28 (E3) tests: geometry, the reuse decision (mirrors the C unit test
scenarios in nuc/kv_reuse/test_qwen36_prefix.c), and the retokenization
experiment on the REAL probe output from :8000 (kv_reuse/probe_p1.json + the
raw reply recorded in /tmp/r28_probe.json on the NUC)."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
NUC = os.path.dirname(HERE)
sys.path.insert(0, NUC)

import kv_reuse_model as krm  # noqa: E402

# Round 442 (NUC-integration E): the same guard `test_prompt_budget.py` has
# carried since round 22, applied to the two tests here that need a real
# tokenizer. `tokenizers` is an OPTIONAL dependency — it is present in the
# repo `.venv` (which every round runs under, via claude-wrapper.sh) and
# absent from /usr/bin/python3 (which the driver's health checks run under,
# because run_driver.sh never activates the venv). Without this marker those
# two tests raised ModuleNotFoundError instead of skipping, and
# `nuc-health-check` reported FAIL on every round from 410 to 441 — 32
# consecutive rounds, zero PASSes — for a missing optional dependency rather
# than for a regression. A health check that cannot go green cannot report
# anything. Round 442 also made the check pick the venv interpreter
# (`nuc/run_checks_fast.sh`), so on this host these tests RUN; this marker is
# the belt to that braces, and it is what keeps the answer honest on any
# interpreter that lacks the library.
needs_tok = pytest.mark.skipif(
    not krm.have_tokenizer(),
    reason="tokenizers lib or tokenizer.json missing")

RAW_REPLY = '{"tool_calls":[{"name":"run_shell","arguments":{"command":"df -h /"}}]}'


# --- geometry ----------------------------------------------------------------
def test_kv_bytes_per_token_matches_engine_comment():
    # qwen36.c: "Context costs 40 KB/token in KV (10 attention layers, f32)"
    assert krm.kv_bytes_per_token() == 40960


def test_dn_snapshot_is_fixed_and_small():
    b = krm.dn_snapshot_bytes()
    rec = 30 * 32 * 128 * 128 * 4          # 62.9 MB recurrent
    conv = 30 * (2 * 16 * 128 + 32 * 128) * 3 * 4   # 2.9 MB conv rings
    assert b == rec + conv
    assert 60e6 < b < 70e6
    # a 26.5k-token Hermes prefix costs 1.08 GB of KV rows but the same snapshot
    assert 26483 * krm.kv_bytes_per_token() > 1.0e9


# --- the decision (same scenarios as test_qwen36_prefix.c) -------------------
def test_strict_continuation():
    sm = krm.StateModel()
    assert sm.prepare([1, 2, 3, 4, 5, 6]) == (0, 0)
    sm.feed([1, 2, 3, 4, 5, 6], 0)
    assert sm.prepare([1, 2, 3, 4, 5, 6, 9, 10]) == (6, 0)
    assert sm.fed == [1, 2, 3, 4, 5, 6]


def test_prompt_end_snapshot_survives_rerendered_reply():
    sm = krm.StateModel()
    sm.prepare([1, 2, 3, 4, 5, 6]); sm.feed([1, 2, 3, 4, 5, 6], 0)
    assert sm.snap(sm.PROMPT_END, 6)
    sm.feed([20, 21], 6)                       # decoded reply
    reuse, lcp = sm.prepare([1, 2, 3, 4, 5, 6, 30, 31, 32])
    assert (reuse, lcp) == (6, 6)
    assert sm.fed == [1, 2, 3, 4, 5, 6] and sm.snaps == {sm.PROMPT_END: 6}


def test_deepest_snapshot_wins_and_deeper_dropped():
    sm = krm.StateModel()
    sm.prepare([1, 2, 3, 4, 5, 6])
    sm.feed([1, 2, 3], 0); assert sm.snap(sm.SYS, 3)
    sm.feed([4, 5, 6], 3); assert sm.snap(sm.PROMPT_END, 6)
    assert sm.prepare([1, 2, 3, 4, 5, 6, 30, 31, 32])[0] == 6
    assert sm.snaps == {sm.SYS: 3, sm.PROMPT_END: 6}
    sm.feed([30, 31, 32], 6)
    reuse, lcp = sm.prepare([1, 2, 3, 40, 41, 42, 43])
    assert (reuse, lcp) == (3, 3)
    assert sm.snaps == {sm.SYS: 3}


def test_rejections():
    sm = krm.StateModel()
    sm.prepare([1, 2, 3, 4, 5, 6]); sm.feed([1, 2, 3, 4, 5, 6], 0); sm.snap(sm.PROMPT_END, 6)
    assert not sm.snap(sm.SYS, 4)                       # state is not at 4
    assert sm.prepare([1, 2, 3, 4, 5, 6]) == (0, 5)     # equal prompt: nothing to feed
    assert sm.fed == [] and sm.snaps == {}
    sm.feed([1, 2, 3, 4, 5, 6], 0); sm.snap(sm.PROMPT_END, 6)
    assert sm.prepare([1, 2, 3, 4])[0] == 0              # shorter, no snapshot inside
    sm.feed([1, 2, 3, 4, 5, 6], 0)
    assert sm.prepare([9, 9, 9, 9, 9, 9, 9]) == (0, 0)   # diverges
    off = krm.StateModel(enabled=False)
    off.feed([1, 2, 3], 0)
    assert off.prepare([1, 2, 3, 4])[0] == 0


def test_serve_plans_system_cut_from_lcp_without_hint():
    sm = krm.StateModel()
    sys_ids = list(range(100, 170))               # 70-token shared system prefix
    a = sys_ids + [1, 2, 3]
    b = sys_ids + [7, 8, 9, 10]
    assert sm.serve(a, [50, 51]) == len(a)        # cold, nothing to plan yet
    # second fresh conversation: LCP = 70 -> no snapshot there yet, so cold
    # prefill again, but the cut is planned at 70 for the NEXT one
    assert sm.serve(b, [60]) == len(b)
    assert sm.snaps[sm.SYS] == 70
    c = sys_ids + [11, 12]
    assert sm.serve(c, [61]) == 2                  # third conversation: only the tail


def test_serve_with_hint_seeds_the_first_conversation():
    sm = krm.StateModel()
    sys_ids = list(range(100, 170))
    a = sys_ids + [1, 2, 3]
    assert sm.serve(a, [50, 51], prefix_hint_pos=70) == len(a)
    assert sm.snaps[sm.SYS] == 70
    b = sys_ids + [7, 8, 9, 10]
    assert sm.serve(b, [60], prefix_hint_pos=70) == 4


# --- timing model ------------------------------------------------------------
def test_prefill_seconds_tail_is_cheaper_than_cold():
    cold = krm.prefill_seconds(646, 0)
    tail = krm.prefill_seconds(646, 546)
    assert 90 < cold < 110
    assert 15 < tail < 25
    assert krm.decode_tok_s(300) == 5.3 and 1.0 <= krm.decode_tok_s(26483) < 3.0


# --- the retokenization experiment on real engine output ---------------------
@pytest.fixture(scope="module")
def probe():
    p = os.path.join(NUC, "kv_reuse", "probe_p1.json")
    if not os.path.exists(p) or not os.path.exists(os.path.join(NUC, "tokenizer-qwen36.json")):
        pytest.skip("probe artifacts / tokenizer not present")
    return json.load(open(p))


def _turn2_request(req1, raw_reply):
    import importlib.util
    spec = importlib.util.spec_from_file_location("nuc_adapter", os.path.join(NUC, "nuc-adapter-copy.py"))
    ad = importlib.util.module_from_spec(spec); spec.loader.exec_module(ad)
    content, calls = ad.parse_tool_reply(raw_reply)
    assert calls, "the probe reply must parse as a tool call"
    msgs = list(req1["messages"]) + [
        {"role": "assistant", "content": content, "tool_calls": calls},
        {"role": "tool", "name": calls[0]["function"]["name"],
         "content": "/dev/mapper/ubuntu--vg-root  98G   14G   80G  15% /"},
    ]
    return {"messages": msgs, "tools": req1["tools"]}


@needs_tok
def test_agent_turn2_breaks_strict_but_not_snapshot(probe):
    """Turn 2's prompt continues turn 1's prompt only up to the assistant
    header: the generation suffix (empty <think> block) is omitted from the
    history rendering and the adapter re-renders the tool call with json.dumps
    spacing. So a kimi_k3-style strict engine reuses 0, a prompt-END snapshot
    would be unreachable, and the stable-boundary snapshot reuses everything
    up to the header (334 of 339 turn-1 tokens)."""
    import prompt_budget as pb
    tok = krm.tokenizer()
    p1 = probe["p1"]
    p2 = pb.engine_prompt(_turn2_request(probe["request"], RAW_REPLY))
    assert not p2.startswith(p1)                     # the empty think block is not in history
    st = krm.stable_boundary(p1)
    assert p1.endswith("<think>\n\n</think>\n\n") and st == len(p1) - len("<think>\n\n</think>\n\n")
    assert p2.startswith(p1[:st])                    # ... but everything up to the header is
    assert not p2.startswith(p1[:st] + RAW_REPLY)    # and the raw reply is re-rendered
    ok, n_stable, n2 = krm.token_prefix_stable(tok, p2, p1[:st])
    # the generation suffix is exactly 4 tokens: <think> \n\n </think> \n\n
    assert ok and n_stable == 335 and n2 > n_stable  # a TOKEN prefix too
    assert tok.encode(p1[st:]).ids == [248068, 271, 248069, 271]
    reply2 = "The root filesystem has 80 GB free"
    rows = krm.agent_session([p1, p2], [RAW_REPLY, reply2], policy="strict")
    assert rows[1]["reuse"] == 0
    rows = krm.agent_session([p1, p2], [RAW_REPLY, reply2], policy="snapshot")
    assert rows[1]["reuse"] == 335
    assert rows[1]["prefilled"] == n2 - 335
    # without the stable hint the engine falls back to the system boundary
    sm = krm.StateModel()
    p1_ids, p2_ids = tok.encode(p1).ids, tok.encode(p2).ids
    sys_pos = krm.token_prefix_stable(tok, p1, p1[:krm.system_boundary(p1)])[1]
    sm.serve(p1_ids, tok.encode(RAW_REPLY).ids, prefix_hint_pos=sys_pos)
    assert sm.serve(p2_ids, tok.encode(reply2).ids, prefix_hint_pos=sys_pos) == n2 - sys_pos
    assert sys_pos == 317


@needs_tok
def test_system_hint_is_a_token_prefix_for_nuc_mini(probe):
    tok = krm.tokenizer()
    p1 = probe["p1"]
    cut = krm.system_boundary(p1)
    assert cut > 0
    ok, n_sys, n_all = krm.token_prefix_stable(tok, p1, p1[:cut])
    assert ok and 250 < n_sys < n_all
