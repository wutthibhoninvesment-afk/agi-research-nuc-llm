#!/usr/bin/env python3
"""Measure the four numbers behind v0.27 (round 368): `_STR_BYTES_PER_CHAR`,
`_LIST_BYTES_PER_ELEM`, `_RANGE_BYTES_PER_ELEM`, and the cost curve that
forced `DEFAULT_MAX_INT_BITS` to be a SECOND budget rather than a conversion
into `DEFAULT_MAX_VALUE`.

usage: python3 bench/value_size.py            # every section
       python3 bench/value_size.py --bytes    # the three memory constants
       python3 bench/value_size.py --ints     # the bigint multiply curve
       python3 bench/value_size.py --runaway  # what each runaway now costs
       python3 bench/value_size.py --corpus   # peak_value over examples/

Re-run this before changing any of them. Same discipline as
`bench/runaway_cost.py` (round 366) and for the same reason: the constants
are the only thing standing between "a limit that is an error" and "a limit
that is a hang", and a constant nobody re-executes is round 333's rot class.

WHY ONE RUN PER PROCESS in --runaway and --corpus. `ru_maxrss` is a
process-wide HIGH-WATER mark: it never falls, so a second measurement in the
same process reads the first one's peak. Round 366 lost 2-4x to exactly this.
"""
import gc
import json
import os
import resource
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from whence.interp import Interpreter                       # noqa: E402
from whence.lexer import LexError                           # noqa: E402
from whence.parser import ParseError                        # noqa: E402
from whence.values import leaf                              # noqa: E402


def peak_kb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss   # KB on Linux


# --------------------------------------------------------------------------
# the three memory constants
# --------------------------------------------------------------------------
def section_bytes():
    print("== memory cost per unit (the `_*_BYTES_PER_*` constants) ==")
    s0, s1 = sys.getsizeof(""), sys.getsizeof("a" * 100000)
    print("  str      %7.3f B/char   (_STR_BYTES_PER_CHAR)"
          % ((s1 - s0) / 100000))

    n = 1 << 1000000
    i0, i1 = sys.getsizeof(0), sys.getsizeof(n)
    print("  int      %7.4f B/bit    (reported only: integers are charged in "
          "BITS)" % ((i1 - i0) / 1000000))

    gc.collect()
    before = peak_kb()
    xs = [None] * 3000000
    gc.collect()
    print("  list     %7.2f B/elem   (_LIST_BYTES_PER_ELEM: `+`/`push` copy "
          "shared pointers)" % ((peak_kb() - before) * 1024 / 3e6))
    del xs
    gc.collect()

    before = peak_kb()
    items = [leaf("range", str(i), 1, i) for i in range(2000000)]
    gc.collect()
    print("  range    %7.2f B/elem   (_RANGE_BYTES_PER_ELEM: a fresh Prov "
          "leaf AND a decimal detail per element)"
          % ((peak_kb() - before) * 1024 / 2e6))
    print("  one Prov %7d B" % sys.getsizeof(items[0]))
    del items
    gc.collect()


# --------------------------------------------------------------------------
# the bigint curve: why `max_int_bits` cannot be `max_value / 8`
# --------------------------------------------------------------------------
def section_ints(stop_s=8.0):
    print("== one `x * x`, by operand size (CPython bigint multiply) ==")
    print("  %-12s %-10s %s" % ("operand bits", "seconds", "result bytes"))
    prev = 3
    while True:
        t = time.perf_counter()
        cur = prev * prev
        dt = time.perf_counter() - t
        if prev.bit_length() >= 100000:
            print("  %-12d %-10.4f %d"
                  % (prev.bit_length(), dt, cur.bit_length() // 8))
        prev = cur
        if dt > stop_s:
            break
    print("  Linear would double the time per doubling; this is ~n**1.58, so"
          " the last\n  multiply a 500 MB byte-budget would permit"
          " (4e9 bits) extrapolates to hours.")


# --------------------------------------------------------------------------
# what a runaway costs NOW, one fresh process per shape
# --------------------------------------------------------------------------
RUNAWAYS = {
    "str_double":
        'fn go(n, s) { if n <= 0 { s } else { go(n - 1, s + s) } }\n'
        'let r = go(60, "ab")\n',
    "list_double":
        'fn go(n, xs) { if n <= 0 { xs } else { go(n - 1, xs + xs) } }\n'
        'let r = go(60, [1, 2])\n',
    "int_square":
        'fn go(n, x) { if n <= 0 { x } else { go(n - 1, x * x) } }\n'
        'let r = go(60, 3)\n',
    "range_huge":
        'let r = range(100000000000)\n',
    "push_loop":
        'fn go(n, xs) { if n <= 0 { xs } else { go(n - 1, push(xs, n)) } }\n'
        'let r = go(2000000, [])\n',
}


def run_one(name):
    src = RUNAWAYS[name]
    sys.setrecursionlimit(6000)
    interp = Interpreter(out=lambda *a: None, gc_relief=True)
    before = peak_kb()
    t = time.perf_counter()
    try:
        interp.run(src)
        err = ""
    except (LexError, ParseError) as e:
        err = "parse: %s" % e
    except Exception as e:                       # noqa: BLE001 - reporting
        err = "%s: %s" % (type(e).__name__, e)
    dt = time.perf_counter() - t
    print(json.dumps({
        "shape": name, "seconds": round(dt, 3),
        "peak_rss_mb": round((peak_kb() - before) / 1024.0, 1),
        "peak_value": interp.peak_value, "peak_int_bits": interp.peak_int_bits,
        "peak_tail": interp.peak_tail, "err": err,
        "result": interp.globals.get("r").show if
        interp.globals.get("r") is not None else "",
    }))


def section_runaway():
    print("== what each runaway costs under the shipped defaults ==")
    print("  (max_value=%d, max_int_bits=%d, max_iter=%d)"
          % (Interpreter.DEFAULT_MAX_VALUE, Interpreter.DEFAULT_MAX_INT_BITS,
             Interpreter.DEFAULT_MAX_ITER))
    for name in RUNAWAYS:
        r = subprocess.run([sys.executable, __file__, "--one", name],
                           capture_output=True, text=True, timeout=600)
        line = (r.stdout.strip().splitlines() or ["<no output>"])[-1]
        try:
            d = json.loads(line)
        except ValueError:
            print("  %-12s FAILED rc=%d %s" % (name, r.returncode, line[:80]))
            continue
        print("  %-12s %6.2f s  %7.1f MB  peak_value=%-11d "
              "peak_int_bits=%-9d %s"
              % (d["shape"], d["seconds"], d["peak_rss_mb"], d["peak_value"],
                 d["peak_int_bits"], (d["err"] or d["result"])[:60]))


# --------------------------------------------------------------------------
# the corpus: what real programs actually build
# --------------------------------------------------------------------------
def run_example(path):
    sys.setrecursionlimit(6000)
    interp = Interpreter(out=lambda *a: None, gc_relief=True,
                         max_value=None, max_int_bits=None)
    try:
        interp.run(open(path, encoding="utf-8").read())
        err = ""
    except (LexError, ParseError) as e:
        err = "parse: %s" % str(e)[:60]
    except Exception as e:                       # noqa: BLE001 - reporting
        err = "%s: %s" % (type(e).__name__, str(e)[:60])
    print(json.dumps({"file": os.path.basename(path),
                      "peak_value": interp.peak_value,
                      "peak_int_bits": interp.peak_int_bits,
                      "peak_tail": interp.peak_tail, "err": err}))


def section_corpus():
    print("== uncapped peak_value over examples/, one fresh process each ==")
    d = os.path.join(ROOT, "examples")
    rows = []
    for name in sorted(os.listdir(d)):
        if not name.endswith(".lang"):
            continue
        r = subprocess.run([sys.executable, __file__, "--example",
                            os.path.join(d, name)],
                           capture_output=True, text=True, timeout=900)
        try:
            rows.append(json.loads(r.stdout.strip().splitlines()[-1]))
        except Exception:                        # noqa: BLE001 - reporting
            rows.append({"file": name, "peak_value": -1, "peak_int_bits": -1,
                         "peak_tail": -1,
                         "err": "runner rc=%d" % r.returncode})
    rows.sort(key=lambda x: -x["peak_value"])
    for x in rows[:12]:
        print("  %-28s peak_value=%-8d peak_int_bits=%-8d peak_tail=%-8d %s"
              % (x["file"], x["peak_value"], x["peak_int_bits"],
                 x["peak_tail"], x["err"][:40]))
    print("  ... %d more, all peak_value <= %d"
          % (max(0, len(rows) - 12), rows[12]["peak_value"] if
             len(rows) > 12 else 0))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--one"]:
        run_one(a[1])
    elif a[:1] == ["--example"]:
        run_example(a[1])
    else:
        want = set(a) or {"--bytes", "--ints", "--runaway", "--corpus"}
        if "--bytes" in want:
            section_bytes()
        if "--ints" in want:
            section_ints()
        if "--runaway" in want:
            section_runaway()
        if "--corpus" in want:
            section_corpus()
