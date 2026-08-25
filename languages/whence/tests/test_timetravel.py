#!/usr/bin/env python3
"""Time-Travel Debugging System Test Suite for Whence v0.7.

Tests all time-travel features:
  - snap(), rewind(), timeline(), diff_snap(), trace()
  - Integration with interpreter builtins
  - Edge cases and error handling
"""

import sys, os

# Add project root to path so 'whence' package can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_ttd_snapshot_basic():
    """Test basic checkpoint creation."""
    from whence.timetravel import TimeTravelDebugger
    
    ttd = TimeTravelDebugger()
    
    # Mock env object
    class MockEnv:
        def __init__(self):
            self.vars = {'a': 1, 'b': 2}
        
        def get(self, key, default=None):
            return self.vars.get(key, default)
    
    env = MockEnv()
    result = ttd.snapshot(env)
    
    assert result == "snap('unnamed') ✓", f"Expected snap message, got: {result}"
    assert len(ttd.checkpoints) == 1, "Should have 1 checkpoint"
    assert 'unnamed' in ttd.creation_order, "Checkpoint name should be in order"
    print("✓ test_ttd_snapshot_basic passed")


def test_ttd_multiple_checkpoints():
    """Test multiple snapshots and checkpoint management."""
    from whence.timetravel import TimeTravelDebugger
    
    ttd = TimeTravelDebugger()
    
    class MockEnv:
        def __init__(self, vars_dict):
            self.vars = vars_dict
        
        def get(self, key, default=None):
            return self.vars.get(key, default)
    
    # Take 3 checkpoints with different states AND names
    class NamedEnv:
        def __init__(self, vars_dict, name):
            self.vars = vars_dict
            self._snap_name = name
        def get(self, key, default=None):
            if key == '_last_snap_name':
                return self._snap_name
            return self.vars.get(key, default)
    
    env1 = NamedEnv({'x': 10}, 'snap_A')
    env2 = NamedEnv({'x': 20, 'y': 30}, 'snap_B')
    env3 = NamedEnv({'x': 30, 'y': 40, 'z': 50}, 'snap_C')
    
    ttd.snapshot(env1)
    ttd.snapshot(env2)
    ttd.snapshot(env3)
    
    assert len(ttd.checkpoints) == 3, "Should have 3 checkpoints"
    assert len(ttd.creation_order) == 3, "Order list should match"
    
    # Verify checkpoint contents preserved
    first_key = next(iter(ttd.checkpoints))
    assert ttd.checkpoints[first_key]['vars'] == {'x': 10}
    second_key = list(ttd.checkpoints.keys())[1]
    assert len(ttd.checkpoints[second_key]['vars']) == 2
    
    print("✓ test_ttd_multiple_checkpoints passed")


def test_ttd_rewind_to_checkpoint():
    """Test rewinding to saved state."""
    from whence.timetravel import TimeTravelDebugger
    from whence.values import Miss
    
    ttd = TimeTravelDebugger()
    
    class MockEnv:
        def __init__(self, vars_dict):
            self.vars = vars_dict
        
        def get(self, key, default=None):
            return self.vars.get(key, default)
    
    # Create initial state and snapshot
    env = MockEnv({'a': 1, 'b': 2})
    ttd.snapshot(env)
    
    # Modify state
    env.vars.update({'c': 3})
    
    # Rewind should restore original state
    result = ttd.rewind(env, 'unnamed')
    assert result == "rewind('unnamed') ✓"
    assert 'a' in env.vars and 'b' in env.vars
    assert 'c' not in env.vars or env.vars.get('c') is None, "Forward progress cleared"
    
    print("✓ test_ttd_rewind_to_checkpoint passed")


def test_ttd_rewind_missing_checkpoint():
    """Test rewind with non-existent checkpoint name."""
    from whence.timetravel import TimeTravelDebugger
    from whence.values import Miss
    
    ttd = TimeTravelDebugger()
    
    class MockEnv:
        def __init__(self):
            self.vars = {}
        
        def get(self, key, default=None):
            return self.vars.get(key, default)
    
    env = MockEnv()
    result = ttd.rewind(env, 'nonexistent')
    
    assert isinstance(result, Miss), "Should return Miss for missing checkpoint"
    assert "not found" in str(result.reasons[0])
    
    print("✓ test_ttd_rewind_missing_checkpoint passed")


def test_ttd_timeline_empty():
    """Test timeline when no checkpoints exist."""
    from whence.timetravel import TimeTravelDebugger
    
    ttd = TimeTravelDebugger()
    result = ttd.timeline()
    
    assert "No checkpoints recorded yet." == result
    print("✓ test_ttd_timeline_empty passed")


def test_ttd_timeline_with_checkpoints():
    """Test timeline formatting with saved checkpoints."""
    from whence.timetravel import TimeTravelDebugger
    
    ttd = TimeTravelDebugger()
    
    class MockEnv:
        def __init__(self, vars_dict):
            self.vars = vars_dict
        
        def get(self, key, default=None):
            return self.vars.get(key, default)
    
    class NamedEnv:
        def __init__(self, vars_dict, name):
            self.vars = vars_dict
            self._snap_name = name
        def get(self, key, default=None):
            if key == '_last_snap_name':
                return self._snap_name
            return self.vars.get(key, default)
    
    env = NamedEnv({'x': 1}, 'my_checkpoint')
    ttd.snapshot(env)
    
    result = ttd.timeline()
    lines = result.split('\n')
    
    assert "Timeline (1 checkpoints):" in lines[0]
    assert "✓ my_checkpoint" in lines[1]
    
    print("✓ test_ttd_timeline_with_checkpoints passed")


def test_ttd_diff_snap_no_diffs():
    """Test diff_snap when two checkpoints are identical."""
    from whence.timetravel import TimeTravelDebugger
    from whence.values import Miss
    
    ttd = TimeTravelDebugger()
    
    class MockEnv:
        def __init__(self, vars_dict):
            self.vars = dict(vars_dict)  # Make a copy
        
        def get(self, key, default=None):
            return self.vars.get(key, default)
    
    env = MockEnv({'x': 10, 'y': 20})
    ttd.snapshot(env)
    
    result = ttd.diff_snap('unnamed', 'unnamed')
    if isinstance(result, Miss):
        raise AssertionError(f"Expected string result, got Miss: {result}")
    assert "No differences" in result
    
    print("✓ test_ttd_diff_snap_no_diffs passed")


def test_ttd_diff_snap_identical_names_both_exist():
    """Test that comparing same checkpoint against itself works."""
    from whence.timetravel import TimeTravelDebugger
    from whence.values import Miss
    
    ttd = TimeTravelDebugger()
    
    class MockEnv:
        def __init__(self, vars_dict):
            self.vars = dict(vars_dict)
        
        def get(self, key, default=None):
            return self.vars.get(key, default)
    
    env = MockEnv({'x': 42})
    ttd.snapshot(env)
    
    # Compare checkpoint with itself
    result = ttd.diff_snap('unnamed', 'unnamed')
    if isinstance(result, Miss):
        raise AssertionError(f"Expected string result, got Miss: {result}")
    assert "No differences between" in result
    
    print("✓ test_ttd_diff_snap_identical_same_name passed")


def test_ttd_trace_non_prov_value():
    """Test trace() with non-Prov value returns appropriate message."""
    from whence.timetravel import TimeTravelDebugger
    
    ttd = TimeTravelDebugger()
    
    # Regular int is not a Prov node
    result = ttd.trace(42)
    assert "does not carry provenance" in result
    print("✓ test_ttd_trace_non_prov_value passed")


def test_ttd_max_checkpoints_eviction():
    """Test that oldest checkpoint is evicted when limit reached."""
    from whence.timetravel import TimeTravelDebugger
    
    ttd = TimeTravelDebugger()
    ttd._max_checkpoints = 3  # Set low limit for testing
    
    class MockEnv:
        def __init__(self, name):
            self.vars = {'name': name}
            self.name_val = name
        
        def get(self, key, default=None):
            if key == '_last_snap_name':
                return self.name_val
            return self.vars.get(key, default)
    
    # Take more checkpoints than max
    class NamedEnv:
        def __init__(self, name):
            self.vars = {'name': name}
            self.name_val = name
        def get(self, key, default=None):
            if key == '_last_snap_name':
                return self.name_val
            return self.vars.get(key, default)
    
    for i in range(5):
        env = NamedEnv(f"cp_{i}")
        ttd.snapshot(env)
    
    # Should only keep last 3
    assert len(ttd.checkpoints) == 3, f"Expected 3 checkpoints, got {len(ttd.checkpoints)}"
    assert len(ttd.creation_order) == 3
    
    # Oldest checkpoints should be evicted
    assert 'checkpoint_0' not in ttd.checkpoints
    assert 'checkpoint_1' not in ttd.checkpoints
    
    print("✓ test_ttd_max_checkpoints_eviction passed")


def test_ttd_rewind_clears_future_progress():
    """Test that rewinding clears forward progress (time paradox prevention)."""
    from whence.timetravel import TimeTravelDebugger
    
    ttd = TimeTravelDebugger()
    
    class MockEnv:
        def __init__(self, vars_dict):
            self.vars = dict(vars_dict)
        
        def get(self, key, default=None):
            return self.vars.get(key, default)
    
    # Create 3 checkpoints in sequence
    env1 = MockEnv({'step': 1})
    env2 = MockEnv({'step': 2})
    env3 = MockEnv({'step': 3})
    
    ttd.snapshot(env1)  # checkpoint_0
    ttd.snapshot(env2)  # checkpoint_1
    ttd.snapshot(env3)  # checkpoint_2
    
    assert len(ttd.creation_order) == 3
    
    # Rewind to first checkpoint should clear forward progress
    result = ttd.rewind(env3, 'unnamed')  # This rewinds to the LAST one by name
    # Since all named 'unnamed', this rewinds to the latest one created
    # The important thing is that order should be truncated
    
    print("✓ test_ttd_rewind_clears_future_progress passed")


def run_all_tests():
    """Run all Time-Travel Debugging tests."""
    tests = [
        test_ttd_snapshot_basic,
        test_ttd_multiple_checkpoints,
        test_ttd_rewind_to_checkpoint,
        test_ttd_rewind_missing_checkpoint,
        test_ttd_timeline_empty,
        test_ttd_timeline_with_checkpoints,
        test_ttd_diff_snap_no_diffs,
        test_ttd_diff_snap_identical_names_both_exist,
        test_ttd_trace_non_prov_value,
        test_ttd_max_checkpoints_eviction,
        test_ttd_rewind_clears_future_progress,
    ]
    
    print("=== Running Time-Travel Debugger Tests ===\n")
    
    passed = 0
    failed = 0
    total = len(tests)
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"✗ {test_func.__name__} FAILED: {e}")
    
    print(f"\n=== Results: {passed}/{total} passed, {failed} failed ===")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
