"""v0.7 (round 24): F1 — direct calls to never-shadowed plain builtins
compile inline (so enclosing subtrees compile too); F2 — non-tail calls to
closures whose whole body compiled fast run with no generator frame.

Semantic anchors:
  - Both features are invisible: fast=True and fast=False agree node for
    node (op/detail/count and payloads) on every program here.
  - Shadowing a builtin name ANYWHERE in the program disables F1 for that
    name (static gate); shadowing introduced by a LATER exec_stmt after a
    call site already compiled is caught by the runtime identity check,
    which falls back to full dynamic call semantics.
  - Arity misses, depth misses and peak_depth are byte-identical to the
    trampoline path.
"""

from whence.interp import Interpreter
from whence.parser import parse
from whence.values import Miss, diverge


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


def assert_modes_agree(src, names):
    _, fast_env = run(src)
    _, slow_env = run(src, fast=False)
    for name in names:
        a, b = fast_env.get(name), slow_env.get(name)
        assert diverge(a, b) == [], (name, diverge(a, b))


# --- F1: builtin calls compile inline ---------------------------------------

def test_builtin_call_subtree_compiles():
    # pre-v0.7 `len(...)` blocked compilation of the whole let-expression
    interp, env = run("let result = len([1, 2, 3]) + 1")
    assert env.get("result").payload == 4
    assert interp.fast_hits > 0


def test_builtin_call_nodes_match_slow_path():
    assert_modes_agree(
        'let a = len([1, 2]) + len("xyz")\n'
        'let b = contains("abc", "b")\n'
        'let c = num("41") + abs(0 - 1)\n'
        'let d = put(@{x: 1}, "y", get(@{x: 1}, "x"))\n'
        'let e = has(@{k: 1}, "k")\n', "abcde")


def test_builtin_arity_miss_identical():
    fast = val('let result = contains("a")')
    slow = val('let result = contains("a")', fast=False)
    assert is_miss(fast) and reasons(fast) == reasons(slow)
    assert "contains expects 2 args, got 1" in reasons(fast)


def test_generator_builtins_never_inline():
    # map/filter/fold/find re-enter guest code: their call sites must stay
    # off the compiled path (the whole subtree stays uncompiled)
    src = "let result = fold(fn(a, x) { a + x }, 0, range(5))"
    p = parse(src)
    interp = Interpreter()
    interp._collect_shadowed(p)
    node = p.stmts[0].expr
    assert interp.compile_fast(node) is False
    assert val(src).payload == 10


def test_shadowed_builtin_name_disables_inline():
    # `len` is bound as a user fn: the static gate must keep every len call
    # dynamic, and late binding must behave exactly like the slow path
    src = ('fn f(s) { len(s) }\n'
           'fn len(x) { 42 }\n'
           'let result = f("abc")\n')
    fast, slow = val(src), val(src, fast=False)
    assert fast.payload == 42 and slow.payload == 42
    assert_modes_agree(src, ["result"])


def test_param_shadowing_builtin():
    src = 'fn g(len) { len(3) }\nlet result = g(5)'
    fast, slow = val(src), val(src, fast=False)
    assert is_miss(fast) and reasons(fast) == reasons(slow)
    assert "not callable" in reasons(fast)


def test_stale_shadow_falls_back_at_runtime():
    # A call site compiled with the builtin inline, THEN a later exec_stmt
    # shadows the name: the identity check must reroute to the new binding.
    interp = Interpreter()
    from whence.interp import Env
    env = Env(interp.globals)
    steps = [
        'fn f(s) { len(s) }',
        'let a = f("xy")',          # compiles len-inline, a == 2
        'fn len(q) { 42 }',         # shadow arrives AFTER compilation
        'let b = f("xy")',          # f's body must now see the user len
    ]
    for s in steps:
        for stmt in parse(s).stmts:
            interp.exec_stmt(stmt, env)
    assert env.get("a").payload == 2
    assert env.get("b").payload == 42


def test_stale_shadow_matches_slow_path():
    # same staged program, slow path is the semantic reference
    def staged(fast):
        interp = Interpreter(fast=fast)
        from whence.interp import Env
        env = Env(interp.globals)
        for s in ('fn f(s) { len(s) }', 'let a = f("xy")',
                  'fn len(q) { 42 }', 'let b = f("xy")'):
            for stmt in parse(s).stmts:
                interp.exec_stmt(stmt, env)
        return env.get("a").payload, env.get("b").payload
    assert staged(True) == staged(False) == (2, 42)


# --- F2: frameless closure calls --------------------------------------------

def test_frameless_call_nodes_match_slow_path():
    assert_modes_agree(
        'fn add(a, b) { a + b }\n'
        'fn pick(r) { if r.x > 1 { r.x } else { 0 - r.x } }\n'
        'let a = add(1, 2)\n'
        'let b = add(add(1, 1), add(2, 2))\n'
        'let c = pick(@{x: 5}) + pick(@{x: 1})\n', "abc")


def test_frameless_call_node_shape():
    v = val("fn add(a, b) { a + b }\nlet result = add(1, 2)")
    node = v.inputs[0]
    assert node.op == "call" and node.detail == "add" and node.count == 1
    plus = node.inputs[0]
    assert plus.op == "+"
    # the + node's inputs are the `arg` wrappers
    assert [n.op for n in plus.inputs] == ["arg", "arg"]
    assert [n.detail for n in plus.inputs] == ["a", "b"]


def test_frameless_arity_miss_identical():
    src = "fn add(a, b) { a + b }\nlet result = add(1)"
    fast, slow = val(src), val(src, fast=False)
    assert is_miss(fast) and reasons(fast) == reasons(slow)
    assert "add expects 2 args, got 1" in reasons(fast)


def test_frameless_depth_miss_identical():
    # `one(y) + 0` keeps the inner call NON-tail (a bare `one(y)` would be
    # a tail call, which is depth-free by design)
    src = ('fn one(x) { x + 1 }\n'
           'fn outer(y) { one(y) + 0 }\n'
           'let result = outer(1)\n')
    fast = val(src, max_depth=1)
    slow = val(src, max_depth=1, fast=False)
    assert is_miss(fast) and reasons(fast) == reasons(slow)
    assert "recursion too deep in one (depth 1)" in reasons(fast)


def test_frameless_peak_depth_matches():
    src = ('fn one(x) { x + 1 }\n'
           'fn two(y) { one(y) + 1 }\n'
           'let result = two(3)\n')
    i_fast, _ = run(src)
    i_slow, _ = run(src, fast=False)
    assert i_fast.peak_depth == i_slow.peak_depth == 2
    assert val(src).payload == 5


def test_fold_element_calls_go_frameless():
    # the per-element fn calls of a generator builtin arrive as _Call
    # requests; a fast body must take the frameless path there too
    src = "let result = fold(fn(a, x) { a + x }, 0, range(100))"
    interp, env = run(src)
    assert env.get("result").payload == 4950
    assert_modes_agree(src, ["result"])


def test_f1_unlocks_f2():
    # lookup's body is only fast because has/get compiled inline (F1);
    # then lookup's own call sites are frameless (F2)
    src = ('fn lookup(env, name) {\n'
           '  if has(env, name) { get(env, name) }\n'
           '  else { miss ("unbound " + name) }\n'
           '}\n'
           'let e = @{a: 1, b: 2}\n'
           'let hit = lookup(e, "b")\n'
           'let mv = lookup(e, "zz")\n')
    interp = Interpreter()
    p = parse(src)
    interp._collect_shadowed(p)
    body = p.stmts[0].body
    assert interp.compile_fast(body)          # F1 made the body compile
    assert_modes_agree(src, ["hit", "mv"])


def test_frameless_call_with_miss_arg():
    src = 'fn add(a, b) { a + b }\nlet result = add(1, miss "bad")'
    fast, slow = val(src), val(src, fast=False)
    assert is_miss(fast) and reasons(fast) == reasons(slow)


def test_recursive_fn_body_never_framless():
    # fib's body contains user calls: F2 must not apply, results unchanged
    src = ("fn fib(n) { if n < 2 { n } else { fib(n - 1) + fib(n - 2) } }\n"
           "let result = fib(12)")
    assert_modes_agree(src, ["result"])
    assert val(src).payload == 144


def test_single_frame_deferred_if_is_not_dropped():
    # v0.4–v0.6 lossiness fixed in v0.7: a tail-position `if` whose taken
    # branch tail-called a BUILTIN deferred its decision into the tail-loop
    # bookkeeping; with merged == 1 the decision then vanished from the
    # history. Both paths must now record call -> if -> builtin-result.
    src = ('fn f(x) { if x > 0 { len("ab") } else { 0 } }\n'
           'let result = f(1)\n')
    for fast in (True, False):
        v = val(src, fast=fast)
        call = v.inputs[0]
        assert call.op == "call" and call.detail == "f", fast
        iff = call.inputs[0]
        assert iff.op == "if" and iff.detail == "took then-branch", fast
        assert iff.inputs[0].op == "len", fast
    assert_modes_agree(src, ["result"])


def test_tail_loops_unchanged():
    # tail calls must still merge into one `call ×N` node, not N frameless calls
    src = ("fn go(i, acc) { if i == 0 { acc } else { go(i - 1, acc + i) } }\n"
           "let result = go(6, 0)")
    v = val(src)
    node = v.inputs[0]
    assert node.op == "call" and node.count == 7
    assert_modes_agree(src, ["result"])


# --- shared-AST determinism (round 25 fix) ---------------------------------
# The v0.7 compiled-builtin closure is cached on the AST node, which two
# fresh interpreters may share (the harness determinism oracle does exactly
# this). Round 24's closure captured the COMPILING interpreter, so the
# second run's print output landed in the first interpreter's sink and the
# `p is b` identity gate always failed cross-interpreter (fresh Builtin
# objects per interpreter). These tests pin the fixed contract.

def _run_ast(program, out):
    interp = Interpreter(out=out.append)
    from whence.interp import Env
    env = Env(interp.globals)
    for stmt in program.stmts:
        interp.exec_stmt(stmt, env)
    return interp, env


def test_shared_ast_two_interpreters_output_isolated():
    program = parse("fn add(a, b) { a + b }\n"
                    "let s = fold(add, 0, range(1, 51))\n"
                    "print(s)\nprint(1 + 1)\n")
    out1, out2 = [], []
    i1, e1 = _run_ast(program, out1)
    i2, e2 = _run_ast(program, out2)
    assert out1 == ["1275", "2"], out1
    assert out2 == ["1275", "2"], out2
    assert e1.get("s").payload == e2.get("s").payload == 1275


def test_shared_ast_second_interpreter_keeps_fast_path():
    # singleton builtins: the identity gate must hold for interpreter 2 too,
    # so its compiled-builtin calls stay on the fast path
    program = parse("let a = len("
                    '"abc") + 1\nprint(a)\n')
    out1, out2 = [], []
    i1, _ = _run_ast(program, out1)
    i2, _ = _run_ast(program, out2)
    assert out1 == out2 == ["4"]
    assert i1.fast_hits > 0
    assert i2.fast_hits > 0


def test_shared_ast_checks_recorded_per_interpreter():
    program = parse("let x = 2 + 2\ncheck \"four\": x == 4\n")
    out1, out2 = [], []
    i1, _ = _run_ast(program, out1)
    i2, _ = _run_ast(program, out2)
    assert len(i1.checks) == 1 and i1.checks[0]["ok"]
    assert len(i2.checks) == 1 and i2.checks[0]["ok"]


def test_builtin_singletons_shared_across_interpreters():
    a, b = Interpreter(), Interpreter()
    assert a.globals.get("len").value is b.globals.get("len").value
    assert a.globals.get("print").value is b.globals.get("print").value
