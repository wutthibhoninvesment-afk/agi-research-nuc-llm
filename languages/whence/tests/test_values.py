from whence.values import (wlist,
    Prov, Value, Miss, Record, Explanation,
    show_payload, full_show, leaf, render_why,
)


def test_show_bool_before_int():
    assert show_payload(True) == "true"
    assert show_payload(False) == "false"
    assert show_payload(1) == "1"


def test_show_string_quoted_and_truncated():
    assert show_payload("hi") == '"hi"'
    long = "x" * 100
    s = show_payload(long)
    assert s.startswith('"xxxx')
    assert "…" in s and len(s) < 60


def test_show_list_preview():
    xs = wlist(leaf("literal", "", 1, i) for i in range(10))
    s = show_payload(xs)
    assert s.startswith("[") and "…" in s


def test_show_record_sorted():
    r = Record({"b": leaf("literal", "", 1, 2), "a": leaf("literal", "", 1, 1)})
    assert show_payload(r) == "@{a: 1, b: 2}"


def test_full_show_miss_lists_reasons():
    m = Miss(["a", "b"])
    assert full_show(m) == "miss: a; b"


def test_miss_dedup_keeps_order():
    m = Miss(["b", "a", "b", "c", "a"])
    assert m.reasons == ("b", "a", "c")


def test_render_leaf():
    assert render_why(Prov("literal", "", 3, (), "5")) == "5 ← literal  (line 3)"


def _chain(depth):
    node = Prov("literal", "", 1, (), "0")
    for i in range(depth):
        node = Prov("+", "", i + 2, (node,), str(i + 1))
    return node


def test_render_depth_cap():
    out = render_why(_chain(30), max_depth=5)
    assert "…" in out
    assert len(out.splitlines()) < 10


def test_render_node_budget():
    wide = Prov("list", "", 1, tuple(
        Prov("literal", "", 1, (), str(i)) for i in range(50)), "[…]")
    out = render_why(wide, max_nodes=10)
    assert "truncated" in out


def test_render_shared_node_marked():
    shared = Prov("+", "", 1, (Prov("literal", "", 1, (), "1"),), "2")
    root = Prov("*", "", 2, (shared, shared), "4")
    out = render_why(root)
    assert out.count("⟲ shown above") == 1


def test_explanation_full_show_renders():
    e = Explanation(Prov("literal", "", 1, (), "7"))
    assert "7 ← literal" in full_show(e)


def test_show_nesting_is_capped():
    from whence.values import leaf, Record
    v = leaf("literal", "", 1, wlist())
    for _ in range(3000):
        v = leaf("list", "", 1, wlist([v]))
    s = show_payload(v.payload)           # must not recurse 3000 deep
    assert s == "[[[[…]]]]"
    r = leaf("record", "", 1, Record({"a": leaf("literal", "", 1, Record({}))}))
    assert show_payload(r.payload) == "@{a: @{}}"
