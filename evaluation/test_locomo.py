"""Locomo evaluation metrics."""

import sys
sys.path.insert(0, ".")

from evaluation.metrics.locomo import LocomoEvaluator

# Test: If actual_answer matches expected_answer, should Pass
result = LocomoEvaluator().evaluate_answer("Q", "A", "A")
if result != "Pass":
    print(f"FAILED: expected 'Pass' but got '{result}'")
    sys.exit(1)

# Test: If actual_answer does NOT match expected_answer, should Fail
result = LocomoEvaluator().evaluate_answer("Q", "A", "B")
if result != "Fail":
    print(f"FAILED: expected 'Fail' but got '{result}'")
    sys.exit(1)

print("PASSED: All tests pass")
sys.exit(0)