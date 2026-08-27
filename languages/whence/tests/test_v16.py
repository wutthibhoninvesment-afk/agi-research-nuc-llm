"""v0.16 (round 204): persistent records — structural sharing for `put`.

Round 200 (self-hosting round 7) measured and root-caused an O(N^2)
cumulative-allocation problem in the guest-evaluator store-passing pattern:
`b_put` did `fields = dict(r.payload.fields); fields[name] = v` — a full
shallow copy of the CURRENT store on every single `put`, with every
superseded copy kept permanently reachable via provenance (`why`/`steps`
must be able to trace back through it, by design). N sequential `put`s each
costing O(current size) is quadratic by construction.

This round gives `Record` the same treatment `WList` (v0.6) already gives
lists: `whence.values.PMap`, a persistent (immutable) AVL tree keyed by
string. `put`/`merged_with` return a NEW map sharing every untouched
subtree — O(log n) new nodes per update instead of a full O(n) copy, so N
sequential `put`s cost O(N log N) cumulative, not O(N^2), while every
intermediate version stays exactly as reachable as before (nothing about
`why`/`steps`/provenance retention changes — this is a representation
change under `Record`, not a semantics change).

Design anchors this file pins:
  - Every Record-consuming builtin/operator (`get`/`put`/`has`/`merge`/
    `keys`, field access, `==`/`deep_eq`, `show`/structural-type
    validation) behaves BYTE-IDENTICALLY whether the record was built from
    a literal (`Record(dict)` -> `PMap.from_dict`) or reached through a
    long chain of `put`s (`Record(PMap)` passed straight through, no
    Record-level copy at all — see `Record.__init__`).
  - Record field ORDER was never semantically meaningful to begin with:
    every display site already does `sorted(p.fields...)` and equality is
    set-based, so PMap's key-ordered iteration is not a behaviour change.
  - `put` on an EXISTING key updates the value and leaves size unchanged
    (dict semantics); on a NEW key it grows size by exactly one.
  - Three-way (fast/direct/slow) parity: a long `put` chain must produce
    byte-identical `render_why`/output/checks across all three evaluation
    modes, same discipline as every other feature in this codebase.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_v09 import run, val, assert_three_way  # noqa: E402

from whence.values import PMap, Record  # noqa: E402


# --- PMap unit tests: differential against plain dict -----------------

def test_pmap_empty():
    m = PMap()
    assert len(m) == 0
    assert list(m) == []
    assert m.get("x") is None
    assert m.get("x", "default") == "default"
    assert "x" not in m
    assert not m
    assert m.to_dict() == {}


def test_pmap_put_new_key_grows_size():
    m = PMap().put("a", 1)
    assert len(m) == 1
    m2 = m.put("b", 2)
    assert len(m2) == 2
    assert len(m) == 1               # m itself is untouched (persistent)
    assert m.get("b") is None
    assert m2.get("a") == 1 and m2.get("b") == 2


def test_pmap_put_existing_key_same_size():
    m = PMap().put("a", 1).put("b", 2)
    m2 = m.put("a", 99)
    assert len(m2) == 2               # size unchanged, value updated
    assert m2.get("a") == 99
    assert m.get("a") == 1             # the old version still reads the old value


def test_pmap_getitem_and_keyerror():
    m = PMap().put("a", 1)
    assert m["a"] == 1
    try:
        m["missing"]
        assert False, "expected KeyError"
    except KeyError:
        pass


def test_pmap_from_dict_roundtrip():
    d = {"z": 1, "a": 2, "m": 3}
    m = PMap.from_dict(d)
    assert m.to_dict() == d
    assert sorted(m.items()) == sorted(d.items())
    assert set(m) == set(d)


def test_pmap_merged_with_other_wins_on_conflict():
    a = PMap.from_dict({"x": 1, "y": 2})
    b = PMap.from_dict({"y": 99, "z": 3})
    merged = a.merged_with(b)
    assert merged.to_dict() == {"x": 1, "y": 99, "z": 3}
    # both inputs untouched
    assert a.to_dict() == {"x": 1, "y": 2}
    assert b.to_dict() == {"y": 99, "z": 3}


def test_pmap_old_versions_survive_every_update_structural_sharing():
    """The whole point: every intermediate version must still read back
    correctly after later `put`s — nothing is mutated in place."""
    versions = [PMap()]
    for i in range(200):
        versions.append(versions[-1].put("k%d" % i, i))
    for i, m in enumerate(versions):
        assert len(m) == i
        for j in range(i):
            assert m.get("k%d" % j) == j
        for j in range(i, 200):
            assert m.get("k%d" % j) is None


def test_pmap_differential_fuzz_vs_dict():
    """Long randomized put sequence over a small key universe (heavy churn
    on existing keys, matching the guest store-passing pattern) must agree
    with a plain dict at every step, plus a mid-run branch (two divergent
    futures from the same shared prefix) to exercise real sharing."""
    rng = random.Random(20204)
    keys = ["field_%d" % i for i in range(12)]
    d = {}
    m = PMap()
    snapshot_d = snapshot_m = None
    for step in range(3000):
        k = rng.choice(keys)
        v = rng.random()
        d[k] = v
        m = m.put(k, v)
        assert len(m) == len(d)
        assert m.to_dict() == d
        if step == 1500:
            snapshot_d, snapshot_m = dict(d), m
    # branch off the snapshot down a different path than `d`/`m` took
    d2, m2 = dict(snapshot_d), snapshot_m
    for step in range(1500):
        k = rng.choice(keys)
        v = rng.random()
        d2[k] = v
        m2 = m2.put(k, v)
    assert m2.to_dict() == d2
    assert snapshot_m.to_dict() == snapshot_d   # the branch point is untouched
    assert m.to_dict() == d                     # the original path is untouched


# --- Record integration: identical behaviour, new representation ------

def test_record_from_plain_dict_unchanged_api():
    r = Record({"b": 2, "a": 1})
    assert r.fields["a"] == 1 and r.fields["b"] == 2
    assert set(r.fields) == {"a", "b"}
    assert len(r.fields) == 2
    assert sorted(r.fields.items()) == [("a", 1), ("b", 2)]


def test_record_from_pmap_no_extra_copy():
    m = PMap.from_dict({"a": 1})
    r = Record(m)
    assert r.fields is m                        # passed straight through


def test_guest_put_chain_via_language_builtins():
    """The real path this round optimizes: `put` called many times in a
    row, exactly the store-passing pattern self_eval.lang/self_host.lang
    use for their guest environment record."""
    src = """
let store = @{}
fn build(s, i) {
    if i >= 200 {
        s
    } else {
        build(put(s, "k" + str(i), i * 2), i + 1)
    }
}
let final = build(store, 0)
let result = get(final, "k150")
check "grew to 200 fields": len(keys(final)) == 200
check "old field survives": get(final, "k0") == 0
check "new field readable": result == 300
"""
    interp, env, out = run(src)
    assert env.get("result").payload == 300
    assert all(c["ok"] for c in interp.checks), interp.checks


def test_put_existing_key_preserves_history_of_prior_version():
    """A record obtained mid-chain (before a later `put` on the same key)
    must still report its OWN, older value — the persistent-map analogue
    of `WList`'s "a view only ever reads buf[:n]" guarantee."""
    src = """
let r0 = @{a: 1}
let r1 = put(r0, "a", 2)
let r2 = put(r1, "a", 3)
check "r0 still 1": r0.a == 1
check "r1 still 2": r1.a == 2
check "r2 is 3": r2.a == 3
"""
    interp, env, out = run(src)
    assert all(c["ok"] for c in interp.checks), interp.checks


def test_merge_still_right_wins_on_conflict():
    base = 'let m = merge(@{a: 1, b: 2}, @{b: 99, c: 3})\nlet result = '
    assert val(base + 'm.b').payload == 99
    assert val(base + 'm.c').payload == 3
    assert val(base + 'm.a').payload == 1


def test_three_way_parity_on_a_long_put_chain():
    src = """
fn build(s, i) {
    if i >= 60 {
        s
    } else {
        build(put(s, "f" + str(i), i), i + 1)
    }
}
let result = get(build(@{}, 0), "f42")
check "f42 is 42": result == 42
"""
    assert_three_way(src)


def test_record_literal_still_captures_input_order_for_provenance():
    """PMap's own iteration is key-ordered (alphabetical), but the `record`
    node's provenance `inputs` are captured from the literal's DECLARED
    order before `Record(...)` is even constructed (interp.py `f_record`/
    `eval_RecordLit`, both build `inputs` from the plain-dict `fields`
    variable, not from any Record/PMap) — unaffected by the new internal
    representation. `z` is declared (and so evaluated/wired as an input)
    before `a`, even though `a` sorts first as a key."""
    from whence.values import render_why
    interp, env, out = run("let r = @{z: 100, a: 200}\nlet w = why r")
    text = render_why(env.get("w").payload.root)
    assert text.index("100 ← literal") < text.index("200 ← literal")
