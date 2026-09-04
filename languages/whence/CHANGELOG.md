# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- None

---

## [v0.44.0] - 2026-09-04

### Security ✅
- **Full Security Audit completed**: No hardcoded secrets, no external dependencies, isolated runtime
- **SECURITY_AUDIT_REPORT.md**: Comprehensive audit covering code safety, dependency security, input validation
- **MIT License**: Clear permissive license for public use

### Packaging 📦
- **pyproject.toml**: Proper build configuration with setuptools
- **Optional dependencies**: `[dev]` (pytest), `[nuc]` (requests), `[bench]` (matplotlib)
- **CLI entry point**: `whence` command available after `pip install whence-lang`
- **Package discovery**: Automatic inclusion of `whence*` packages

### Testing 🧪
- **875+ unit tests**: All passing across test files (test_interp.py, test_fuzz_*.py, test_vXX.py, etc.)
- **Fast/slow tier separation**: `run_tests_fast.sh` for quick CI checks (~30s)
- **Regression testing**: Every feature has dedicated test cases
- **Guest differential tests**: Host/guest parity verification

### Core Features ⚙️
- **Fold function verified**: Works correctly with proper argument order `(fn, acc, xs)`
- **Provenance DAG**: Full traceability of all computations
- **Time-Travel Debugging**: Step back through execution history
- **First-Class Errors**: Miss values propagate safely without crashes
- **Closure evaluation**: Inline and named functions work consistently

### Documentation 📚
- **SPEC.md v0.44**: Complete language specification
- **README.md**: Quick start guide with examples
- **CHANGELOG.md**: This file — tracking all major changes
- **SECURITY.md**: Security policy and vulnerability reporting
- **Production examples**: Working `.lang` files demonstrating best practices

### Architecture 🏗️
- **Zero external dependencies**: Core interpreter uses Python stdlib only
- **Modular design**: Parser, Evaluator, Values separated cleanly
- **SSH Bridge**: Optional connection to NUC edge devices
- **Hermes integration**: Gateway protocol for autonomous research

---

## [v0.19.0] - August 2026

### Breaking Changes
- Argument order for higher-order builtins (`fold`, `map`, `filter`) now requires `FUNCTION FIRST`

### Added
- Provenance-first error handling with First-Class Miss values
- Time-Travel Debugger for post-execution analysis
- Parameter contracts for type safety
- Bridge layer for NQC Qwen API integration

### Fixed
- Fold accumulator provenance preservation (round 347)

---

## [v0.14.0] - Earlier Versions

### Core Language Features
- Provenance DAG for full computation traceability
- First-Class Errors and Miss values
- Time-Travel Debugging capabilities
- Closure and function evaluation
- List operations (map, filter, fold)

---

_Versions below v0.14 tracked in git history only._
