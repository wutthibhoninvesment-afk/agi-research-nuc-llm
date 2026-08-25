"""swe.killers: package isolation, canonical behaviour, killer search, rendering."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swe.fuzz import WHENCE_ROOT
from swe.killers import (load_whence, behaviour, find_killer, corpus, render_tests,
                         Killer, CANONICAL_HELPER_SRC)
from swe.mutation import generate


def test_load_whence_isolates_packages():
    a = load_whence(WHENCE_ROOT, "a")
    b = load_whence(WHENCE_ROOT, "b")
    assert a["Interpreter"] is not b["Interpreter"]
    assert a["Interpreter"].__module__ == "whence_a.interp"


def test_behaviour_is_plain_data_and_stable():
    pkg = load_whence(WHENCE_ROOT, "beh")
    src = 'let x = 1 + 2\ncheck "three": x == 3\nprint(x)\nlet m = 1 / 0\n'
    b = behaviour(pkg, src)
    assert b["kind"] == "ok" and b["out"] == ["3"]
    assert b["checks"] == [["three", True]]
    assert b["vals"]["x"] == "3" and b["vals"]["m"].startswith("miss:")
    assert behaviour(pkg, src) == b
    assert behaviour(pkg, "let = \n")["kind"] == "ParseError"
    assert behaviour(pkg, "let p = " + "(" * 400 + "1" + ")" * 400)["kind"] == "ParseError"
    from tests.synthetic_crash import install as install_crash, CRASH_PROGRAM
    assert behaviour(pkg, CRASH_PROGRAM)["kind"] == "ok"
    install_crash("whence_beh.interp", WHENCE_ROOT)
    assert behaviour(pkg, CRASH_PROGRAM)["kind"] == "crash"


def test_find_killer_for_a_real_semantic_mutant():
    with open(os.path.join(WHENCE_ROOT, "whence", "interp.py")) as f:
        src = f.read()
    # string concat in binop: since v0.6 two strings take the fast path
    # `Prov(op, "concat", line, (left, right), _LAZY, l + r)` — anchor on
    # THAT site (the old general-path concat line is unreachable for two
    # strings now; round-20 re-anchor, process rule 7). The arith mutant
    # turns `+` into `-`, which crashes on strings.
    m = next(m for m in generate(src, "whence/interp.py")
             if m.op == "arith"
             and "(left, right), _LAZY, l + r)" in src.splitlines()[m.lineno - 1])
    orig = load_whence(WHENCE_ROOT, "orig")
    progs = ['let a = "x" + "y"\n', "let b = 1\n"]
    k = find_killer(m, progs, orig, WHENCE_ROOT)
    assert k.found and k.tried == 1
    # the shrinker may have minimised the literals; the sum must still differ
    assert k.expected["vals"]["a"] != k.mutant_behaviour.get("vals", {}).get("a")
    assert k.mutant_behaviour != k.expected


def test_find_killer_reports_no_killer_for_equivalent_change():
    with open(os.path.join(WHENCE_ROOT, "whence", "interp.py")) as f:
        src = f.read()
    m = generate(src, "whence/interp.py")[0]
    m.source = src + "\n_UNUSED = 1\n"          # behaviourally equivalent
    orig = load_whence(WHENCE_ROOT, "orig2")
    k = find_killer(m, ["let a = 1\n", "print(2)\n"], orig, WHENCE_ROOT)
    assert not k.found and k.tried == 2


def test_render_tests_is_valid_python_and_idempotent():
    m = generate("x = 1 < 2\n", "f.py")[0]
    k = Killer(m, "let a = 1\n", {"kind": "ok", "out": [], "checks": [], "vals": {"a": "1"}},
               {"kind": "ok", "out": [], "checks": [], "vals": {"a": "2"}}, 1, 0.1)
    text = render_tests([k])
    compile(text, "gen", "exec")
    assert CANONICAL_HELPER_SRC.strip() in text
    assert text.count("def test_kill_") == 1
    assert render_tests([k], existing=text) == text     # no duplicate on re-run


def test_corpus_includes_examples_and_fuzz():
    progs = corpus(0, 5, WHENCE_ROOT)
    assert len(progs) > 5 and any("check" in p for p in progs)


def test_generated_file_compiles_with_hostile_docstring_text():
    """Round-6 regression: a behaviour ending in a double quote fused with the
    closing triple quote and made the whole generated module a SyntaxError."""
    import ast
    from types import SimpleNamespace
    from swe.killers import render_tests as write_tests, docstring_safe, TEST_HEADER

    hostile = {"vals": {"v": 'miss: cannot order <why> and ["x…"] (line 1)"'}}
    mutant = SimpleNamespace(id="values.py:1:const#0", description='"quoted" \\ desc\nnext', lineno=1)
    killer = SimpleNamespace(found=True, mutant=mutant, mutant_behaviour=hostile,
                             program='let v = "q"\n', expected={"kind": "ok"})
    body = write_tests([killer], TEST_HEADER)
    ast.parse(body)                                   # must compile
    assert '"' not in docstring_safe('a"b\\c\nd') and docstring_safe("x" * 500) == "x" * 120
