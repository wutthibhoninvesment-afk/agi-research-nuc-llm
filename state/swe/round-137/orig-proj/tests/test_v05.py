"""v0.5 (round 14): `get` / `put` (records as data) and `find` (first match).

These exist for self-hosting: a metacircular evaluator's environment is a
record keyed by names it only knows at runtime. The semantic anchors:
  - get(r, "a") is indistinguishable from r.a — same node, same misses.
  - put(r, n, v) is merge(r, @{n: v}) with a dynamic key; the original
    record is unchanged (no mutation, ever).
  - find passes the element through like xs[i] (access does not launder).
"""

from whence.interp import Interpreter
from whence.values import Miss, Record


def run(src, **kw):
    interp = Interpreter(**kw)
    env = interp.run(src)
    return interp, env


def val(src, **kw):
    return run(src, **kw)[1].get("result")


def is_miss(v):
    return isinstance(v.payload, Miss)


def reasons(v):
    return " | ".join(v.payload.reasons)


# --- get ---------------------------------------------------------------------

def test_get_reads_a_field():
    v = val('let r = @{a: 1, b: 2}\nlet result = get(r, "b")')
    assert v.payload == 2


def test_get_is_field_access_same_node():
    # pass-through: get returns the very node the record holds, like r.a
    # (each `let` adds its own wrapper — round 4's lesson — so compare
    # the wrapped node, not the binding)
    _, env = run('let r = @{a: 1 + 2}\nlet via_get = get(r, "a")\n'
                 'let via_dot = r.a')
    assert env.get("via_get").inputs[0] is env.get("via_dot").inputs[0]


def test_get_absent_field_matches_dot_wording():
    v = val('let result = get(@{a: 1}, "z")')
    assert is_miss(v)
    assert "no field 'z'" in reasons(v)


def test_get_non_record():
    v = val('let result = get([1, 2], "a")')
    assert is_miss(v)
    assert "cannot access .a" in reasons(v)


def test_get_non_string_name():
    v = val('let result = get(@{a: 1}, 3)')
    assert is_miss(v)
    assert "field name must be a string" in reasons(v)


def test_get_propagates_record_miss():
    v = val('let bad = num("3O")\nlet result = get(bad, "a")')
    assert is_miss(v)
    assert "cannot parse" in reasons(v)


def test_get_propagates_name_miss():
    v = val('let result = get(@{a: 1}, num("x"))')
    assert is_miss(v)


def test_get_field_holding_a_miss_returns_it():
    # a bound miss is a present value, not an absent field
    v = val('let r = @{a: num("3O")}\nlet result = get(r, "a")')
    assert is_miss(v)
    assert "cannot parse" in reasons(v)


# --- put ---------------------------------------------------------------------

def test_put_adds_a_field():
    v = val('let result = put(@{a: 1}, "b", 2)')
    assert isinstance(v.payload, Record)
    assert v.payload.fields["b"].payload == 2
    assert v.payload.fields["a"].payload == 1


def test_put_replaces_a_field():
    v = val('let result = (put(@{a: 1}, "a", 9)).a')
    assert v.payload == 9


def test_put_leaves_original_unchanged():
    _, env = run('let r = @{a: 1}\nlet r2 = put(r, "a", 9)\n'
                 'let old = r.a')
    assert env.get("old").payload == 1
    assert env.get("r2").payload.fields["a"].payload == 9


def test_put_provenance_node():
    v = val('let r = @{a: 1}\nlet result = put(r, "b", 5)')
    # let-wrapper around the put node
    assert v.op == "let"
    put_node = v.inputs[0]
    assert put_node.op == "put" and put_node.detail == "b"
    assert len(put_node.inputs) == 2  # (record, value)


def test_put_on_empty_record():
    v = val('let result = (put(@{}, "x", 1)).x')
    assert v.payload == 1


def test_put_miss_value_is_allowed():
    # records hold misses (literals can too); only r and the key propagate
    v = val('let result = get(put(@{}, "x", num("3O")), "x")')
    assert is_miss(v)
    assert "cannot parse" in reasons(v)


def test_put_non_record():
    v = val('let result = put([1], "a", 2)')
    assert is_miss(v)
    assert "put needs a record" in reasons(v)


def test_put_non_string_name():
    v = val('let result = put(@{}, 1, 2)')
    assert is_miss(v)
    assert "field name must be a string" in reasons(v)


def test_put_dynamic_key_equals_merge_static():
    _, env = run('let a = put(@{x: 1}, "y", 2)\n'
                 'let b = merge(@{x: 1}, @{y: 2})\n'
                 'let result = a == b')
    assert env.get("result").payload is True


# --- find --------------------------------------------------------------------

def test_find_first_match():
    v = val('let result = find(fn(x) { x > 2 }, [1, 2, 3, 4])')
    assert v.payload == 3


def test_find_passes_element_through():
    # the found element keeps its own provenance node (like xs[i])
    _, env = run('let xs = [1 + 1, 2 + 2]\n'
                 'let direct = xs[1]\n'
                 'let found = find(fn(x) { x == 4 }, xs)')
    assert env.get("found").inputs[0] is env.get("direct").inputs[0]


def test_find_no_match_is_a_miss():
    v = val('let result = find(fn(x) { x > 99 }, [1, 2])')
    assert is_miss(v)
    assert "no element matched" in reasons(v)


def test_find_empty_list_is_a_miss():
    v = val('let result = find(fn(x) { true }, [])')
    assert is_miss(v)


def test_find_predicate_non_bool():
    v = val('let result = find(fn(x) { x }, [1])')
    assert is_miss(v)
    assert "must return true/false" in reasons(v)


def test_find_predicate_miss_propagates():
    # like filter: the ORIGINAL reason survives; "predicate missed" is the
    # node's detail, not a fabricated new reason
    v = val('let result = find(fn(x) { x + num("q") > 0 }, [1])')
    assert is_miss(v)
    assert "cannot parse" in reasons(v)
    assert v.inputs[0].op == "find" and v.inputs[0].detail == "predicate missed"


def test_find_non_list():
    v = val('let result = find(fn(x) { true }, "abc")')
    assert is_miss(v)
    assert "find needs a list" in reasons(v)


def test_find_with_builtin_predicate():
    v = val('let xs = [1, num("3O"), 3]\n'
            'let result = find(missed, xs)')
    assert is_miss(v)          # the found *element* is the miss — correct
    assert "cannot parse" in reasons(v)


def test_find_propagates_list_miss():
    v = val('let result = find(fn(x) { true }, num("3O"))')
    assert is_miss(v)


def test_find_stops_at_first_match():
    # elements after the first match are never tested: a poisoned later
    # element cannot fail the find
    v = val('let xs = [1, 5, num("3O")]\n'
            'let result = find(fn(x) { x > 2 }, xs)')
    assert v.payload == 5


# --- fast/slow differential on the new builtins -------------------------------

CORPUS = [
    'let result = get(put(@{a: 1}, "b", 2), "b")',
    'let result = find(fn(x) { x % 2 == 0 }, range(1, 9))',
    'let result = str(get(@{a: 1}, "z"))',
    'let result = put(@{}, "k", find(fn(x) { x > 1 }, [1, 2]))',
]


def test_new_builtins_same_on_both_paths():
    for src in CORPUS:
        fast = Interpreter(fast=True)
        slow = Interpreter(fast=False)
        vf = fast.run(src).get("result")
        vs = slow.run(src).get("result")
        assert type(vf.payload) is type(vs.payload), src
        if not isinstance(vf.payload, (Miss, Record)):
            assert vf.payload == vs.payload, src
