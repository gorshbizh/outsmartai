#!/usr/bin/env python3
"""
E2E Test Runner for Simple LLM Grader

Run with: python run_simple_grader_e2e.py
         python run_simple_grader_e2e.py --problem geo_6
         python run_simple_grader_e2e.py --type correct
         python run_simple_grader_e2e.py --use-tool

Tests the simple single-shot grading approach:
- Always uses two images: problem image + solution image
- Extracts givens from problem image with confidence scores
- Extracts steps from solution image with confidence scores
- Minor issues: -2 points each
- Major issues: -10 points each
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
    print("\n" + "=" * 80)
    print(text)
    print("=" * 80 + "\n")


def print_section(text):
    """Print formatted section"""
    print("\n" + "-" * 80)
    print(text)
    print("-" * 80 + "\n")


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


async def run_simple_grader_test(
    problem_path: Path,
    solution_path: Path,
    expected_result: str,
    output_dir: Path,
    use_tool: bool = False,
) -> Dict[str, Any]:
    """Run test using the simple LLM grader (always two-image mode)"""

    print_section(f"Testing: {problem_path.name} + {solution_path.name}")
    print(f"Expected result: {expected_result.upper()}")
    print(f"Use tool: {use_tool}")
    print(f"Image mode: Two separate images (problem + solution)")

    # Load images
    problem_image = problem_path.read_bytes()
    solution_image = solution_path.read_bytes()

    print(f"  Problem image: {len(problem_image):,} bytes")
    print(f"  Solution image: {len(solution_image):,} bytes")

    print("\nRunning Simple LLM Grader...")
    print("  → Two-image mode: extracting givens from problem, steps from solution")
    print("  → Minor issues: -3 points each")
    print("  → Major issues: -35 pts (first) + -10 pts (cascading)")

    try:
        from graders.simple_llm_grader import SimpleLLMGrader
        import app as app_module

        grader = SimpleLLMGrader(app_module.llm_service)

        # Always use separate problem and solution images
        result = await grader.grade(
            solution_image=solution_image,
            problem_image=problem_image,
            max_points=100,
            use_tool=use_tool
        )

    except Exception as e:
        print(f"\n❌ Grading failed: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

    # Display results
    print_header(f"RESULTS: {solution_path.name}")

    # Score
    total_points = result.total_score
    max_points = result.max_score

    if expected_result == "correct":
        score_icon = "✅" if total_points >= 80 else "⚠️"
    else:
        score_icon = "✅" if total_points < 80 else "⚠️"

    print(f"{score_icon} SCORE: {total_points}/{max_points}")
    print(f"   Expected: {'HIGH (≥80, correct solution)' if expected_result == 'correct' else 'LOW (<80, wrong solution)'}")

    # Assessment
    print(f"\n📋 Assessment:")
    print(f"   Problem goal: {result.problem_goal}")
    print(f"   Correct answer: {result.correct_answer}")
    print(f"   Student answer: {result.student_answer}")
    print(f"   Is correct: {'✓' if result.is_correct else '✗'}")
    print(f"   Is reasoning valid: {'✓' if result.is_reasoning_valid else '✗'}")

    # Display extracted givens
    if result.givens:
        print(f"\n📝 EXTRACTED GIVENS ({len(result.givens)}):")
        for g in result.givens:
            conf = g.confidence if hasattr(g, 'confidence') else g.get('confidence', 0)
            fact = g.fact if hasattr(g, 'fact') else g.get('fact', '')
            source = g.source if hasattr(g, 'source') else g.get('source', '?')
            conf_indicator = "HIGH" if conf >= 0.8 else "MED" if conf >= 0.5 else "LOW"
            print(f"   [{conf_indicator} {conf:.2f}] [{source}] {fact}")
    else:
        print(f"\n📝 No givens extracted")

    # Display extracted steps
    if result.steps:
        print(f"\n📝 EXTRACTED STEPS ({len(result.steps)}):")
        for s in result.steps:
            step_num = s.step_number if hasattr(s, 'step_number') else s.get('step_number', 0)
            content = s.content if hasattr(s, 'content') else s.get('content', '')
            conf = s.confidence if hasattr(s, 'confidence') else s.get('confidence', 0)
            is_valid = s.is_valid if hasattr(s, 'is_valid') else s.get('is_valid')
            issue = s.issue if hasattr(s, 'issue') else s.get('issue')

            conf_indicator = "HIGH" if conf >= 0.8 else "MED" if conf >= 0.5 else "LOW"
            valid_indicator = "✓" if is_valid else "✗" if is_valid is False else "?"

            # Truncate content for display
            content_display = content[:70] + "..." if len(content) > 70 else content
            print(f"   Step {step_num}: [{conf_indicator} {conf:.2f}] [{valid_indicator}] {content_display}")
            if issue:
                print(f"            └─ Issue: {issue}")
    else:
        print(f"\n📝 No steps extracted")

    # Issues
    if result.minor_issues:
        print(f"\n⚠️ Minor Issues ({len(result.minor_issues)}):")
        for issue in result.minor_issues:
            step_ref = f" (step {issue.get('step_number')})" if issue.get('step_number') else ""
            print(f"   • {issue.get('description')}{step_ref} (-{issue.get('deduction', 2)} pts)")
    else:
        print(f"\n✓ No minor issues")

    if result.major_issues:
        print(f"\n❌ Major Issues ({len(result.major_issues)}):")
        for issue in result.major_issues:
            issue_type = issue.get('type', 'error')
            step_ref = f" (step {issue.get('step_number')})" if issue.get('step_number') else ""
            type_label = "Root cause" if issue_type == "root_cause" else "Cascading"
            print(f"   • {type_label}: {issue.get('description')}{step_ref}")
    else:
        print(f"\n✓ No major issues")

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
    output_file = output_dir / f"e2e_simple_{problem_path.stem}_{solution_path.stem}.json"
    output_data = {
        "problem_image": str(problem_path),
        "solution_image": str(solution_path),
        "expected_result": expected_result,
        "test_passed": test_passed,
        "grader_mode": "simple_llm",
        "use_tool": use_tool,
        "image_mode": "two_images",
        "result": result.to_dict(),
    }
    output_file.write_text(json.dumps(output_data, indent=2, ensure_ascii=False))

    print(f"\n💾 Results saved to: {output_file}")

    return {
        "success": True,
        "test_passed": test_passed,
        "expected": expected_result,
        "score": total_points,
        "is_correct": result.is_correct,
        "is_reasoning_valid": result.is_reasoning_valid,
        "givens_count": len(result.givens),
        "steps_count": len(result.steps),
        "minor_issues": len(result.minor_issues),
        "major_issues": len(result.major_issues),
    }


async def main():
    """Run E2E test with simple LLM grader"""

    load_dotenv(find_dotenv())

    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Run E2E tests using Simple LLM Grader"
    )
    parser.add_argument(
        "--problem",
        default="",
        help="Filter by problem name (e.g., geo_1, geo_6)",
    )
    parser.add_argument(
        "--type",
        choices=["correct", "wrong", "all"],
        default="all",
        help="Filter by solution type",
    )
    parser.add_argument(
        "--use-tool",
        action="store_true",
        help="Enable image inspection tool",
    )
    args, _ = parser.parse_known_args()

    print_header("SIMPLE LLM GRADER E2E TEST")

    # Configuration check
    print("📋 Configuration Check:")

    provider = os.getenv('LLM_PROVIDER', 'mock')
    api_key = os.getenv('LLM_API_KEY', '')

    print(f"   LLM Provider: {provider}")
    print(f"   API Key: {'✓ Set' if api_key else '✗ Not set (will use mock)'}")
    print(f"   Grader Mode: SIMPLE (single-shot evaluation)")
    print(f"   Image Inspection Tool: {'Enabled' if args.use_tool else 'Disabled'}")
    print(f"   Image Mode: Two separate images (problem + solution)")

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
    print_section("Initializing Simple LLM Grader")

    try:
        import app as app_module
        print("✓ Imported app module")
        print("✓ Using SimpleLLMGrader")
        print("   - Two-image mode: problem + solution")
        print("   - Extracts givens with confidence scores")
        print("   - Extracts steps with confidence scores")
        print("   - Minor (-3) vs Major (-35/-10) issue classification")
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
        result = await run_simple_grader_test(
            problem_path=problem_path,
            solution_path=solution_path,
            expected_result=expected_result,
            output_dir=output_dir,
            use_tool=args.use_tool,
        )
        results.append({
            "problem": problem_path.name,
            "solution": solution_path.name,
            "expected": expected_result,
            "grader_mode": "simple_llm",
            **result,
        })

    # Summary
    print_header("TEST SUMMARY")

    print(f"Grader mode: SIMPLE LLM (two-image)")
    print(f"Image inspection tool: {'Enabled' if args.use_tool else 'Disabled'}")
    passed = sum(1 for r in results if r.get("test_passed", False))
    failed = len(results) - passed

    print(f"\nTotal tests: {len(results)}")
    print(f"  ✅ Passed: {passed}")
    print(f"  ❌ Failed: {failed}")

    print("\nDetailed Results:")
    for r in results:
        icon = "✅" if r.get("test_passed") else "❌"
        score = r.get("score", "N/A")
        expected = r.get("expected", "?")
        correct = "✓" if r.get("is_correct") else "✗"
        givens = r.get("givens_count", 0)
        steps = r.get("steps_count", 0)
        minor = r.get("minor_issues", 0)
        major = r.get("major_issues", 0)
        print(f"  {icon} {r['solution']}: {score}/100 (expected: {expected}) [correct:{correct}, givens:{givens}, steps:{steps}, minor:{minor}, major:{major}]")

    if failed > 0:
        print(f"\n⚠️ {failed} test(s) did not match expectations.")
    else:
        print(f"\n✅ All tests passed!")

    # Compare with LLM-vision grader if results exist
    print_section("Comparison with LLM-Vision Grader (if available)")

    for r in results:
        solution_name = r["solution"].replace(".png", "")
        problem_name = r["problem"].replace(".png", "")
        llm_vision_file = output_dir / f"e2e_llm_vision_{problem_name}_{solution_name}.json"

        if llm_vision_file.exists():
            llm_vision_data = json.loads(llm_vision_file.read_text())
            llm_vision_score = llm_vision_data.get("result", {}).get("total_score", "N/A")
            simple_score = r.get("score", "N/A")

            if llm_vision_score != "N/A" and simple_score != "N/A":
                diff = simple_score - llm_vision_score
                diff_str = f"+{diff}" if diff > 0 else str(diff)
                print(f"  {r['solution']}:")
                print(f"    Simple:     {simple_score}/100")
                print(f"    LLM-Vision: {llm_vision_score}/100")
                print(f"    Difference: {diff_str}")
        else:
            print(f"  {r['solution']}: No LLM-Vision result to compare")


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
