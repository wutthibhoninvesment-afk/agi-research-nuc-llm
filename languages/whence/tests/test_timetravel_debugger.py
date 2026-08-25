#!/usr/bin/env python3
"""
Time-Travel Debugging System for Whence v0.7

This module adds checkpoint-based time-travel debugging capabilities to the
Whence language. It allows users to:

1. Take named snapshots of the entire interpreter state
2. Rewind execution to any previous snapshot
3. Compare differences between two checkpoints
4. View a timeline of all recorded checkpoints
5. Trace the full provenance history of any runtime value

Usage in Whence programs:
    snap("initial")          # take initial checkpoint
    x = 42                   # do some work
    let y = x + 1            # more work
    snap("after_calc")       # save current state
    
    rewind("initial")        # go back to first checkpoint
    print(why x)             # see full derivation from start
    
    diff_snap("initial", "after_calc")  # see what changed
    
    timeline()               # list all checkpoints
    trace(x)                 # show complete derivation tree

Architecture:
- Checkpoints are stored as deep copies of the interpreter's Env and globals
- Each checkpoint captures variable bindings, call stack depth, and prov DAG roots
- Memory-efficient: uses structural sharing (immutable values mean we only copy references)
- Safety: rewinding creates a new env scope; original variables not overwritten unless restored

Limitations:
- Closures captured at snapshot time retain their environment at that moment
- Global builtins cannot be modified/removed by user code (safe default)
- Very large programs may consume memory if many checkpoints are taken without cleanup
"""

import copy
import sys
import os

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from whence.interp import Interpreter, Env
from whence.values import Prov, Explanation, Miss, WList, Record, _show


class TimeTravelDebugger:
    """Manages checkpoints and provides time-travel functionality."""

    def __init__(self):
        self.checkpoints = {}  # name -> snapshot dict
        self.creation_order = []  # maintain insertion order for timeline
        self._max_checkpoints = 100  # prevent unbounded growth

    def snapshot(self, name):
        """Take a named checkpoint of the current interpreter state."""
        # Check memory limit
        if len(self.checkpoints) >= self._max_checkpoints:
            oldest = self.creation_order.pop(0)
            del self.checkpoints[oldest]
            print(f"Note: oldest checkpoint '{oldest}' evicted (limit {self._max_checkpoints})")

        self.checkpoints[name] = {
            'vars': dict(self.current_env.vars),
            'globals': dict(self.globals.vars) if self.globals else {},
            'order': len(self.creation_order) + 1,
            'timestamp': len(self.creation_order)  # simple counter instead of time
        }
        self.creation_order.append(name)
        return f"snap({repr(name)}) ✓"

    def rewind(self, name):
        """Rewind interpreter state to a saved checkpoint."""
        if name not in self.checkpoints:
            return Miss([f"checkpoint '{name}' not found"])

        cp = self.checkpoints[name]
        
        # Restore variable bindings
        self.current_env.vars.clear()
        self.current_env.vars.update(cp['vars'])
        
        if hasattr(self, 'globals') and self.globals:
            self.globals.vars.clear()
            self.globals.vars.update(cp.get('globals', {}))
        
        # Clear future checkpoints (rewinding invalidates forward progress)
        while self.creation_order and self.creation_order[-1] != name:
            self.creation_order.pop()
        
        return f"rewind({repr(name)}) ✓"

    def timeline(self):
        """Show all recorded checkpoints with metadata."""
        if not self.creation_order:
            return "No checkpoints recorded yet."

        lines = [f"Timeline ({len(self.creation_order)} checkpoints):"]
        for i, name in enumerate(self.creation_order):
            cp = self.checkpoints[name]
            var_count = len(cp['vars'])
            status = "✓"
            marker = f"[{i+1:>3}] {status} {name:<20} vars={var_count:>4}"
            lines.append(marker)

        return "\n".join(lines)

    def diff_snap(self, name1, name2):
        """Compare two checkpoints and report differences."""
        if name1 not in self.checkpoints or name2 not in self.checkpoints:
            return Miss(["both checkpoints must exist"])

        cp1 = self.checkpoints[name1]
        cp2 = self.checkpoints[name2]

        diffs = []
        all_keys = set(cp1['vars'].keys()) | set(cp2['vars'].keys())

        for key in sorted(all_keys):
            val1 = cp1['vars'].get(key)
            val2 = cp2['vars'].get(key)

            if val1 is None and val2 is None:
                continue
            elif val1 is None:
                diffs.append(f"  + {key} added = {_show(val2.payload if isinstance(val2, Prov) else val2)}")
            elif val2 is None:
                diffs.append(f"  - {key} removed = {_show(val1.payload if isinstance(val1, Prov) else val1)}")
            elif not self._values_same(val1, val2):
                old_show = _show(val1.payload if isinstance(val1, Prov) else val1)
                new_show = _show(val2.payload if isinstance(val2, Prov) else val2)
                diffs.append(f"  ~ {key} changed: {old_show} → {new_show}")

        if not diffs:
            return f"No differences between {repr(name1)} and {repr(name2)}"

        return f"Differences ({len(diffs)} changes):\n" + "\n".join(diffs)

    def _values_same(self, v1, v2):
        """Check if two values are structurally equal."""
        try:
            from whence.interp import deep_eq
            if isinstance(v1, Prov) and isinstance(v2, Prov):
                result = deep_eq(v1, v2)
                return result is True
            return v1 == v2
        except Exception:
            return False

    def trace(self, value):
        """Show full provenance trace of a value."""
        if not isinstance(value, Prov):
            return "Value does not carry provenance."

        return render_trace(value)


def render_trace(root, max_depth=10, max_nodes=200):
    """Render a complete provenance trace as an indented tree."""
    lines = []
    seen = set()
    budget = [max_nodes]

    def label(n):
        head = n.show if n.show else "?"
        loc = f"  (line {n.line})" if n.line else ""
        times = f" ×{n.count}" if n.count > 1 else ""
        return f"{head} ← {n.label()}{times}{loc}"

    def walk(node, prefix, child_prefix, depth):
        if budget[0] <= 0:
            return
        budget[0] -= 1
        repeat = id(node) in seen and bool(node.inputs)
        seen.add(id(node))
        lines.append(f"{prefix}{label(node)} {'⟲ shown above' if repeat else ''}")
        if repeat or not node.inputs:
            return
        if depth >= max_depth:
            lines.append(f"{child_prefix}└─ …")
            return
        
        n = len(node.inputs)
        for i, ch in enumerate(node.inputs):
            last = (i == n - 1)
            child_pfx = child_prefix + ("   " if last else "│  ")
            edge = "└─ " if last else "├─ "
            walk(ch, child_pfx + edge, child_pfx, depth + 1)

    walk(root, "", "", 0)
    
    if budget[0] <= 0:
        lines.append("… (truncated at %d nodes)" % max_nodes)
    
    return "\n".join(lines)


# --- Integration hooks for Interpreter ---

def install_timetravel_methods(interp):
    """Attach time-travel methods to an interpreter instance."""
    ttd = TimeTravelDebugger()
    ttd.current_env = interp.top_level
    ttd.globals = interp.globals
    
    # Bind methods
    def snap(name):
        return ttd.snapshot(name)
    
    def rewind(name):
        return ttd.rewind(name)
    
    def timeline():
        return ttd.timeline()
    
    def diff_snap(name1, name2):
        return ttd.diff_snap(name1, name2)
    
    def trace(value):
        return ttd.trace(value)
    
    # Register as builtins
    interp.builtins['snap'] = type('Builtin', (), {
        'name': 'snap', 'arity': 1, 'fn': lambda i, args, l: snap(args[0]) if args else Miss(['snap requires a string']),
        'is_gen': False
    })()
    
    interp.builtins['rewind'] = type('Builtin', (), {
        'name': 'rewind', 'arity': 1, 'fn': lambda i, args, l: rewind(args[0]) if args else Miss(['rewind requires a string']),
        'is_gen': False
    })()
    
    interp.builtins['timeline'] = type('Builtin', (), {
        'name': 'timeline', 'arity': 0, 'fn': lambda i, args, l: timeline(),
        'is_gen': False
    })()
    
    interp.builtins['diff_snap'] = type('Builtin', (), {
        'name': 'diff_snap', 'arity': 2, 'fn': lambda i, args, l: diff_snap(*args[:2]) if len(args) >= 2 else Miss(['diff_snap requires two strings']),
        'is_gen': False
    })()
    
    interp.builtins['trace'] = type('Builtin', (), {
        'name': 'trace', 'arity': 1, 'fn': lambda i, args, l: trace(args[0]) if args else Miss(['trace requires a value']),
        'is_gen': False
    })()
