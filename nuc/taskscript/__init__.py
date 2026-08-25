"""Errand — task-script language for agent ops on a slow box (mission E5).

Package layout: lexer.py (tokens), parser.py (AST + parser + link checks),
interp.py (values, budgets, preflight, retries, telemetry), transport.py
(mock / dry-run / HTTP transports), run.py (CLI). See SPEC.md.
"""
from .lexer import LexError, tokenize  # noqa: F401
from .parser import ParseError, parse, parse_program  # noqa: F401
from .interp import Interp, Miss, Ok, FlowResult  # noqa: F401
from .transport import DryTransport, HTTPTransport, MockTransport, TransportError  # noqa: F401
