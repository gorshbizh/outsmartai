#!/usr/bin/env /Users/yud/repo/outsmartai/.venv/bin/python
"""
E2E Test Runner for LLM-Vision Grading Pipeline
Run with: /Users/yud/repo/outsmartai/.venv/bin/python run_llm_vision_e2e.py

Tests the pure LLM-based grading pipeline with tool-calling:
1. Phase 1: Problem Understanding (analyzing problem image)
2. Phase 2: Student Work Extraction (extracting steps)
3. Phase 3: Step Verification (with image re-inspection tools)
4. Phase 4: Scoring (cascading error tracking)
"""

import os
import sys
import asyncio
import json
import re
import argparse
from dotenv import load_dotenv, find_dotenv
from pathlib import Path
from typing import List, Tuple, Dict, Any

# Add backend to path
BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))


def print_header(text):
    """Print formatted header"""
    print("\n" + "="*80)
    print(text)
    print("="*80 + "\n")


def print_section(text):
    """Print formatted section"""
    print("\n" + "-"*80)
    print(text)
    print("-"*80 + "\n")


def find_problem_solution_pairs(images_dir: Path) -> List[Tuple[Path, Path, str]]:
    """
    Find pairs of (problem_image, solution_image, expected_result).

    Naming convention:
    - geo_N.png or alg_N.png = problem image
    - geo_N_c_*.png = correct solution (expect high score)
    - geo_N_w_*.png = wrong solution (expect deductions)

    Returns:
        List of (problem_path, solution_path, "correct" | "wrong")
    """
    pairs = []

    # Find all problem images (geo_N.png, alg_N.png)
    problem_pattern = re.compile(r'^(geo|alg)_(\d+)\.png$')

    for problem_path in images_dir.glob("*.png"):
        match = problem_pattern.match(problem_path.name)
        if not match:
            continue

        prefix = match.group(1)  # geo or alg
        num = match.group(2)      # problem number

        # Find corresponding solution images
        # Correct solutions: geo_N_c_*.png
        correct_pattern = f"{prefix}_{num}_c_*.png"
        for solution_path in images_dir.glob(correct_pattern):
            pairs.append((problem_path, solution_path, "correct"))

        # Wrong solutions: geo_N_w_*.png
        wrong_pattern = f"{prefix}_{num}_w_*.png"
        for solution_path in images_dir.glob(wrong_pattern):
            pairs.append((problem_path, solution_path, "wrong"))

    return sorted(pairs, key=lambda x: (x[0].name, x[1].name))


async def run_llm_vision_test(
    problem_path: Path,
    solution_path: Path,
    expected_result: str,
    output_dir: Path,
) -> Dict[str, Any]:
    """Run test using the LLM-vision grader with tool-calling"""

    print_section(f"Testing: {problem_path.name} + {solution_path.name}")
    print(f"Expected result: {expected_result.upper()}")

    # Load images
    problem_image = problem_path.read_bytes()
    solution_image = solution_path.read_bytes()

    print(f"  Problem image: {len(problem_image):,} bytes")
    print(f"  Solution image: {len(solution_image):,} bytes")

    print("\nRunning LLM-Vision Grading Pipeline...")
    print("  → Phase 1: Problem Understanding (analyzing problem image)")
    print("  → Phase 2: Student Work Extraction (extracting steps)")
    print("  → Phase 3: Step Verification (with image re-inspection tools)")
    print("  → Phase 4: Scoring (cascading error tracking)")

    try:
        from graders.llm_native_grader import LLMNativeGeometryGrader
        import app as app_module

        grader = LLMNativeGeometryGrader(app_module.llm_service)
        result = await grader.grade(
            problem_image=problem_image,
            student_image=solution_image,
            max_points=100
        )
    except Exception as e:
        print(f"\n❌ Grading failed: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

    # Extract results
    total_points = result.total_score
    max_points = result.max_score
    goal_achieved = result.goal_achieved

    # Count step verdicts
    valid_steps = sum(1 for sf in result.steps_feedback if sf.verdict == "valid")
    imperfect_steps = sum(1 for sf in result.steps_feedback if sf.verdict == "imperfect")
    invalid_steps = sum(1 for sf in result.steps_feedback if sf.verdict == "invalid")
    cascading_errors = sum(1 for sf in result.steps_feedback if sf.verdict == "cascading_error")

    # Display results
    print_header(f"RESULTS: {solution_path.name}")

    # Score
    if expected_result == "correct":
        score_icon = "✅" if total_points >= 80 else "⚠️"
    else:
        score_icon = "✅" if total_points < 80 else "⚠️"

    print(f"{score_icon} SCORE: {total_points}/{max_points}")
    print(f"   Expected: {'HIGH (correct solution)' if expected_result == 'correct' else 'LOW (wrong solution)'}")
    print(f"   Goal achieved: {'✓' if goal_achieved else '✗'}")

    # Problem analysis
    if result.problem_analysis:
        pa = result.problem_analysis
        print(f"\n📋 Problem Analysis:")
        print(f"   Goal: {pa.goal}")
        print(f"   Givens: {len(pa.givens)} items")
        for i, g in enumerate(pa.givens[:3]):
            print(f"     {i+1}. {g}")
        if len(pa.givens) > 3:
            print(f"     ... and {len(pa.givens) - 3} more")

    # Student work
    if result.student_work:
        sw = result.student_work
        print(f"\n✏️ Student Work Extracted:")
        print(f"   Constructions: {len(sw.constructions)}")
        print(f"   Steps: {len(sw.steps)}")
        if sw.final_answer:
            print(f"   Final answer: {sw.final_answer}")

        for step in sw.steps[:5]:
            print(f"   [{step.step_id}] {step.normalized_claim[:60]}...")
        if len(sw.steps) > 5:
            print(f"   ... and {len(sw.steps) - 5} more")

    # Verification results
    print(f"\n🔍 Verification Summary:")
    print(f"   ✓ Valid:     {valid_steps}")
    print(f"   ≈ Imperfect: {imperfect_steps} (correct conclusion, minor reasoning issues)")
    print(f"   ✗ Invalid:   {invalid_steps}")
    print(f"   ↯ Cascading: {cascading_errors}")

    # Show step details with full information
    print(f"\n📝 Detailed Step-by-Step Analysis:")
    for i, sf in enumerate(result.steps_feedback):
        step = result.student_work.steps[i]
        print(f"\n   [{sf.step_id}] {step.normalized_claim}")
        print(f"       Raw: {step.raw_text[:80]}..." if len(step.raw_text) > 80 else f"       Raw: {step.raw_text}")
        print(f"       Depends on: {', '.join(step.depends_on)}")

        if sf.verdict == "valid":
            print(f"       ✓ VALID ({sf.evidence_source})")
            if sf.points_deducted > 0:
                print(f"       📝 Conclusion CORRECT, but reasoning has minor issues: -{sf.points_deducted} points")
            print(f"       Reason: {sf.justification}")
        elif sf.verdict == "imperfect":
            print(f"       ≈ IMPERFECT ({sf.evidence_source}) - Conclusion correct, reasoning flawed")
            print(f"       📝 Minor deduction: -{sf.points_deducted} points")
            print(f"       Reason: {sf.justification}")
            if sf.error_details:
                print(f"       Details: {sf.error_details}")
        elif sf.verdict == "invalid":
            print(f"       ✗ INVALID - {sf.error_type}")
            print(f"       Reason: {sf.justification}")
            if sf.error_details:
                print(f"       Details: {sf.error_details}")
        elif sf.verdict == "cascading_error":
            print(f"       ↯ CASCADING ERROR from {sf.root_cause_step}")
            print(f"       Reason: {sf.justification}")

        # Show tool calls if any
        if sf.tool_calls_made:
            for tc in sf.tool_calls_made:
                print(f"       🔧 Tool used: {tc.tool_name}")
                if tc.result:
                    print(f"          Result: {tc.result.get('answer', 'N/A')} (confidence: {tc.result.get('confidence', 'N/A')})")
                    print(f"          Evidence: {tc.result.get('evidence', 'N/A')[:100]}...")

    # Cascading chains
    if result.cascading_chains:
        print(f"\n🔗 Cascading Error Chains:")
        for chain in result.cascading_chains:
            print(f"   {' → '.join(chain)}")

    # Summary
    print(f"\n📊 Summary: {result.summary}")

    # Check if result matches expectation
    test_passed = False
    if expected_result == "correct" and total_points >= 80:
        test_passed = True
        print(f"\n✅ TEST PASSED: Correct solution got high score ({total_points}/{max_points})")
    elif expected_result == "wrong" and total_points < 80:
        test_passed = True
        print(f"\n✅ TEST PASSED: Wrong solution got low score ({total_points}/{max_points})")
    elif expected_result == "correct":
        print(f"\n⚠️ TEST ISSUE: Correct solution got lower than expected ({total_points}/{max_points})")
    else:
        print(f"\n⚠️ TEST ISSUE: Wrong solution got higher than expected ({total_points}/{max_points})")

    # Save results
    output_file = output_dir / f"e2e_llm_vision_{problem_path.stem}_{solution_path.stem}.json"
    output_file.write_text(json.dumps({
        "problem_image": str(problem_path),
        "solution_image": str(solution_path),
        "expected_result": expected_result,
        "test_passed": test_passed,
        "grader_mode": "llm_vision",
        "result": result.to_dict(),
    }, indent=2, ensure_ascii=False))

    print(f"\n💾 Results saved to: {output_file}")

    return {
        "success": True,
        "test_passed": test_passed,
        "expected": expected_result,
        "score": total_points,
        "valid": valid_steps,
        "imperfect": imperfect_steps,
        "invalid": invalid_steps,
        "cascading": cascading_errors,
    }


async def main():
    """Run E2E test with LLM-vision grading pipeline"""

    load_dotenv(find_dotenv())

    # Parse arguments
    parser = argparse.ArgumentParser(description="Run E2E tests on problem-solution pairs using LLM-vision grader")
    parser.add_argument(
        "--problem",
        default="",
        help="Filter by problem name (e.g., geo_1, geo_2)",
    )
    parser.add_argument(
        "--type",
        choices=["correct", "wrong", "all"],
        default="all",
        help="Filter by solution type",
    )
    args, _ = parser.parse_known_args()

    print_header("LLM-VISION GRADING PIPELINE E2E TEST")

    # Configuration check
    print("📋 Configuration Check:")

    provider = os.getenv('LLM_PROVIDER', 'mock')
    api_key = os.getenv('LLM_API_KEY', '')

    print(f"   LLM Provider: {provider}")
    print(f"   API Key: {'✓ Set' if api_key else '✗ Not set (will use mock)'}")
    print(f"   Grader Mode: LLM-VISION (pure LLM with tool-calling)")

    if provider == 'mock' or not api_key:
        print("\n⚠️  Using MOCK LLM - results will be simulated")
        print("   For real grading, set environment variables:")
        print("     export LLM_PROVIDER=openai")
        print("     export LLM_API_KEY=your_key")

    # Find problem-solution pairs
    print_section("Finding Problem-Solution Pairs")

    images_dir = BACKEND_DIR / "tests/data"
    pairs = find_problem_solution_pairs(images_dir)

    # Filter pairs
    if args.problem:
        pairs = [(p, s, e) for p, s, e in pairs if args.problem in p.stem]
    if args.type != "all":
        pairs = [(p, s, e) for p, s, e in pairs if e == args.type]

    if not pairs:
        print("❌ No problem-solution pairs found.")
        print(f"   Looked in: {images_dir}")
        print("\nExpected naming convention:")
        print("   geo_N.png        - Problem image")
        print("   geo_N_c_1.png    - Correct solution")
        print("   geo_N_w_1.png    - Wrong solution")
        return

    print(f"✓ Found {len(pairs)} test pair(s):")
    for problem, solution, expected in pairs:
        icon = "✓" if expected == "correct" else "✗"
        print(f"   {icon} {problem.name} + {solution.name} ({expected})")

    # Initialize
    print_section("Initializing LLM-Vision Grading Pipeline")

    try:
        import app as app_module
        print("✓ Imported app module")
        print("✓ Using LLMNativeGeometryGrader")
        print("   - 4-phase pipeline with tool-calling")
        print("   - Image re-inspection during verification")
    except Exception as e:
        print(f"❌ Failed to import app: {e}")
        import traceback
        traceback.print_exc()
        return

    output_dir = BACKEND_DIR / "tests/output"
    output_dir.mkdir(exist_ok=True)

    # Run tests
    results = []
    for problem_path, solution_path, expected_result in pairs:
        result = await run_llm_vision_test(
            problem_path=problem_path,
            solution_path=solution_path,
            expected_result=expected_result,
            output_dir=output_dir,
        )
        results.append({
            "problem": problem_path.name,
            "solution": solution_path.name,
            "expected": expected_result,
            "grader_mode": "llm_vision",
            **result,
        })

    # Summary
    print_header("TEST SUMMARY")

    print(f"Grader mode: LLM-VISION")
    passed = sum(1 for r in results if r.get("test_passed", False))
    failed = len(results) - passed

    print(f"Total tests: {len(results)}")
    print(f"  ✅ Passed: {passed}")
    print(f"  ❌ Failed: {failed}")

    print("\nDetailed Results:")
    for r in results:
        icon = "✅" if r.get("test_passed") else "❌"
        score = r.get("score", "N/A")
        expected = r.get("expected", "?")
        print(f"  {icon} {r['solution']}: {score}/100 (expected: {expected})")

    if failed > 0:
        print(f"\n⚠️ {failed} test(s) did not match expectations.")
        print("   This may indicate issues with extraction or verification.")
    else:
        print(f"\n✅ All tests passed!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n❌ Test cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
