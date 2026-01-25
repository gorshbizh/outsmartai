#!/usr/bin/env /Users/yud/repo/outsmartai/.venv/bin/python
"""
Simple E2E Test Runner - No dependencies on shell scripts
Run with: /Users/yud/repo/outsmartai/.venv/bin/python run_e2e.py
"""

import os
import sys
import asyncio
import json
import re
import argparse
from dotenv import load_dotenv, find_dotenv
from pathlib import Path

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


def _parse_indices_arg(raw: str) -> set[int]:
    if not raw:
        return set()
    cleaned = raw.strip()
    if cleaned.startswith("[") and cleaned.endswith("]"):
        cleaned = cleaned[1:-1]
    parts = [p.strip() for p in cleaned.split(",") if p.strip()]
    indices = set()
    for p in parts:
        if p.isdigit():
            indices.add(int(p))
    return indices


def _filter_images_by_indices(image_paths, indices: set[int]):
    if not indices:
        return image_paths
    filtered = []
    for path in image_paths:
        match = re.search(r"(\d+)", path.stem)
        if match and int(match.group(1)) in indices:
            filtered.append(path)
    return filtered


async def main():
    """Run E2E test with all PNGs in tests/data"""
    
    load_dotenv(find_dotenv())

    print_header("E2E GRADING TEST: Diameter-Right Angle Problem")
    
    # Step 1: Check configuration
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
        print("\n   Continuing with mock data...")
    
    # Step 2: Load images
    print_section("Step 1: Loading Test Images")
    
    images_dir = BACKEND_DIR / "tests/data"
    image_paths = sorted(p for p in images_dir.glob("*.png") if p.is_file())

    parser = argparse.ArgumentParser(description="Run E2E tests on selected PNGs")
    parser.add_argument(
        "--indices",
        default="",
        help="Comma-separated indices to test, e.g. 2,3 or [2, 3] (matches digits in filename)",
    )
    args, _ = parser.parse_known_args()
    indices = _parse_indices_arg(args.indices)
    if indices:
        image_paths = _filter_images_by_indices(image_paths, indices)
    
    if not image_paths:
        print("❌ No test images found.")
        print(f"   Looked in: {images_dir}")
        if indices:
            print(f"   Filtered by indices: {sorted(indices)}")
        print("\nPlease add a PNG image to tests/data/")
        return
    
    print(f"✓ Found {len(image_paths)} image(s):")
    for img in image_paths:
        print(f"   - {img.name} ({img.stat().st_size:,} bytes)")
    
    # Step 3: Import and initialize
    print_section("Step 2: Initializing Grading Pipeline")
    
    try:
        import app as app_module
        print("✓ Imported app module")
    except Exception as e:
        print(f"❌ Failed to import app: {e}")
        print("\nMake sure you're running from the backend directory:")
        print("  cd /Users/yud/repo/outsmartai/backend")
        print("  python run_e2e.py")
        return
    
    llm_service = app_module.LLMService()
    pipeline = app_module.GradingPipeline(llm_service)
    print("✓ Initialized LLM service and grading pipeline")
    
    output_dir = BACKEND_DIR / "tests/output"
    output_dir.mkdir(exist_ok=True)

    for image_path in image_paths:
        image_bytes = image_path.read_bytes()

        # Step 4: Analyze image
        print_section(f"Step 3: Analyzing Image with LLM ({image_path.name})")
        
        try:
            print("Running LLM image analysis...")
            analysis = await llm_service.analyze_image(image_bytes)
            print("✓ Analysis complete")
            
            text_desc = analysis.get('text_description', 'N/A')
            draw_desc = analysis.get('drawing_description', 'N/A')
            
            print(f"\n📝 Text extracted: {len(text_desc)} characters")
            print(f"   {text_desc[:120]}...")
            
            print(f"\n🎨 Drawing described: {len(draw_desc)} characters")
            print(f"   {draw_desc[:120]}...")
            
            if 'steps' in analysis:
                print(f"\n📋 Steps found: {len(analysis['steps'])}")
                for i, step in enumerate(analysis['steps'][:3], 1):
                    print(f"   {i}. {step[:50]}...")
            
        except Exception as e:
            print(f"❌ Image analysis failed: {e}")
            import traceback
            traceback.print_exc()
            continue
        
        # Step 5: Run grading pipeline
        print_section("Step 4: Running Multi-Agent Grading Pipeline")
        
        print("Executing agents:")
        print("  → A1: StepExtractorAgent")
        print("  → A2: ClaimGeneratorAgent")
        print("  → GeometryFormalizerAgent")
        print("  → H1: FormalGeoStepGrader (if available)")
        print("  → A3: RubricScorerAgent")
        print("  → A4: RefereeAgent")
        
        try:
            grading_result = await pipeline.grade(
                problem_id="diameter_right_angle",
                text_description=analysis.get("text_description", ""),
                drawing_description=analysis.get("drawing_description", ""),
                image_data=image_bytes,
                use_formalgeo=True
            )
            print("\n✓ Grading complete!")
            
        except Exception as e:
            print(f"\n❌ Grading failed: {e}")
            import traceback
            traceback.print_exc()
            continue
        
        # Step 6: Display results
        print_header(f"GRADING RESULTS ({image_path.name})")
        
        score = grading_result.get('score_total', 0)
        max_score = grading_result.get('score_max', 100)
        percentage = (score / max_score * 100) if max_score > 0 else 0
        
        print(f"🎯 FINAL SCORE: {score}/{max_score} ({percentage:.1f}%)")
        
        # Check if FormalGeo was used
        formalgeo_used = grading_result.get('formalgeo_used', False)
        print(f"🔬 FormalGeo Grading: {'✅ ENABLED' if formalgeo_used else '❌ NOT USED'}")
        
        # Show steps
        steps = grading_result.get('steps', [])
        print(f"\n📝 Steps Extracted: {len(steps)}")
        for i, step in enumerate(steps[:5], 1):
            raw_text = step.get('raw_text', 'N/A')
            print(f"   {i}. {raw_text[:60]}...")
        if len(steps) > 5:
            print(f"   ... and {len(steps) - 5} more steps")
        
        # Show claims
        claims = grading_result.get('claims', [])
        print(f"\n🔍 Claims Generated: {len(claims)}")
        for i, claim in enumerate(claims[:5], 1):
            claim_id = claim.get('claim_id', '?')
            claim_type = claim.get('type', '?')
            args = claim.get('args', [])
            args_str = ', '.join(str(a) for a in args[:2])
            print(f"   {i}. [{claim_id}] {claim_type}({args_str})")
        if len(claims) > 5:
            print(f"   ... and {len(claims) - 5} more claims")
        
        # Show verification results
        verification_results = grading_result.get('verification_results', [])
        if verification_results:
            true_count = sum(1 for r in verification_results if r.get('verdict') == 'true')
            false_count = sum(1 for r in verification_results if r.get('verdict') == 'false')
            unknown_count = sum(1 for r in verification_results if r.get('verdict') == 'unknown')
            
            print(f"\n✅ Verification Summary:")
            print(f"   ✓ True:    {true_count}")
            print(f"   ✗ False:   {false_count}")
            print(f"   ? Unknown: {unknown_count}")
            
            if false_count > 0:
                print(f"\n❌ Failed Claims:")
                for result in verification_results:
                    if result.get('verdict') == 'false':
                        claim_id = result.get('claim_id', '?')
                        reason = result.get('reason_code', 'N/A')
                        print(f"   - {claim_id}: {reason}")
        
        # Show rubric scores
        rubric_scores = grading_result.get('rubric_scores', [])
        if rubric_scores:
            print(f"\n💯 Rubric Scores:")
            for rs in rubric_scores:
                item_id = rs.get('rubric_item_id', '?')
                earned = rs.get('earned', 0)
                max_pts = rs.get('max', 0)
                notes = rs.get('notes', '')[:50]
                print(f"   [{item_id}] {earned}/{max_pts} - {notes}")
        
        # Show FormalGeo detailed report if available
        if formalgeo_used and 'formalgeo_grading' in grading_result:
            print_section("FormalGeo Detailed Report")
            
            fg = grading_result['formalgeo_grading']
            
            print(f"📊 FormalGeo Score: {fg.get('total_points', 0)}/100")
            print(f"🎯 Goal Reached: {fg.get('goal_reached', False)}")
            print(f"💯 Confidence: {fg.get('confidence', 0):.2f}")
            
            # Step feedback
            step_feedback = fg.get('step_feedback', [])
            if step_feedback:
                print(f"\n📝 Step-by-Step Verification ({len(step_feedback)} steps):")
                for feedback in step_feedback[:8]:
                    step_id = feedback.get('step_id', '?')
                    is_valid = feedback.get('is_valid', False)
                    status = "✓" if is_valid else "✗"
                    
                    if is_valid:
                        theorem = feedback.get('theorem_applied', 'N/A')
                        print(f"   {status} Step {step_id}: Valid (theorem: {theorem})")
                    else:
                        error = feedback.get('error_details', 'Invalid')[:60]
                        print(f"   {status} Step {step_id}: {error}")
                
                if len(step_feedback) > 8:
                    print(f"   ... and {len(step_feedback) - 8} more steps")
            
            # Deductions
            deductions = fg.get('deductions', [])
            if deductions:
                print(f"\n❌ Point Deductions ({len(deductions)} total):")
                for d in deductions:
                    points = d.get('deducted_points', 0)
                    reason = d.get('deduction_reason', 'N/A')[:80]
                    step = d.get('deduction_step', '?')
                    print(f"\n   -{points} pts | {step}")
                    print(f"   {reason}")
            
            # Summary
            summary = fg.get('summary', 'N/A')
            print(f"\n📄 Summary:")
            print(f"   {summary}")
        
        # Save results
        output_file = output_dir / f"e2e_result_{image_path.stem}.json"
        output_file.write_text(json.dumps({
            "image": str(image_path),
            "score": score,
            "max_score": max_score,
            "formalgeo_used": formalgeo_used,
            "analysis": analysis,
            "grading": grading_result
        }, indent=2, ensure_ascii=False))
        
        print(f"\n💾 Full results saved to:")
        print(f"   {output_file}")
        
        print(f"\nSummary for {image_path.name}:")
        print(f"  • Score: {score}/{max_score} ({percentage:.1f}%)")
        print(f"  • FormalGeo: {'Yes' if formalgeo_used else 'No'}")
        print(f"  • Steps: {len(steps)}")
        print(f"  • Claims: {len(claims)}")
        
        if formalgeo_used:
            print(f"\n✅ FormalGeo theorem-proving grading was used!")
            print(f"   Your solution was verified with mathematical rigor.")
        else:
            print(f"\n⚠️  FormalGeo was not available - used LLM-based verification")
            print(f"   To enable FormalGeo: See QUICKSTART.md")
        
        print()

    print_header("TESTS COMPLETED")


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
