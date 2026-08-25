# Exact commands

One-liners used at steps 10–16 (differential check of the fast path,
call-count profile, three-way differential incl. direct mode, frames-per-guest-level
measurement, and the decoupling proof under a tiny host recursion limit). Paths are
relative to the interpreter package; adapt the module names.

```bash
# differential check of the fast path (must be identical both ways)
python3 -c "from whence.interp import Interpreter; from whence.values import render_why
for fast in (False, True):
    i = Interpreter(fast=fast); env = i.run('let r = if 1 < 2 { [1, 2][1] } else { 0 }')
    print(fast, i.fast_hits, render_why(env.get('r')))"
# where does the time go? count calls per iteration, not just seconds
python3 -c "import cProfile, pstats; from whence.interp import Interpreter
cProfile.run('Interpreter().run(open(\"examples/tco.lang\").read())', '/tmp/p')
pstats.Stats('/tmp/p').sort_stats('tottime').print_stats(15)"
# three-way differential incl. direct mode (v0.9): all render_why equal
python3 -c "from whence.interp import Interpreter; from whence.values import render_why
src = 'fn f(n) { if n < 2 { n } else { f(n - 1) + f(n - 2) } }\nlet r = f(12)'
ts = [render_why(Interpreter(**kw).run(src).get('r')) for kw in ({}, {'direct': False}, {'fast': False})]
print(ts[0] == ts[1] == ts[2])"
# frames per guest level in direct mode (must equal the charge, cdepth + 1)
python3 -c "import sys; from whence.interp import Interpreter
def peak(n):
    d=[0]; p=[0]
    def prof(f, ev, a):
        if ev == 'call': d[0] += 1; p[0] = max(p[0], d[0])
        elif ev == 'return': d[0] -= 1
    sys.setprofile(prof); Interpreter().run('fn c(n) { if n == 0 { 0 } else { 1 + c(n - 1) } }\nlet r = c(%d)' % n); sys.setprofile(None); return p[0]
print((peak(60) - peak(30)) / 30.0)"
# prove decoupling: evaluate a 3000-deep guest recursion under a tiny host limit
python3 - <<'EOF'
import sys; sys.setrecursionlimit(200)
from whence.interp import Interpreter
i = Interpreter(); env = i.run("fn c(n) { if n == 0 { 0 } else { 1 + c(n - 1) } }\nlet r = c(3000)")
print(env.get("r").payload, i.peak_depth)
EOF
python3 -m pytest tests/ -q
```
