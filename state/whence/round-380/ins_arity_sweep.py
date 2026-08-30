"""Round 380 — does a guest provenance node keep the same INPUTS the host's
does?

Found while measuring `GUEST_STEPS_BUDGET` (item 3): the proxy and the real
guest walk disagreed on `note(1 + 2, "m")` — 6 host nodes, 3 guest nodes.
`self_eval.lang`'s `apply_host_builtin` curates the inputs for two builtins
whose host node drops an argument's derivation:

    else if name == "put"  { [args[0], args[2]] }   # not the key
    else if name == "note" { [args[1]] }            # only the noted value

Both are right for the SUCCESS node and wrong for the MISS node: host
`b_put`/`b_note` pass `inputs=(r, name, v)` / `inputs=(label, v)` to
`mk_miss`, i.e. every argument.  This sweeps the whole builtin surface for
that shape rather than fixing the two cases that happened to be noticed.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
ROOT = os.path.join(REPO, "languages", "whence")
sys.path.insert(0, ROOT)
sys.path.insert(0, _HERE)

from whence.interp import Interpreter                      # noqa: E402
from guest_walk_probe import library_source, escape        # noqa: E402

CASES = [
    ("note ok",      'note("m", 1 + 2)'),
    ("note bad-lbl", 'note(1 + 2, "m")'),
    ("put ok",       'put(@{a: 1}, "b", 2 + 3)'),
    ("put bad-rec",  'put(7, "b", 2 + 3)'),
    ("put bad-key",  'put(@{a: 1}, 9, 2 + 3)'),
    ("len ok",       'len([1 + 1, 2])'),
    ("len bad",      'len(1 + 1)'),
    ("get ok",       'get(@{a: 1 + 1}, "a")'),
    ("get bad-rec",  'get(7, "a")'),
    ("get bad-key",  'get(@{a: 1}, 9)'),
    ("has ok",       'has(@{a: 1}, "a")'),
    ("has bad",      'has(7, "a")'),
    ("merge ok",     'merge(@{a: 1}, @{b: 2 + 2})'),
    ("merge bad",    'merge(7, @{b: 2})'),
    ("keys ok",      'keys(@{a: 1 + 1})'),
    ("keys bad",     'keys(7)'),
    ("push ok",      'push([1], 2 + 2)'),
    ("push bad",     'push(7, 2)'),
    ("join ok",      'join(["a", "b"], "-")'),
    ("join bad",     'join(7, "-")'),
    ("contains ok",  'contains("abc", "b")'),
    ("contains bad", 'contains(7, "b")'),
    ("str ok",       'str(1 + 1)'),
    ("show ok",      'show(1 + 1)'),
    ("num ok",       'num("3")'),
    ("num bad",      'num("x")'),
    ("abs ok",       'abs(0 - 3)'),
    ("abs bad",      'abs("x")'),
    ("sqrt bad",     'sqrt("x")'),
    ("trunc bad",    'trunc("x")'),
    ("range ok",     'range(1 + 1)'),
    ("range bad",    'range("x")'),
    ("map ok",       'map(fn(v) { v + 1 }, [1, 2])'),
    ("map bad",      'map(fn(v) { v + 1 }, 7)'),
    ("filter bad",   'filter(fn(v) { true }, 7)'),
    ("fold bad",     'fold(fn(s, v) { s }, 0, 7)'),
    ("find bad",     'find(fn(v) { true }, 7)'),
    ("reasons ok",   'reasons(1 / 0)'),
    ("reasons bad",  'reasons(1 + 1)'),
    ("missed ok",    'missed(1 + 1)'),
    ("guess ok",     'guess(1 + 1, 0.5, "s")'),
    ("guess bad",    'guess(1 + 1, "x", "s")'),
    ("is_guess ok",  'is_guess(1 + 1)'),
    ("confidence b", 'confidence(1 + 1)'),
    ("sure bad",     'sure(1 + 1, 2)'),
    ("typed ok",     'typed(1 + 1, "num", "p")'),
    ("typed bad",    'typed("s", "num", "p")'),
    ("matches ok",   'matches(1 + 1, "num")'),
    ("shapeof ok",   'shapeof(1 + 1)'),
    ("steps ok",     'steps(1 + 1)'),
    ("steps bad",    'steps(1 + 1, 7)'),
    ("at bad",       'at(1 + 1, 7)'),
    ("blame ok",     'blame(1 / 0)'),
    ("diverge ok",   'diverge(1 + 1, 1 + 2)'),
    ("diverge bad",  'diverge(7)'),
    ("contrast bad", 'contrast(7)'),
]


def host_node(expr):
    env = Interpreter(out=lambda s: None, seed=7).run("let r = %s" % expr)
    n = env.get("r")
    return n.inputs[0] if n.inputs else n


def guest_boxes(exprs, lib):
    parts = [lib]
    for i, e in enumerate(exprs):
        src = "let r = %s" % e
        parts.append('let __g%d = ((guest_history_root('
                     '(run_src_p("%s")).v)).ins)[0]\n' % (i, escape(src)))
        parts.append('let __o%d = __g%d.op\n' % (i, i))
        parts.append('let __k%d = len(__g%d.ins)\n' % (i, i))
    env = Interpreter(out=lambda s: None, seed=7).run("".join(parts))
    out = []
    for i in range(len(exprs)):
        o, k = env.get("__o%d" % i), env.get("__k%d" % i)
        out.append((None if o is None else o.payload,
                    None if k is None else k.payload))
    return out


if __name__ == "__main__":
    lib = library_source()
    exprs = [e for _, e in CASES]
    g = guest_boxes(exprs, lib)
    rows = []
    for (label, expr), (gop, gk) in zip(CASES, g):
        h = host_node(expr)
        # A guest box has ONE label slot (`op`); v0.30 established that
        # `Prov.label()` == `op + " " + detail` is its exact inverse, so the
        # host side of a label comparison is `label()`, not `.op`.
        rows.append((label, expr, h.label(), h.op, len(h.inputs), gop, gk))

    ins_diff = [r for r in rows if r[4] != r[6]]
    lab_diff = [r for r in rows if r[2] != r[5]]
    # the label class splits again: a guest label that is the host's OP with
    # the detail dropped is the delegation shape; anything else is not.
    det_dropped = [r for r in lab_diff if r[5] == r[3]]
    other_lab = [r for r in lab_diff if r[5] != r[3]]

    print("%-14s %-27s %-4s %-4s %s" %
          ("case", "expr", "h#", "g#", "host label | guest label"))
    for label, expr, hlab, hop, hk, gop, gk in rows:
        flag = ""
        if hk != gk:
            flag = "  <-- INS"
        elif hlab != gop:
            flag = "  <-- lab"
        print("%-14s %-27s %-4d %-4s %s | %s%s"
              % (label, expr[:27], hk, gk, hlab[:44], str(gop)[:30], flag))

    print("\n--- INPUT-COUNT divergences (the bug) : %d of %d"
          % (len(ins_diff), len(rows)))
    for label, expr, hlab, hop, hk, gop, gk in ins_diff:
        print("  %-14s %-27s host %d  guest %s" % (label, expr, hk, gk))
    print("--- LABEL divergences                 : %d of %d"
          % (len(lab_diff), len(rows)))
    print("      of which 'host detail dropped'  : %d" % len(det_dropped))
    print("      of which something else         : %d" % len(other_lab))
    for label, expr, hlab, hop, hk, gop, gk in other_lab:
        print("  %-14s host %r  guest %r" % (label, hlab, gop))
    print("--- agreeing on BOTH                  : %d of %d"
          % (len([r for r in rows if r[4] == r[6] and r[2] == r[5]]),
             len(rows)))
