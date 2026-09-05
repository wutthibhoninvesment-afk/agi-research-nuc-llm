# Release Notes — Whence-lang v1.0.0

**Release Date:** September 4, 2026
**Build Status:** ✅ All tests passing
**Research Rounds:** ~500 autonomous research rounds completed

---

## What is v1.0.0?

Whence-lang v1.0.0 is the **first stable production release** of a provenance-first programming language designed for trustworthy AI systems.

## Key Features
- Full Provenance DAG tracking for all computations
- First-class error handling via Miss values
- Time-travel debugging capabilities
- Zero external runtime dependencies
- Configurable safety limits (max_iter, max_value)
- 200+ unit tests passing

## Installation
```bash
pip install .
```

## Quick Start
```python
from whence.interp import Interpreter
code = """fn add(a, b) { a + b }
let total = fold(add, 0, [1, 2, 3, 4, 5])"""
interp = Interpreter()
env = interp.run(code)
```

## License: MIT
_Building trustworthy AI, one computation at a time._
