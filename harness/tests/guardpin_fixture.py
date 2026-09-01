"""Round 413 — the synthetic project both guardpin test files run against.

One copy, imported by `test_guardpin.py` (fast: pure AST/text/registry
checks) and `test_swe_guardpin.py` (slow: real pytest subprocesses per
verdict). The split follows this repo's own tiering rule — the fast file has
no `test_swe_` prefix, so `run_tests_fast.sh` runs the cheap rot detector
(`the live registry still locates`) EVERY round instead of once per rotation.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swe import guardpin as G                                  # noqa: E402


MOD = '''\
"""A tiny module with a gate, a guard and a call nobody reads."""

RECORD = []


def exempt(tok):
    """The gate — one home for the rule."""
    if tok.startswith("<"):
        return "placeholder: a template"
    return None


def collect(tokens):
    out = []
    for t in tokens:
        # the gate is consulted here, and this comment must survive the edit
        if exempt(t) is not None:
            continue
        out.append(t)          # keep — it is a real token
    return out


def audit(n):
    if n < 0:
        raise ValueError("n must be >= 0")
    return n * 2


def log_it(x):
    RECORD.append(x)


def run(x):
    log_it(x)
    return x
'''

TEST_MOD = '''\
import io
import mod


def test_collect_skips_placeholders():
    assert mod.collect(["a", "<b>"]) == ["a"]


def test_collect_mentions_the_gate():
    """Structural: `collect` must CALL the gate. Text only."""
    src = io.open(mod.__file__, encoding="utf-8").read()
    body = src.split("def collect(")[1].split("\\ndef ")[0]
    assert "exempt(" in body


def test_audit_rejects_negative():
    try:
        mod.audit(-1)
    except ValueError:
        return
    raise AssertionError("audit accepted a negative n")


def test_audit_doubles():
    assert mod.audit(3) == 6


def test_run_returns_its_argument():
    assert mod.run(7) == 7
'''


def _project(tmp_path, extra_tests=""):
    root = tmp_path / "proj"
    (root / "tests").mkdir(parents=True)
    (root / "mod.py").write_text(MOD)
    (root / "tests" / "test_mod.py").write_text(TEST_MOD + extra_tests)
    (root / "tests" / "conftest.py").write_text(
        "import os, sys\n"
        "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n")
    return str(root)


def _pin(**kw):
    base = {"id": "T", "path": "mod.py", "func": "collect", "edit": "call_value",
            "target": "exempt", "becomes": "none",
            "test": "tests/test_mod.py::test_collect_skips_placeholders",
            "why": "fixture"}
    base.update(kw)
    return base


def _run(pins, root, **kw):
    return G.run_registry(pins, root=root, workers=1, timeout_s=120.0, **kw)


# ------------------------------------------------------------ locating -------

def test_symbolic_locator_finds_the_call_and_reports_its_line():
    mutated, note = G.apply_edit(MOD, _pin(keep_call=True))
    assert "exempt(t)" in mutated and note.endswith("(call kept, value discarded)")


def test_a_site_that_moved_is_unlocatable_not_silently_relocated():
    with pytest.raises(G.PinUnlocatable):
        G.apply_edit(MOD, _pin(target="gate_that_was_renamed"))
    with pytest.raises(G.PinUnlocatable):
        G.apply_edit(MOD, _pin(func="collect_all"))
    with pytest.raises(G.PinUnlocatable):
        G.apply_edit(MOD, _pin(occurrence=2))


def test_an_ambiguous_function_name_refuses_to_pick_one():
    src = MOD + "\n\nclass Other:\n    def collect(self, tokens):\n        return exempt(tokens)\n"
    with pytest.raises(G.PinUnlocatable) as e:
        G.apply_edit(src, _pin())
    assert "ambiguous" in str(e.value)


def test_a_dotted_locator_disambiguates_a_method():
    src = MOD + "\n\nclass Other:\n    def collect(self, tokens):\n        return exempt(tokens)\n"
    mutated, _ = G.apply_edit(src, _pin(func="Other.collect"))
    assert "return None" in mutated


# ------------------------------------------------------------ the edit -------

def test_the_call_value_edit_changes_exactly_one_line_and_keeps_the_comments():
    """The pin on the bug this module was born with.

    `_stmt_parents` first kept the OUTERMOST enclosing statement (ast.walk is
    breadth-first), so a two-token edit re-unparsed the whole `for` loop and
    deleted its comments. That is not a wrong answer, it is a wrong
    EXPERIMENT: a source-grep pin reads the very text the edit destroyed.
    """
    mutated, _ = G.apply_edit(MOD, _pin(keep_call=True))
    assert "# the gate is consulted here, and this comment must survive" in mutated
    assert "# keep — it is a real token" in mutated
    before, after = MOD.splitlines(), mutated.splitlines()
    assert len(before) == len(after)
    differing = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    assert len(differing) == 1, [before[i] for i in differing]
    assert after[differing[0]].strip() == "if (exempt(t), None)[1] is not None:"


def test_the_span_slice_is_utf8_byte_correct():
    """`col_offset` is a byte offset. A line with an em-dash before the call
    is off by two characters if the slice is done on the decoded string."""
    src = 'def f(x):\n    y = "— dash —" + str(exempt(x))\n    return y\n'
    mutated, _ = G.apply_edit(
        src, _pin(func="f", target="exempt", keep_call=True))
    assert mutated == 'def f(x):\n    y = "— dash —" + str((exempt(x), None)[1])\n    return y\n'


def test_keep_call_leaves_the_name_in_the_source_and_removing_it_does_not():
    kept, _ = G.apply_edit(MOD, _pin(keep_call=True))
    gone, _ = G.apply_edit(MOD, _pin(keep_call=False))
    collect_body = lambda s: s.split("def collect(")[1].split("\ndef ")[0]
    assert "exempt(" in collect_body(kept)
    assert "exempt(" not in collect_body(gone)


def test_becomes_true_and_false_are_available_and_unknown_ones_are_not():
    t, _ = G.apply_edit(MOD, _pin(becomes="true"))
    assert "if True is not None:" in t
    with pytest.raises(G.PinUnlocatable):
        G.apply_edit(MOD, _pin(becomes="empty_string"))


def test_drop_stmt_replaces_the_statement_with_pass():
    mutated, note = G.apply_edit(
        MOD, _pin(func="run", edit="drop_stmt", stmt_kind="expr", target="log_it"))
    assert "        pass\n        return x" not in mutated      # indentation kept
    assert "    pass\n    return x\n" in mutated and "log_it(x)" not in mutated
    assert "drop" in note


def test_drop_stmt_needs_the_kind_because_an_if_and_its_raise_both_match():
    both = G.find_stmt_sites(G.find_function(ast.parse(MOD), "audit"), "ValueError", "if")
    just_raise = G.find_stmt_sites(G.find_function(ast.parse(MOD), "audit"), "ValueError", "raise")
    assert len(both) == 1 and len(just_raise) == 1
    assert both[0].lineno < just_raise[0].lineno


def test_every_edit_still_parses():
    for pin in (_pin(keep_call=True), _pin(keep_call=False),
                _pin(func="run", edit="drop_stmt", stmt_kind="expr", target="log_it")):
        ast.parse(G.apply_edit(MOD, pin)[0])


# ------------------------------------------------------------ validation -----

def test_validate_rejects_the_registry_mistakes_that_would_score_silently():
    bad = [{"id": "A", "path": "m.py", "func": "f", "edit": "nope",
            "target": "g", "test": "t.py::x", "why": "w"},
           {"id": "A", "path": "m.py", "func": "f", "edit": "drop_stmt",
            "target": "g", "test": "t.py", "why": "w", "keep_call": True}]
    problems = "\n".join(G.validate(bad))
    for expected in ("unknown edit", "duplicate id", "stmt_kind",
                     "keep_call is meaningless", "pytest node id"):
        assert expected in problems


def test_run_registry_refuses_an_invalid_registry_rather_than_scoring_it(tmp_path):
    with pytest.raises(ValueError):
        _run([_pin(edit="nope")], _project(tmp_path))


def test_the_live_registry_validates_and_every_pin_still_locates():
    """The registry in `state/swe/` is a claim about THIS checkout."""
    root = G.REPO_ROOT
    pins = G.load_registry(os.path.join(root, G.DEFAULT_REGISTRY))
    assert G.validate(pins) == []
    for p in pins:
        src = io.open(os.path.join(root, p["path"]), encoding="utf-8").read()
        G.apply_edit(src, p)                    # raises if the site rotted


