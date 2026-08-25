"""Provenance as data: `steps`, `at`, `blame`, and payload-retaining Prov."""

from whence.interp import Interpreter
from whence.values import (Miss, Record, Prov, leaf, derived, mk_miss,
                           walk_steps, find_step, is_origin_miss)


def run(src):
    interp = Interpreter()
    return interp, interp.run(src)


def val(src, name="result"):
    _, env = run(src)
    return env.get(name).payload


def field(rec, name):
    return rec.fields[name].payload


GROW = """
let base = 40
let rate = 0.05
fn grow(amount, r) { amount + amount * r }
let after1 = note("year 1", grow(base, rate))
let after2 = note("year 2", grow(after1, rate))
"""


# --- Prov retains its payload ------------------------------------------------

def test_prov_carries_value():
    v = derived("+", "", 1, (), 7)
    assert v.prov.value == 7
    m = mk_miss("boom", 2, "op")
    assert isinstance(m.prov.value, Miss)


def test_prov_label():
    assert Prov("let", "x", 1).label() == "let x"
    assert Prov("+", "", 1).label() == "+"
    assert Prov("", "only detail", 1).label() == "only detail"


def test_walk_steps_preorder_dedup():
    a = Prov("literal", "", 1, (), "1", 1)
    b = Prov("+", "", 2, (a, a), "2", 2)
    root = Prov("let", "x", 3, (b,), "2", 2)
    got = [(n.label(), d) for n, d in walk_steps(root)]
    assert got == [("let x", 0), ("+", 1), ("literal", 2)]


def test_find_step_is_breadth_first_nearest_first():
    old = Prov("note", "k", 1, (), "1", 1)
    mid = Prov("*", "", 2, (old,), "2", 2)
    new = Prov("note", "k", 3, (mid,), "3", 3)
    assert find_step(new, "note k") is new
    assert find_step(new, "*") is mid
    assert find_step(new, "zzz") is None


def test_is_origin_miss():
    ok = Prov("literal", "", 1, (), "1", 1)
    origin = mk_miss("bad", 1, "num", inputs=(ok,)).prov
    downstream = Prov("+", "", 2, (origin, ok), "miss", Miss(["x"]))
    assert is_origin_miss(origin)
    assert not is_origin_miss(downstream)
    assert not is_origin_miss(ok)


# --- steps -----------------------------------------------------------------

def test_steps_returns_records_root_first():
    p = val(GROW + "let result = steps(after2)")
    from whence.values import WList
    assert isinstance(p, WList) and len(p) > 10
    first = p[0].payload
    assert isinstance(first, Record)
    assert field(first, "op") == "let" and field(first, "detail") == "after2"
    assert field(first, "depth") == 0 and field(first, "line") == 6
    assert set(first.fields) == {"op", "detail", "line", "show", "depth",
                                 "inputs", "count", "value"}


def test_steps_value_field_is_live_history():
    p = val(GROW + "let result = steps(after2)")
    lets = [s.payload for s in p if field(s.payload, "op") == "let"]
    names = [field(s, "detail") for s in lets]
    assert names[:2] == ["after2", "after1"]
    v = lets[1].fields["value"]
    assert v.payload == 42.0 and v.prov.op == "let" and v.prov.detail == "after1"


def test_steps_accepts_why_or_value():
    src = GROW + "let a = len(steps(after2))\nlet result = a == len(steps(why after2))"
    assert val(src) is True


def test_steps_is_foldable_in_whence():
    src = GROW + """
let notes = filter(fn(s) { s.op == "note" }, steps(after2))
let result = map(fn(s) { s.detail }, notes)
"""
    p = val(src)
    assert [e.payload for e in p] == ["year 2", "year 1"]


def test_steps_on_miss_works():
    p = val("let m = 1 / 0\nlet result = steps(m)")
    assert field(p[0].payload, "op") == "let"     # the `let m` wrapper
    assert field(p[1].payload, "op") == "/"
    assert isinstance(p[1].payload.fields["value"].payload, Miss)


def test_steps_of_a_step_record_points_at_the_node():
    src = GROW + "let s = steps(after2)[3]\nlet result = why s"
    _, env = run(src)
    expl = env.get("result").payload
    # the record's provenance input is the node it reifies
    assert expl.root.op == "let" and expl.root.inputs[0].op == "step"


# --- at --------------------------------------------------------------------

def test_at_by_label_returns_historic_value():
    assert val(GROW + 'let result = at(after2, "year 1")') == 42.0
    assert val(GROW + 'let result = at(after2, "let base")') == 40


def test_at_by_op_or_detail():
    assert val(GROW + 'let result = at(after2, "note")') == 44.1
    assert val(GROW + 'let result = at(after2, "rate")') == 0.05


def test_at_result_is_live_and_keeps_history():
    src = GROW + """
let past = at(after2, "year 1")
let result = past * 2
let shorter = len(steps(past)) < len(steps(after2))
"""
    _, env = run(src)
    assert env.get("result").payload == 84.0
    assert env.get("shorter").payload is True
    # the provenance of `past` is the historic node itself, wrapped by `let`
    past = env.get("past")
    assert past.prov.inputs[0].label() == "note year 1"


def test_at_unknown_step_is_miss():
    p = val(GROW + 'let result = at(after2, "nope")')
    assert isinstance(p, Miss)
    assert "no step named 'nope' in the history of 44.1" in p.reasons[0]


def test_at_bad_pattern_is_miss():
    p = val(GROW + "let result = at(after2, 3)")
    assert isinstance(p, Miss) and "at needs a string" in p.reasons[0]
    p = val(GROW + "let result = at(after2, 1 / 0)")
    assert isinstance(p, Miss) and "division by zero" in p.reasons[0]


def test_at_on_why_and_on_miss():
    assert val(GROW + 'let result = at(why after2, "year 1")') == 42.0
    # breadth-first: the nearer literal (1, depth 1) wins over "x" (depth 2)
    src = 'let m = num("x") + 1\nlet result = at(m, "literal")'
    assert val(src) == 1
    src = 'let m = num("x") + 1\nlet result = at(at(m, "num"), "literal")'
    assert val(src) == "x"


# --- blame -----------------------------------------------------------------

BLAME = """
fn parse_row(row) { note("parsed " + row.name, num(row.qty)) }
let rows = [@{name: "alpha", qty: "12"}, @{name: "beta", qty: "3O"},
            @{name: "gamma", qty: "7"}]
fn add(a, b) { a + b }
let total = fold(add, 0, map(parse_row, rows))
"""


def test_blame_finds_single_origin():
    p = val(BLAME + "let result = blame(total)")
    assert len(p) == 1
    culprit = p[0].payload
    assert field(culprit, "op") == "num"
    assert field(culprit, "line") == 2
    assert 'cannot parse "3O"' in field(culprit, "detail")


def test_blame_origin_value_travels_to_the_literal():
    p = val(BLAME + 'let result = at(blame(total)[0].value, "literal")')
    assert p == "3O"


def test_blame_finds_multiple_independent_origins():
    src = "let a = 1 / 0\nlet b = num(\"q\")\nlet c = a + b\nlet result = blame(c)"
    p = val(src)
    ops = sorted(field(s.payload, "op") for s in p)
    assert ops == ["/", "num"]


def test_blame_of_healthy_value_is_empty():
    assert val(GROW + "let result = blame(after2)") == []


def test_blame_of_unbound_name():
    p = val("let result = blame(nope)")
    assert field(p[0].payload, "op") == "name"


def test_blame_result_has_provenance_to_root():
    _, env = run(BLAME + "let result = blame(total)")
    v = env.get("result")
    assert v.prov.inputs[0].op == "blame"
    assert v.prov.inputs[0].detail == "1 origins"


# --- rendering fixes -------------------------------------------------------

def test_show_payload_long_string_keeps_closing_quote():
    from whence.values import show_payload
    s = show_payload("x" * 100)
    assert s.endswith('…"') and s.count('"') == 2


def test_full_show_renders_all_record_fields_and_list_items():
    from whence.values import full_show, Record
    rec = Record({k: leaf("literal", "", 1, i) for i, k in
                  enumerate("abcdefg")})
    out = full_show(rec)
    assert "g: 6" in out and "…" not in out
    from whence.values import wlist
    xs = wlist(leaf("literal", "", 1, i) for i in range(10))
    assert full_show(xs) == "[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]"
