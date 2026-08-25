"""Static triage of surviving mutants by the code they sit in (round 113).

A survivor is a test gap, a weak assertion, or an equivalent mutant — and
the mutation score lumps them together. Round 107's 132 survivors were
mostly neither: 48 `const` mutants, of which most bumped a STATISTICS
COUNTER (`self.fast_hits += 1`) or a HOST-FRAME BUDGET constant
(`HOST_RESERVE`, `cost = body.cdepth + 1`, `self._hleft -= 3`) — changes no
program's value, output or check can observe. Spending a corpus search or
$0.45 of model time on those is waste, and counting them against the suite
misstates what the suite is for.

This module classifies every survivor by the statement it sits in, keyed on
NAMES (the counter attributes, the budget identifiers) and on one syntactic
shape (`x is None` cache guards), and reports the score both ways: over
every mutant, and over the BEHAVIOURAL set (everything but `counter` and
`budget`). The classes are not "equivalent" verdicts — `oraclekill` can
still kill a counter mutant through the counters and a budget mutant
through the frame-charge oracle — they say which instrument can see the
mutant, so the campaign spends each instrument where it can pay.
"""
import ast

from .mutation import _sites

COUNTER_NAMES = ("fast_hits", "direct_hits", "direct_fallbacks", "peak_depth")
BUDGET_NAMES = ("HOST_RESERVE", "FAST_MAX_DEPTH", "GC_RELIEF_THRESHOLD", "FRAME_SLACK",
                "_hleft", "hleft", "cdepth", "cost", "extra", "gc_relief", "set_threshold")
CLASSES = ("counter", "budget", "none_guard", "error_message", "other")
NON_BEHAVIOURAL = ("counter", "budget")


class Site(object):
    __slots__ = ("index", "op", "line", "enclosing", "assign", "text", "kind")

    def __init__(self, index, op, line, enclosing, assign, text, kind):
        self.index = index
        self.op = op
        self.line = line
        self.enclosing = enclosing      # "Class.method" chain
        self.assign = assign            # assignment target text or ""
        self.text = text                # the smallest statement/test/decorator holding the node
        self.kind = kind

    def as_dict(self):
        return {"index": self.index, "op": self.op, "line": self.line, "enclosing": self.enclosing,
                "assign": self.assign, "text": self.text[:160], "class": self.kind}


def _parents(tree):
    parent = {}
    for n in ast.walk(tree):
        for ch in ast.iter_child_nodes(n):
            parent[id(ch)] = n
    return parent


_HEAD_FIELDS = {ast.If: ("test",), ast.While: ("test",), ast.For: ("target", "iter"),
                ast.FunctionDef: ("args", "decorator_list", "returns"),
                ast.ClassDef: ("bases", "keywords", "decorator_list"),
                ast.With: ("items",), ast.Try: ()}


def _field_of(parent, child):
    for name, val in ast.iter_fields(parent):
        if val is child:
            return name
        if isinstance(val, list) and any(v is child for v in val):
            return name
    return None


def describe(tree, node, parent):
    """(enclosing def chain, assignment target, statement text) for a node."""
    chain, assign, text = [], "", None
    if isinstance(node, (ast.If, ast.While)):
        text = ast.unparse(node.test)        # ifneg: the condition, never the body
    cur = node
    while True:
        p = parent.get(id(cur))
        if p is None:
            break
        if text is None and isinstance(p, ast.stmt):
            field = _field_of(p, cur)
            if type(p) in _HEAD_FIELDS and field in _HEAD_FIELDS[type(p)]:
                text = ast.unparse(cur)          # the head part of a compound statement
            elif isinstance(p, (ast.If, ast.While, ast.For, ast.FunctionDef, ast.ClassDef,
                                ast.With, ast.Try)):
                text = ast.unparse(cur)          # defensive: never the whole compound body
            else:
                text = ast.unparse(p)            # a simple statement: the whole line
        if isinstance(p, (ast.Assign, ast.AugAssign, ast.AnnAssign)) and not assign:
            t = p.targets[0] if isinstance(p, ast.Assign) else p.target
            assign = ast.unparse(t)
        if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            chain.append(p.name)
        cur = p
    if text is None:
        text = ast.unparse(node)
    return ".".join(reversed(chain)), assign, text


def _mentions(text, names):
    import re
    return any(re.search(r"(?<![\w.])%s\b|\.%s\b" % (re.escape(n), re.escape(n)), text) for n in names)


def _is_none_guard(node, op):
    test = node.test if isinstance(node, ast.If) else node
    return (isinstance(test, ast.Compare) and len(test.ops) == 1
            and isinstance(test.ops[0], (ast.Is, ast.IsNot))
            and isinstance(test.comparators[0], ast.Constant) and test.comparators[0].value is None)


def _is_format_mod(node, op):
    return (op == "arith" and isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod)
            and isinstance(node.left, (ast.Constant, ast.JoinedStr))
            and (not isinstance(node.left, ast.Constant) or isinstance(node.left.value, str)))


def classify(node, op, assign, text):
    if _mentions(assign, COUNTER_NAMES) or _mentions(text, COUNTER_NAMES):
        return "counter"
    if _mentions(assign, BUDGET_NAMES) or _mentions(text, BUDGET_NAMES):
        return "budget"
    if op in ("cmp", "ifneg") and _is_none_guard(node, op):
        return "none_guard"
    if _is_format_mod(node, op):
        return "error_message"
    return "other"


def sites(source):
    """{site index (the `#i` of a mutant id): Site} for a module source."""
    tree = ast.parse(source)
    parent = _parents(tree)
    out = {}
    for i, (node, op, desc, apply, undo) in enumerate(_sites(tree)):
        enclosing, assign, text = describe(tree, node, parent)
        out[i] = Site(i, op, node.lineno, enclosing, assign, text, classify(node, op, assign, text))
    return out


def site_index(mutant_id):
    return int(mutant_id.rsplit("#", 1)[1])


def triage(mutant_dicts, source_by_path):
    """Classify the SURVIVORS of a mutation report. Returns the per-class
    id lists, the survivor rows, and the score over all mutants vs. over
    the behavioural set (non-behavioural survivors AND their killed
    siblings both drop out of that denominator: the score is a property of
    the code class, not of the survivors alone)."""
    cache = dict((p, sites(src)) for p, src in source_by_path.items())
    classes = dict((c, []) for c in CLASSES)
    rows = []
    class_of = {}
    for d in mutant_dicts:
        s = cache.get(d["path"], {}).get(site_index(d["id"]))
        kind = s.kind if s else "other"
        class_of[d["id"]] = kind
        if d["status"] == "survived":
            classes[kind].append(d["id"])
            row = s.as_dict() if s else {"class": kind}
            row.update({"id": d["id"], "description": d.get("description", "")})
            rows.append(row)
    total = len(mutant_dicts)
    killed = sum(1 for d in mutant_dicts if d["status"] in ("killed", "timeout"))
    beh = [d for d in mutant_dicts if class_of[d["id"]] not in NON_BEHAVIOURAL]
    beh_killed = sum(1 for d in beh if d["status"] in ("killed", "timeout"))
    return {"classes": classes,
            "counts": dict((c, len(v)) for c, v in classes.items()),
            "class_totals": dict((c, sum(1 for d in mutant_dicts if class_of[d["id"]] == c)) for c in CLASSES),
            "survivors": rows,
            "score_all": round(killed / total, 4) if total else None,
            "score_behavioural": round(beh_killed / len(beh), 4) if beh else None,
            "behavioural_total": len(beh), "behavioural_killed": beh_killed,
            "non_behavioural_survivors": sum(len(classes[c]) for c in NON_BEHAVIOURAL)}


def render(t):
    lines = ["triage: %d survivors; score all %.4f, behavioural %.4f (%d/%d after dropping %s)"
             % (sum(t["counts"].values()), t["score_all"] or 0, t["score_behavioural"] or 0,
                t["behavioural_killed"], t["behavioural_total"], "+".join(NON_BEHAVIOURAL))]
    for c in CLASSES:
        lines.append("  %-14s survived %3d of %3d" % (c, t["counts"][c], t["class_totals"][c]))
    return "\n".join(lines)


def main(argv=None):
    import argparse
    import json
    import os
    from .fuzz import WHENCE_ROOT
    ap = argparse.ArgumentParser(description="classify surviving mutants by the code they sit in")
    ap.add_argument("mutation_json")
    ap.add_argument("--root", default=WHENCE_ROOT)
    ap.add_argument("--json")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args(argv)
    with open(a.mutation_json, encoding="utf-8") as f:
        data = json.load(f)
    paths = sorted(set(d["path"] for d in data["mutants"]))
    srcs = dict((p, open(os.path.join(a.root, p), encoding="utf-8").read()) for p in paths)
    t = triage(data["mutants"], srcs)
    print(render(t))
    if a.show:
        for r in sorted(t["survivors"], key=lambda r: (r["class"], r.get("enclosing", ""), r.get("line", 0))):
            print("  %-13s %-30s L%-5s %-14s | %s" % (r["class"], r.get("enclosing", "")[:30], r.get("line"),
                                                   r["description"][:14], r.get("text", "")[:70]))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(t, f, indent=1)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
