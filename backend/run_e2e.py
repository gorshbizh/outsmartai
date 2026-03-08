#!/usr/bin/env /Users/yud/repo/outsmartai/.venv/bin/python
"""
E2E Test Runner for Two-Image Grading Pipeline
Run with: /Users/yud/repo/outsmartai/.venv/bin/python run_e2e.py

Tests the new two-image grading pipeline that:
1. Extracts given claims from problem-only image
2. Extracts student claims from solution image
3. Verifies each claim with 2-step derivation limit
4. Applies cascading errors for invalid claims
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


def _parse_files_arg(raw: str) -> set[str]:
    """Parse comma-separated filenames (with or without .png extension)"""
    if not raw:
        return set()
    cleaned = raw.strip()
    if cleaned.startswith("[") and cleaned.endswith("]"):
        cleaned = cleaned[1:-1]
    parts = [p.strip() for p in cleaned.split(",") if p.strip()]
    filenames = set()
    for p in parts:
        if p.lower().endswith('.png'):
            p = p[:-4]
        filenames.add(p)
    return filenames


async def run_two_image_test(
    pipeline,
    problem_path: Path,
    solution_path: Path,
    expected_result: str,
    output_dir: Path,
) -> Dict[str, Any]:
    """Run two-image grading test on a single problem-solution pair"""

    print_section(f"Testing: {problem_path.name} + {solution_path.name}")
    print(f"Expected result: {expected_result.upper()}")

    # Load images
    problem_image = problem_path.read_bytes()
    solution_image = solution_path.read_bytes()

    print(f"  Problem image: {len(problem_image):,} bytes")
    print(f"  Solution image: {len(solution_image):,} bytes")

    # Run the new two-image pipeline
    print("\nRunning Two-Image Grading Pipeline...")
    print("  → ProblemClaimExtractor (extracting givens)")
    print("  → StudentClaimExtractor (extracting student claims)")
    print("  → ClaimVerifier (2-step verification with cascading)")
    print("  → Scorer (calculating final score)")

    try:
        result = await pipeline.grade(
            problem_image_data=problem_image,
            solution_image_data=solution_image,
            problem_id=problem_path.stem,
        )
    except Exception as e:
        print(f"\n❌ Grading failed: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

    # Extract results
    score_data = result.get("score", {})
    total_points = score_data.get("total_points", 0)
    valid_claims = score_data.get("valid_claims", 0)
    invalid_claims = score_data.get("invalid_claims", 0)
    cascading_errors = score_data.get("cascading_errors", 0)

    # Display results
    print_header(f"RESULTS: {solution_path.name}")

    # Score
    if expected_result == "correct":
        score_icon = "✅" if total_points >= 80 else "⚠️"
    else:
        score_icon = "✅" if total_points < 80 else "⚠️"

    print(f"{score_icon} SCORE: {total_points}/100")
    print(f"   Expected: {'HIGH (correct solution)' if expected_result == 'correct' else 'LOW (wrong solution)'}")

    # Problem claims (givens)
    problem_claims = result.get("problem_claims", {})
    given_claims = problem_claims.get("given_claims", [])
    print(f"\n📋 Given Claims Extracted: {len(given_claims)}")
    for claim in given_claims[:5]:
        print(f"   [{claim.get('claim_id')}] {claim.get('type')} {claim.get('args')}")
    if len(given_claims) > 5:
        print(f"   ... and {len(given_claims) - 5} more")

    # Student claims
    student_claims_data = result.get("student_claims", {})
    student_claims = student_claims_data.get("student_claims", [])
    print(f"\n✏️ Student Claims Extracted: {len(student_claims)}")
    for claim in student_claims[:5]:
        deps = claim.get('depends_on', [])
        print(f"   [{claim.get('claim_id')}] {claim.get('type')} {claim.get('args')}")
        if deps:
            print(f"       depends_on: {deps}")
    if len(student_claims) > 5:
        print(f"   ... and {len(student_claims) - 5} more")

    # Verification results
    verification_results = result.get("verification_results", [])
    print(f"\n🔍 Verification Summary:")
    print(f"   ✓ Valid:    {valid_claims}")
    print(f"   ✗ Invalid:  {invalid_claims}")
    print(f"   ↯ Cascading: {cascading_errors}")

    # Show details
    for vr in verification_results:
        claim_id = vr.get("claim_id", "?")
        verdict = vr.get("verdict", "?")
        depth = vr.get("derivation_depth", -1)

        if verdict == "valid":
            print(f"   ✓ {claim_id}: valid (depth={depth})")
        elif verdict == "invalid":
            error = vr.get("error_details", "")[:50]
            print(f"   ✗ {claim_id}: INVALID - {error}")
        elif verdict == "cascading_error":
            root = vr.get("root_cause_claim", "?")
            print(f"   ↯ {claim_id}: cascading from {root}")

    # Deductions
    deductions = score_data.get("deductions", [])
    if deductions:
        print(f"\n❌ Deductions:")
        for d in deductions:
            print(f"   -{d.get('deducted_points', 0)} pts: {d.get('reason', '')[:60]}")

    # Summary
    print(f"\n📊 Summary: {score_data.get('summary', 'N/A')}")

    # Check if result matches expectation
    test_passed = False
    if expected_result == "correct" and total_points >= 80:
        test_passed = True
        print(f"\n✅ TEST PASSED: Correct solution got high score ({total_points}/100)")
    elif expected_result == "wrong" and total_points < 80:
        test_passed = True
        print(f"\n✅ TEST PASSED: Wrong solution got low score ({total_points}/100)")
    elif expected_result == "correct":
        print(f"\n⚠️ TEST ISSUE: Correct solution got lower than expected ({total_points}/100)")
    else:
        print(f"\n⚠️ TEST ISSUE: Wrong solution got higher than expected ({total_points}/100)")

    # Save results
    output_file = output_dir / f"e2e_result_{problem_path.stem}_{solution_path.stem}.json"
    output_file.write_text(json.dumps({
        "problem_image": str(problem_path),
        "solution_image": str(solution_path),
        "expected_result": expected_result,
        "test_passed": test_passed,
        "result": result,
    }, indent=2, ensure_ascii=False))

    print(f"\n💾 Results saved to: {output_file}")

    return {
        "success": True,
        "test_passed": test_passed,
        "expected": expected_result,
        "score": total_points,
        "valid": valid_claims,
        "invalid": invalid_claims,
        "cascading": cascading_errors,
    }


async def main():
    """Run E2E test with two-image grading pipeline"""

    load_dotenv(find_dotenv())

    print_header("TWO-IMAGE GRADING PIPELINE E2E TEST")

    # Configuration check
    print("📋 Configuration Check:")

    provider = os.getenv('LLM_PROVIDER', 'mock')
    api_key = os.getenv('LLM_API_KEY', '')

    print(f"   LLM Provider: {provider}")
    print(f"   API Key: {'✓ Set' if api_key else '✗ Not set (will use mock)'}")

    if provider == 'mock' or not api_key:
        print("\n⚠️  Using MOCK LLM - results will be simulated")
        print("   For real grading, set environment variables:")
        print("     export LLM_PROVIDER=openai")
        print("     export LLM_API_KEY=your_key")

    # Find problem-solution pairs
    print_section("Finding Problem-Solution Pairs")

    images_dir = BACKEND_DIR / "tests/data"
    pairs = find_problem_solution_pairs(images_dir)

    parser = argparse.ArgumentParser(description="Run E2E tests on problem-solution pairs")
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

    # Initialize pipeline
    print_section("Initializing Two-Image Grading Pipeline")

    try:
        import app as app_module
        print("✓ Imported app module")
    except Exception as e:
        print(f"❌ Failed to import app: {e}")
        import traceback
        traceback.print_exc()
        return

    pipeline = app_module.two_image_pipeline
    print("✓ Using TwoImageGradingPipeline")
    print(f"   - ProblemClaimExtractor: {type(pipeline.problem_extractor).__name__}")
    print(f"   - StudentClaimExtractor: {type(pipeline.student_extractor).__name__}")
    print(f"   - ClaimVerifier: {type(pipeline.claim_verifier).__name__}")
    print(f"   - Scorer: {type(pipeline.scorer).__name__}")

    output_dir = BACKEND_DIR / "tests/output"
    output_dir.mkdir(exist_ok=True)

    # Run tests
    results = []
    for problem_path, solution_path, expected_result in pairs:
        result = await run_two_image_test(
            pipeline=pipeline,
            problem_path=problem_path,
            solution_path=solution_path,
            expected_result=expected_result,
            output_dir=output_dir,
        )
        results.append({
            "problem": problem_path.name,
            "solution": solution_path.name,
            "expected": expected_result,
            **result,
        })

    # Summary
    print_header("TEST SUMMARY")

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
        print("   This may indicate issues with claim extraction or verification.")
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
