# 🐦 Whence — Provenance-First Language

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

> **"Every value remembers where it came from."**

Whence is an experimental, research-grade programming language built on a single radical idea: **every runtime value carries its own derivation history as a first-class DAG**. No exceptions, no nulls — only `miss` values with reason strings and provenance. Recover with `rescue`. Inspect failures with `blame()`. Ask any value where it originated with `why x`.

## ✨ What Makes Whence Different

| Feature | Description |
|---|---|
| **Provenance-Carrying Values** | `(payload, prov)` merged into one node — every computation traces back to its source |
| **Error-as-Value (`miss`)** | Division by zero? Unbound name? Each failure propagates with reasons + lineage |
| **Time-Travel Queries** | `at(x, "let rate")` retrieves the live value at a named step; `steps(x)` walks the whole derivation |
| **Tail-Call Merging** | 1M iterations → ONE `call f ×N` node with lossless branch condition recording |
| **No Exceptions, No Null** | All errors are ordinary `miss` values — safe to catch, recover, and inspect |
| **Self-Hosting v0.5** | The evaluator for Whence is itself written in Whence (~950 lines) with differential testing |
| **Immutable & Cheap** | Full history retained in O(n) memory via structural sharing — no retention policy needed |

## 🚀 Quick Start

```bash
# Clone and run
git clone https://github.com/wutthibhoninvesment-afk/whence-lang.git
cd whence-lang

# Run example programs
python3 run.py examples/hello.lang
python3 run.py examples/self_eval.lang    # self-hosted evaluator
python3 run.py examples/diverge.lang       # diff two histories

# Run full test suite (449 tests, ~20s)
python3 -m pytest tests/ -v

# Launch benchmarking
python3 run.py bench/retention.py --n 20000
```

## 📖 Design Decisions (Anti-Mainstream)

1. **A value IS its provenance node** — no separate wrapper, one pointer per operation
2. **History is queryable data** — not a printout; you can fold, diff, and travel through derivations
3. **Tests are statements** — `check "label": expr` fails fast with a printed why-tree
4. **Strict booleans** — only `true`/`false` are conditions; `if 0 {…}` is a miss, not "falsy"
5. **Recursion is trampolined** — depth capped by `max_depth` (default 20000); exceeding it is an ordinary miss
   (v0.9: the first few hundred levels run by budgeted host recursion — direct mode — and the trampoline takes over beyond)

## 🏗️ Architecture Overview

```
source.whence
    │
    ▼
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│  Lexer      │────▶│   Parser     │────▶│  Trampolined Eval│
│  (char scan)│     │  (AST build) │     │  (DAG construction│
└─────────────┘     └──────────────┘     │   with TCO +      │
                                          │   compiled paths) │
└─────────────────────────────────────────┼──────────────────┘
                                          ▼
                                    Prov DAG nodes
                                      (values + proofs)
```

## 🧪 Test Coverage

- **449 passing tests** across: lexer, parser, interpreter, values, provenance, self-evaluation, fuzz oracles, differential comparisons
- **Fuzz-driven hardening**: 21 + 33 seed programs × 511 programs × 4 oracles = **0 crash signatures found** (v0.6 state)
- **Mutation score**: tracked per round via `harness/swe/fuzz.py`

## 💡 Use Cases

- **Debugging**: Find the exact source literal that caused a division-by-zero
- **Educational**: Visualize how functional computations build up over time
- **Formal Verification**: Diff two runs to prove behavioral differences
- **Research**: Experiment with provenance-carrying semantics, TCO merging, metacircular evaluation

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork and create a feature branch
2. Add tests for new behavior (run `pytest` before submitting)
3. Update SPEC.md if changing syntax or semantics
4. Open a Pull Request describing changes and motivation

## 🙏 Support This Project

Whence is a passion project developed independently. If you find it useful or educational, consider supporting continued development:

👉 [Donate via PayPal](https://paypal.me/wutthibhon)  
👉 [Support via Ko-fi](https://ko-fi.com/wutthibhon)  
*(Links will be updated to active payment methods — stay tuned!)*

## 📜 License

[MIT License](LICENSE) — free to use, modify, and distribute with attribution.

## 🔗 Related Work

This project draws inspiration from several areas of computer science:
- SICP metacircular evaluators (Abelson & Sussman)
- Datalog and relational databases (derivation tracking)
- Symbolic execution and constraint solving
- Functional programming languages (OCaml, Haskell, Rust's `Result`)
- Time-travel debugging tools (Chrome DevTools, GDB reverse execution)

What makes Whence unique: **provenance is a semantic primitive**, not a logging side-effect. Every derived value IS its own proof tree.

---

*Built autonomously through 25+ rounds of AGI research loops using Claude Code (Anthropic).*
*Current spec version: v0.9 | Last updated: August 2026*
