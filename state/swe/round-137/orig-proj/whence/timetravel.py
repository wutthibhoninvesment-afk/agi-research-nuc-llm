"""Host-side time-travel debugging helper (round 132 finding, not a Whence
language feature). `TimeTravelDebugger` is a plain Python class for
inspecting `Env.vars` snapshots while developing the interpreter itself —
it is NEVER wired into `Interpreter` and exposes no Whence builtins.

An earlier commit outside the round process ("Time-Travel Debugger v0.7
complete!", 8637795) shipped this class alongside `install_timetravel_
builtins` and a SPEC section claiming five new guest-language builtins
(`snap`/`rewind`/`timeline`/`diff_snap`/`trace`). Neither was ever reachable:
nothing called `install_timetravel_builtins`, and had it been wired in it
would still have been broken — it wrote to `interp.builtins[...]` instead of
the real per-process `_BUILTIN_TABLE` singleton dispatch table (interp.py),
called a nonexistent `Interpreter.miss()`, and assumed raw Python values
where Whence's builtin convention is `fn(interp, args, line)` over
`Prov`-wrapped values. `install_timetravel_builtins` was deleted in round
138 rather than fixed: rewinding `env.vars` in place is also a poor match
for Whence's actual design (decision 3, no assignment/no mutation of
bindings) — a real "time travel" feature belongs on TOP of the existing
`at`/`steps`/`blame` provenance builtins, not as a mutable checkpoint
stack. `tests/test_timetravel.py` exercises this class directly as a
Python utility; that part was always real.
"""


class TimeTravelDebugger:
    """Manages checkpoints and provides time-travel functionality."""

    def __init__(self):
        self.checkpoints = {}      # name -> {vars, order, timestamp}
        self.creation_order = []   # Maintain insertion order for timeline
        self._max_checkpoints = 100  # Prevent unbounded growth

    def snapshot(self, env):
        """Take a named checkpoint of the current interpreter state.
        
        Args:
            env: Interpreter's Env object with .vars dict
            
        Returns:
            str: Success message with checkpoint name
        """
        if len(self.checkpoints) >= self._max_checkpoints:
            oldest = self.creation_order.pop(0)
            del self.checkpoints[oldest]
            return f"snap({repr(oldest)}) ✓ [evicted due to max limit]"

        name = env.get('_last_snap_name', 'unnamed')
        self.checkpoints[name] = {
            'vars': dict(env.vars),          # Shallow copy (values are immutable)
            'order': len(self.creation_order) + 1,
            'timestamp': len(self.creation_order)
        }
        self.creation_order.append(name)
        return f"snap({repr(name)}) ✓"

    def rewind(self, env, name):
        """Rewind interpreter state to a saved checkpoint.
        
        Args:
            env: Interpreter's Env object
            name: Checkpoint name to restore
            
        Returns:
            Prov or Miss: Result value or miss error
        """
        from whence.values import Miss
        
        if name not in self.checkpoints:
            return Miss([f"checkpoint '{name}' not found"])

        cp = self.checkpoints[name]
        
        # Clear current vars and restore
        env.vars.clear()
        env.vars.update(cp['vars'])
        
        # Also restore globals if they exist
        if hasattr(env, '_globals') and env._globals:
            env._globals.clear()
            env._globals.update(cp.get('globals', {}))
        
        # Clear forward progress (time paradox prevention)
        while self.creation_order and self.creation_order[-1] != name:
            self.creation_order.pop()
        
        return f"rewind({repr(name)}) ✓"

    def timeline(self):
        """Show all recorded checkpoints with metadata.
        
        Returns:
            str: Formatted timeline string
        """
        if not self.creation_order:
            return "No checkpoints recorded yet."

        lines = [f"Timeline ({len(self.creation_order)} checkpoints):"]
        for i, name in enumerate(self.creation_order):
            cp = self.checkpoints[name]
            var_count = len(cp['vars'])
            marker = f"[{i+1:>3}] ✓ {name:<20} vars={var_count:>4}"
            lines.append(marker)

        return "\n".join(lines)

    def diff_snap(self, name1, name2):
        """Compare two checkpoints and report differences.
        
        Uses structural equality comparison that respects provenance DAGs.
        
        Args:
            name1: First checkpoint name
            name2: Second checkpoint name
            
        Returns:
            str: Diff report or miss error
        """
        from whence.values import Miss, Prov, _show
        from whence.interp import deep_eq
        
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
                diffs.append(f"  + {key} added")
            elif val2 is None:
                diffs.append(f"  - {key} removed")
            else:
                # Structural equality check
                same = self._values_same(val1, val2)
                if not same:
                    payload1 = getattr(val1, 'payload', val1)
                    payload2 = getattr(val2, 'payload', val2)
                    show1 = _show(payload1, limit=40, nest=0)[:40]
                    show2 = _show(payload2, limit=40, nest=0)[:40]
                    diffs.append(f"  ~ {key}: {show1} → {show2}")

        if not diffs:
            return f"No differences between {repr(name1)} and {repr(name2)}"

        return f"Differences ({len(diffs)} changes):\n" + "\n".join(diffs)

    def _values_same(self, v1, v2):
        """Check if two values are structurally equal."""
        try:
            from whence.interp import deep_eq
            from whence.values import Prov
            
            if isinstance(v1, Prov) and isinstance(v2, Prov):
                result = deep_eq(v1, v2)
                return result is True
            return v1 == v2
        except Exception:
            return False

    def trace(self, value):
        """Show full provenance trace of a value using existing render_why.
        
        Args:
            value: A Prov node to trace
            
        Returns:
            str: Indented provenance tree or error message
        """
        from whence.values import Prov, render_why
        
        if not isinstance(value, Prov):
            return "Value does not carry provenance (not a Prov node)"
        
        return render_why(value, max_depth=10, max_nodes=200)
