import pytest

from whence.parser import parse, ParseError
from whence import ast_nodes as A


def first_expr(src):
    prog = parse(src)
    stmt = prog.stmts[0]
    assert isinstance(stmt, A.ExprStmt)
    return stmt.expr


def test_precedence_mul_over_add():
    e = first_expr("1 + 2 * 3")
    assert isinstance(e, A.Binary) and e.op == "+"
    assert isinstance(e.right, A.Binary) and e.right.op == "*"


def test_rescue_is_lowest():
    e = first_expr("a + 1 rescue 0")
    assert isinstance(e, A.Rescue)
    assert isinstance(e.left, A.Binary) and e.left.op == "+"


def test_rescue_left_assoc():
    e = first_expr("a rescue b rescue c")
    assert isinstance(e, A.Rescue) and isinstance(e.left, A.Rescue)


def test_comparison_does_not_chain():
    with pytest.raises(ParseError):
        parse("1 < 2 < 3")


def test_unary_layers():
    e = first_expr("not missed(x)")
    assert isinstance(e, A.Unary) and e.op == "not"
    assert isinstance(e.operand, A.Call)
    e = first_expr("why x + 1")  # unary binds tighter than +
    assert isinstance(e, A.Binary) and isinstance(e.left, A.Why)


def test_miss_literal():
    e = first_expr('miss "no data"')
    assert isinstance(e, A.MissLit)


def test_postfix_chain():
    e = first_expr("f(x)[0].name")
    assert isinstance(e, A.FieldAccess)
    assert isinstance(e.obj, A.Index)
    assert isinstance(e.obj.obj, A.Call)


def test_if_requires_else():
    with pytest.raises(ParseError) as ei:
        parse("if true { 1 }")
    assert "else" in str(ei.value)


def test_if_else_if_chain():
    e = first_expr("if a { 1 } else if b { 2 } else { 3 }")
    assert isinstance(e, A.If) and isinstance(e.otherwise, A.If)


def test_block_must_end_with_expression():
    with pytest.raises(ParseError) as ei:
        parse("fn f() { let x = 1 }")
    assert "end with an expression" in str(ei.value)


def test_empty_block_rejected():
    with pytest.raises(ParseError):
        parse("fn f() { }")


def test_duplicate_binding_same_block():
    with pytest.raises(ParseError) as ei:
        parse("let x = 1\nlet x = 2")
    assert "already bound" in str(ei.value)
    with pytest.raises(ParseError):
        parse("fn f() { 1 }\nlet f = 2")


def test_shadowing_in_inner_block_ok():
    parse("let x = 1\nlet y = { let x = 2\nx }")


def test_duplicate_params():
    with pytest.raises(ParseError):
        parse("fn f(a, a) { a }")


def test_duplicate_record_field():
    with pytest.raises(ParseError):
        parse("@{a: 1, a: 2}")


def test_fn_statement_vs_anonymous():
    prog = parse("fn f(x) { x }\nlet g = fn(x) { x }")
    assert isinstance(prog.stmts[0], A.FnDef)
    assert isinstance(prog.stmts[1].expr, A.FnExpr)


def test_check_needs_string_label():
    with pytest.raises(ParseError):
        parse("check foo: 1 == 1")
    prog = parse('check "adds": 1 + 1 == 2')
    assert isinstance(prog.stmts[0], A.Check)


def test_multiline_data_in_brackets():
    prog = parse("let xs = [\n  1,\n  2\n]")
    assert isinstance(prog.stmts[0].expr, A.ListLit)


def test_parse_error_reports_position():
    with pytest.raises(ParseError) as ei:
        parse("let = 5")
    assert ei.value.line == 1
