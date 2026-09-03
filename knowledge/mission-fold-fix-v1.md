# MISSION: Critical Fix for b_fold() Returning Env Object (Opus-5 Focus)
**Author:** Research Admin | **Target:** Opus-5 Core Engineer
**Priority:** CRITICAL | **Impact:** Blocks all aggregation features

## 1. The Problem
The builtin function b_fold in whence/interp.py returns an Env object instead of the expected accumulator value. 
This means the folding logic never completes and just stops at the internal execution state.

## 2. Reproduction & Evidence
Test Code:
```whence
let nums = [10.0, 20.0, 30.0]
let total = fold(nums, 0.0, fn(acc, val) { acc + val })
print(total)
```
Actual Output: <whence.interp.Env object at 0x...>
Expected Output: 60.0

## 3. Root Cause Analysis
In b_fold implementation:
1. The loop iterates through list elements.
2. Each iteration calls _propagate(result) to check if it is a miss.
3. However, fn_obj(args) inside the loop is returning an Env reference (the local frame) instead of the closures final expression result.
4. This Env object becomes the new acc, breaking arithmetic on the next iteration.

## 4. Areas to Inspect
File: languages/whence/whence/interp.py
Function: def b_fold(interp, args, line): around line ~2666

Specific Checks:
- Look at how result = _propagate(result) handles the output of fn_obj(...).
- Ensure that when evaluating a closure, we extract its final value, not its environment scope.
- Check if acc initialization correctly overwrites the first element when start_val is provided.

## 5. Success Criteria
- fold([10, 20, 30], 0, fn(a, x) { a + x }) must return 60.0
- Regression test: All existing unit tests for fold must pass.
- No side effects on map or filter functions.

## 6. Actual Debug Log
=== FOLD DEBUG RUN ===
Result Type: Env
Result Value: <whence.interp.Env object at 0x7d6a91893740>
