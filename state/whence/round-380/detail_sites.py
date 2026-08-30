"""Round 380 — how many `mk_miss` call sites set `detail`, and where it bites.

`tests/test_v30.py::test_a_miss_nodes_detail_is_recovered_from_its_reason`
(round 378) asserts:

    assert "detail=" not in src, "a mk_miss call now overrides `detail`"

`mk_miss(reason, line, op, detail="", inputs=())` — `detail` is the FOURTH
POSITIONAL parameter.  The grep is true; the property it stands in for is
not.  This counts the call sites by AST, and separates the ones whose node
the guest evaluator BUILDS ITSELF (where the guest label carries the detail
and nothing is lost) from the ones it DELEGATES to the host (where
`guest_detail`'s reasons()-recovery answers with the reason instead).
"""
import ast
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
ROOT = os.path.join(REPO, "languages", "whence")


def mk_miss_sites(path):
    """(lineno, op_literal_or_None, sets_detail) for every mk_miss call."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)
        if name != "mk_miss":
            continue
        sets = len(n.args) >= 4 or any(k.arg == "detail" for k in n.keywords)
        op = None
        if len(n.args) >= 3 and isinstance(n.args[2], ast.Constant):
            op = n.args[2].value
        out.append((n.lineno, op, sets, ast.unparse(n)))
    return out


if __name__ == "__main__":
    path = os.path.join(ROOT, "whence", "interp.py")
    sites = mk_miss_sites(path)
    setting = [s for s in sites if s[2]]
    print("mk_miss call sites in whence/interp.py : %d" % len(sites))
    print("  ... that SET a detail                : %d" % len(setting))
    print("  ... spelled `detail=`                : %d"
          % open(path, encoding="utf-8").read().count("detail="))
    by_op = {}
    for ln, op, _, _ in setting:
        by_op.setdefault(op, []).append(ln)
    print("\n  op         n   lines")
    for op in sorted(by_op, key=lambda k: (k is None, k)):
        print("  %-10s %-3d %s" % (op, len(by_op[op]),
                                   ", ".join(str(x) for x in
                                             sorted(by_op[op]))))
