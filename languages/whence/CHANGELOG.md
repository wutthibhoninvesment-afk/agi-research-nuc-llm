# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.19.0] — 2026-08-30

### Added
- **Parameter Contract Validation:** Type checking for function arguments (v0.19 contracts)
- **Dev Dependencies:** `pytest`, `pytest-cov` added to `[project.optional-dependencies]`
- **Automated Bridge Testing:** Integration test suite for NQC Bridge (Port 8080 → Port 8000)

### Changed
- **Version Bump:** Package metadata updated from v0.14.0 to v0.19.0 to reflect research rounds 009–346
- **SPEC.md Header:** Updated `spec_version` to match package version
- **Documentation Structure:** Added `CHANGELOG.md` and `SECURITY.md` for Open Source readiness

### Fixed
- **JSON Precision Handling:** Resolved Python 3.12 `json.dump` floating-point precision issue (Process Rule 28)
- **Error Handling Stability:** Improved `miss` value propagation to prevent mid-loop crashes in infinite calculations

### Security
- **No Secrets in Codebase:** Verified zero hardcoded API keys, passwords, or private keys in source files
- **MIT License:** Project released under MIT License — free for commercial and personal use

## [0.14.0] — 2026-08-25 (Research Phase)

### Initial Release
- Core Parser & Evaluator implemented
- Provenance DAG tracking (every value remembers its origin)
- First-Class Error Handling (`miss` type instead of exceptions)
- Time-Travel Debugger (`snap()`, `rewind()`, `timeline()`)
- Immutable Data Structures (WList with O(n) memory sharing)
- Test Suite: 801+ tests passing (Interpreter, Lexer, Parser, Timetravel)

[0.19.0]: https://github.com/wutthibhoninvesment-afk/agi-research-nuc-llm/releases/tag/v0.19.0
[0.14.0]: https://github.com/wutthibhoninvesment-afk/agi-research-nuc-llm/releases/tag/v0.14.0
