"""
LLM-Native Geometry Grader

A pure LLM-based grader (GPT-5.4 vision) with tool-calling for image re-inspection.
This grader uses a 4-phase pipeline:
  1. Problem Understanding - Analyze the problem image
  2. Student Work Extraction - Extract steps and constructions from both images
  3. Step-by-Step Verification - Verify each step with tool-calling for image queries
  4. Scoring & Feedback - Calculate final score with cascading error tracking
"""

import json
import base64
from typing import Dict, List, Any, Optional, Tuple, TYPE_CHECKING

from .llm_grader_models import (
    ProblemAnalysis,
    StudentStep,
    StudentConstruction,
    StudentWorkExtraction,
    StepVerification,
    ConstructionVerification,
    GradingResult,
    ToolCall,
)
from .image_verification_tools import (
    ImageVerificationToolHandler,
    get_tool_definitions,
)

if TYPE_CHECKING:
    from app import LLMService


class LLMNativeGeometryGrader:
    """
    Pure LLM-based geometry grader with tool-calling for image re-inspection.

    Key features:
    - 4-phase pipeline for structured grading
    - Tool calling allows model to re-inspect images during verification
    - Cascading error tracking: errors propagate but only root cause is penalized
    - Detailed feedback with evidence sources
    """

    def __init__(self, llm_service: "LLMService", model: str = "claude-opus-4-5"):
        """
        Initialize the grader.

        Args:
            llm_service: LLM service for making API calls
            model: Model to use for grading (should support vision and tool calling)
        """
        self.llm_service = llm_service
        self.model = model

    async def grade(
        self,
        problem_image: bytes,
        student_image: bytes,
        max_points: int = 100
    ) -> GradingResult:
        """
        Grade a student's geometry solution.

        Args:
            problem_image: Raw bytes of the problem image
            student_image: Raw bytes of the student's solution image
            max_points: Maximum possible points

        Returns:
            GradingResult with score, feedback, and detailed analysis
        """
        print(f"[LLMNativeGrader] Starting grading pipeline with max_points={max_points}")

        # Phase 1: Problem understanding
        print("[LLMNativeGrader] Phase 1: Problem Understanding")
        problem_analysis = await self._phase1_problem_understanding(problem_image)
        print(f"[LLMNativeGrader] Problem: {problem_analysis.goal}")

        # Phase 2: Student work extraction
        print("[LLMNativeGrader] Phase 2: Student Work Extraction")
        student_work = await self._phase2_extract_student_work(
            problem_image, student_image, problem_analysis
        )
        print(f"[LLMNativeGrader] Extracted {len(student_work.steps)} steps, {len(student_work.constructions)} constructions")

        # Phase 3: Step verification with tool calling
        print("[LLMNativeGrader] Phase 3: Step Verification")
        tool_handler = ImageVerificationToolHandler(
            self.llm_service, problem_image, student_image, self.model
        )
        verifications, construction_verifications = await self._phase3_verify_steps(
            problem_analysis, student_work, tool_handler
        )
        print(f"[LLMNativeGrader] Verified {len(verifications)} steps")

        # Phase 4: Scoring
        print("[LLMNativeGrader] Phase 4: Scoring")
        result = await self._phase4_score(
            problem_analysis, student_work, verifications,
            construction_verifications, max_points
        )

        print(f"[LLMNativeGrader] Final score: {result.total_score}/{result.max_score}")
        return result

    async def _phase1_problem_understanding(self, problem_image: bytes) -> ProblemAnalysis:
        """
        Phase 1: Analyze the problem image to understand what needs to be proven/solved.
        """
        prompt = """Analyze this geometry problem image carefully.

Extract the following information and respond with JSON:
{
    "problem_text": "Full text of the problem as written",
    "givens": ["List of given information"],
    "goal": "What needs to be proven or calculated",
    "required_method": "Specific method required if stated, or null",
    "diagram_elements": {
        "points": ["List of labeled points"],
        "lines": ["List of lines/segments"],
        "circles": ["List of circles with centers"],
        "angles": ["List of marked angles"],
        "other": ["Other geometric elements"]
    }
}

Be thorough in identifying all given information from both text and diagram."""

        messages = [
            {
                "role": "system",
                "content": "You are an expert geometry problem analyzer. Extract all relevant information precisely."
            },
            {"role": "user", "content": prompt}
        ]

        result = await self.llm_service.chat(
            messages=messages,
            model=self.model,
            temperature=0.0,
            image_data=problem_image
        )

        # Debug: print raw result
        print(f"[DEBUG Phase1] Raw LLM response type: {type(result)}")
        print(f"[DEBUG Phase1] Raw LLM response keys: {result.keys() if isinstance(result, dict) else 'not a dict'}")
        print(f"[DEBUG Phase1] Raw LLM response: {json.dumps(result, indent=2)[:500]}...")

        # Parse result
        if "raw" in result:
            raw_content = result["raw"]
            # Strip markdown code fences if present
            if raw_content.startswith("```"):
                # Remove opening fence (```json or ```)
                raw_content = raw_content.split('\n', 1)[1] if '\n' in raw_content else raw_content
                # Remove closing fence
                if raw_content.endswith("```"):
                    raw_content = raw_content.rsplit("```", 1)[0]
                raw_content = raw_content.strip()

            try:
                result = json.loads(raw_content)
            except json.JSONDecodeError as e:
                print(f"[DEBUG Phase1] JSON parse error: {e}")
                print(f"[DEBUG Phase1] Attempted to parse: {raw_content[:200]}...")
                # Fallback if parsing fails
                result = {
                    "problem_text": result.get("raw", ""),
                    "givens": [],
                    "goal": "Unknown",
                    "diagram_elements": {}
                }
        else:
            # Result is already parsed JSON
            print(f"[DEBUG Phase1] Result already parsed, using as-is")

        print(f"[DEBUG Phase1] Final parsed result: goal={result.get('goal', 'N/A')}, givens={len(result.get('givens', []))}")
        return ProblemAnalysis.from_dict(result)

    async def _phase2_extract_student_work(
        self,
        problem_image: bytes,
        student_image: bytes,
        problem_analysis: ProblemAnalysis
    ) -> StudentWorkExtraction:
        """
        Phase 2: Extract student's work from their solution image.
        Uses both images for context.
        """
        prompt = f"""Analyze the student's geometry solution.

PROBLEM CONTEXT:
Goal: {problem_analysis.goal}
Givens: {', '.join(problem_analysis.givens)}

Extract the student's work and respond with JSON:
{{
    "constructions": [
        {{
            "construction_id": "C1",
            "description": "What was constructed (e.g., 'Drew perpendicular from C to AB')",
            "justification": "Student's stated justification if any"
        }}
    ],
    "steps": [
        {{
            "step_id": "S1",
            "raw_text": "Exact text from student's work",
            "normalized_claim": "Mathematical claim in clear form (e.g., 'angle ABC = 90 degrees')",
            "depends_on": ["S0"] // List of step IDs this step depends on (use 'GIVEN' for given facts)
        }}
    ],
    "final_answer": "Student's final answer or conclusion"
}}

Guidelines:
- Number steps sequentially as S1, S2, etc.
- For depends_on, use "GIVEN" if the step follows from given information
- Capture ALL steps, even if they seem redundant
- Be precise about what the student actually wrote"""

        result = await self.llm_service.chat_with_two_images(
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at reading and interpreting student geometry solutions. Extract work precisely."
                },
                {"role": "user", "content": prompt}
            ],
            image1_data=problem_image,
            image2_data=student_image,
            model=self.model,
            temperature=0.0
        )

        # Debug: print raw result
        print(f"[DEBUG Phase2] Raw LLM response type: {type(result)}")
        print(f"[DEBUG Phase2] Raw LLM response keys: {result.keys() if isinstance(result, dict) else 'not a dict'}")
        print(f"[DEBUG Phase2] Raw LLM response: {json.dumps(result, indent=2)[:500]}...")

        # Parse result
        if "raw" in result:
            raw_content = result["raw"]
            # Strip markdown code fences if present
            if raw_content.startswith("```"):
                # Remove opening fence (```json or ```)
                raw_content = raw_content.split('\n', 1)[1] if '\n' in raw_content else raw_content
                # Remove closing fence
                if raw_content.endswith("```"):
                    raw_content = raw_content.rsplit("```", 1)[0]
                raw_content = raw_content.strip()

            try:
                result = json.loads(raw_content)
            except json.JSONDecodeError as e:
                print(f"[DEBUG Phase2] JSON parse error: {e}")
                print(f"[DEBUG Phase2] Attempted to parse: {raw_content[:200]}...")
                result = {"constructions": [], "steps": [], "final_answer": None}
        else:
            # Result is already parsed JSON
            print(f"[DEBUG Phase2] Result already parsed, using as-is")

        print(f"[DEBUG Phase2] Final parsed result: steps={len(result.get('steps', []))}, constructions={len(result.get('constructions', []))}")
        return StudentWorkExtraction.from_dict(result)

    async def _phase3_verify_steps(
        self,
        problem_analysis: ProblemAnalysis,
        student_work: StudentWorkExtraction,
        tool_handler: ImageVerificationToolHandler
    ) -> Tuple[List[StepVerification], List[ConstructionVerification]]:
        """
        Phase 3: Verify each step with tool calling for image queries.
        Tracks cascading errors.
        """
        verifications: List[StepVerification] = []
        construction_verifications: List[ConstructionVerification] = []
        invalid_steps: Dict[str, StepVerification] = {}  # Track first invalid step

        # First verify constructions
        for construction in student_work.constructions:
            cv = await self._verify_construction(construction, tool_handler, problem_analysis)
            construction_verifications.append(cv)

        # Then verify each step
        for step in student_work.steps:
            verification = await self._verify_single_step(
                step, problem_analysis, student_work, verifications,
                invalid_steps, tool_handler
            )
            verifications.append(verification)

            if verification.verdict == "invalid":
                invalid_steps[step.step_id] = verification

        return verifications, construction_verifications

    async def _verify_construction(
        self,
        construction: StudentConstruction,
        tool_handler: ImageVerificationToolHandler,
        problem_analysis: ProblemAnalysis
    ) -> ConstructionVerification:
        """Verify a single construction."""
        tool_result = await tool_handler.handle_tool_call(
            "check_construction_validity",
            {
                "construction": construction.description,
                "justification": construction.justification or ""
            }
        )

        is_valid = tool_result.get("is_valid", True)  # Default to valid if unclear
        reason = tool_result.get("reason", "Construction appears valid")

        tool_call = ToolCall(
            tool_name="check_construction_validity",
            arguments={"construction": construction.description},
            result=tool_result
        )

        return ConstructionVerification(
            construction_id=construction.construction_id,
            is_valid=is_valid,
            justification=reason,
            tool_calls_made=[tool_call]
        )

    async def _verify_single_step(
        self,
        step: StudentStep,
        problem_analysis: ProblemAnalysis,
        student_work: StudentWorkExtraction,
        previous_verifications: List[StepVerification],
        invalid_steps: Dict[str, StepVerification],
        tool_handler: ImageVerificationToolHandler
    ) -> StepVerification:
        """
        Verify a single step, checking for cascading errors first.
        """
        # Check for cascading errors first
        for dep_id in step.depends_on:
            if dep_id in invalid_steps:
                root = invalid_steps[dep_id]
                root_cause = root.root_cause_step or root.step_id
                return StepVerification(
                    step_id=step.step_id,
                    verdict="cascading_error",
                    justification=f"This step depends on {dep_id} which contains an error",
                    evidence_source="reasoning",
                    error_type="cascading_error",
                    root_cause_step=root_cause
                )

        # Build context for verification
        prev_steps_context = "\n".join([
            f"- {s.step_id}: {student_work.steps[i].normalized_claim} [{s.verdict}]"
            for i, s in enumerate(previous_verifications)
        ])

        prompt = f"""You are grading a geometry problem step-by-step.

PROBLEM GOAL: {problem_analysis.goal}
GIVENS: {', '.join(problem_analysis.givens)}

PREVIOUS STEPS:
{prev_steps_context if prev_steps_context else "None yet"}

CURRENT STEP TO VERIFY:
ID: {step.step_id}
Student's claim: {step.normalized_claim}
Depends on: {', '.join(step.depends_on)}

Your task: Determine if this step is mathematically correct.

CRITICAL GRADING PHILOSOPHY - THREE-TIER EVALUATION:

STEP 1: IDENTIFY THE MAIN CONCLUSION
- What is the PRIMARY RESULT/CLAIM of this step? (e.g., "AC = 6", "perimeter = 10 + 3π")
- This is what later steps will depend on

STEP 2: VERIFY THE CONCLUSION INDEPENDENTLY
- Is the main conclusion CORRECT? Use image verification tools if it's a geometric claim
- Focus on the FINAL RESULT, not the reasoning path used to get there

STEP 3: EVALUATE REASONING QUALITY (only after verifying conclusion)
- If conclusion is CORRECT:
  * Perfect reasoning → verdict="valid", points_deducted=0
  * Wrong terminology/typos/mistakes in the middle of reasoning → verdict="imperfect", points_deducted=2
  * Informal language/omitted steps → verdict="valid", points_deducted=0
  * NO cascading error - later steps can use this conclusion

- If conclusion is INCORRECT:
  * The result itself is wrong → verdict="invalid", major deduction
  * This WILL cascade to later steps that depend on it

KEY PRINCIPLE - WHAT MATTERS FOR THE REASONING CHAIN:
- Later steps depend on the CORRECTNESS OF CONCLUSIONS (values, results)
- Later steps do NOT depend on the quality of reasoning that produced those conclusions
- Therefore: Correct conclusion + flawed reasoning = VALID (with minor deduction, no cascade)
- Only cascade when the conclusion VALUE itself is wrong

1. MAJOR CREDIT - Correct Conclusion:
   - Is the MAIN CONCLUSION of the step correct?
   - Verify independently with tools if geometric
   - This determines whether later steps can validly build on it
   - verdict="valid" or "imperfect" (both allow later steps to use the conclusion)

2. IMPERFECT (2 points deduction) - Correct Conclusion + Flawed Reasoning:
   - Conclusion is CORRECT, but reasoning has issues:
     * Wrong terminology in the middle (e.g., "diameter" when meaning "radius")
     * Mistakes or typos in the reasoning process
     * Faulty intermediate logic that happens to reach correct answer
   - verdict="imperfect", points_deducted=2
   - NO cascading errors (conclusion is correct, so later steps can use it)

3. NO CREDIT DEDUCTION - Correct Conclusion + Acceptable Presentation:
   - Conclusion is correct with acceptable presentation:
     * Informal language
     * Omitted intermediate steps
     * Abbreviated notation
   - verdict="valid", points_deducted=0

KEY PRINCIPLE:
- Verdict "valid" = The mathematical CLAIM is correct (result + logic are sound)
- Verdict "invalid" = The mathematical CLAIM is false (wrong result OR flawed logic)
- Later steps depend on VALUES, not on how those values were justified

Instructions - FOLLOW THIS PROCESS:
1. IDENTIFY: What is the main conclusion/result of this step?
2. VERIFY: Is that conclusion correct? (Use image verification tools for geometric claims)
3. EVALUATE REASONING: Only after confirming the conclusion, assess the reasoning quality
4. DECIDE:
   - If conclusion CORRECT + reasoning perfect → verdict="valid", points_deducted=0
   - If conclusion CORRECT + reasoning has mistakes/typos → verdict="imperfect", points_deducted=2
   - If conclusion INCORRECT → verdict="invalid", points_deducted=10+

IMPORTANT: For geometric/numerical claims, ALWAYS use verification tools to independently check the conclusion before deciding the verdict.

Respond in JSON format:
{{
    "main_conclusion": "The primary result/claim of this step",
    "conclusion_correct": true or false,
    "verdict": "valid" or "imperfect" or "invalid",
    "justification": "Explain if the CONCLUSION is correct and assess reasoning quality",
    "evidence_source": "given" or "reasoning" or "problem_image" or "student_image",
    "error_type": null or "computational_error" or "logical_error" or "incorrect_claim",
    "error_details": null or "description of error",
    "points_deducted": 0 or 2 or 10,
    "needs_image_verification": true or false,
    "verification_query": null or "what to verify"
}}

What Makes a Step INVALID (verdict="invalid"):
- The MAIN CONCLUSION is demonstrably WRONG (e.g., claims "perimeter = 15" when it's actually 10)
- The CONCLUSION contradicts verified facts from the diagram
- The CONCLUSION is mathematically impossible or logically inconsistent

What Makes a Step IMPERFECT (verdict="imperfect"):
- The MAIN CONCLUSION is CORRECT (verified independently)
- BUT the reasoning process contains mistakes, wrong terminology, or typos
- Later steps CAN validly use this conclusion (no cascading)
- Small deduction for reasoning quality issues

What Makes a Step VALID (verdict="valid"):
- The MAIN CONCLUSION is CORRECT (independently verified if needed)
- The reasoning is sound OR uses acceptable informal presentation
- No issues with terminology or logical flow

CRITICAL EXAMPLES:

Example 1: Correct conclusion + wrong terminology (IMPERFECT)
- Student says: "AC = 6 because RB is a diameter"
- Main conclusion: AC = 6
- Verify independently: Check if AC truly equals 6 in the diagram
- If AC = 6 is TRUE: verdict="imperfect", points_deducted=2 (wrong terminology "diameter"), NO cascading
- If AC = 6 is FALSE: verdict="invalid", major deduction, YES cascading

Example 2: Correct conclusion + informal language (VALID)
- Student says: "the curved part is 3π"
- Main conclusion: arc length = 3π
- If arc length truly = 3π: verdict="valid", points_deducted=0 (informal language is acceptable)

Example 3: Wrong conclusion (INVALID)
- Student says: "perimeter = 15"
- Main conclusion: perimeter = 15
- Verify: actual perimeter = 10 + 3π
- verdict="invalid", points_deducted=10+, YES cascading to dependent steps

Remember: VERIFY the conclusion independently. A correct conclusion with flawed reasoning is IMPERFECT, not invalid."""

        # First pass: determine if we need image verification
        messages = [
            {
                "role": "system",
                "content": "You are a geometry grader. CRITICAL PROCESS: (1) Identify the MAIN CONCLUSION of each step, (2) INDEPENDENTLY VERIFY if that conclusion is correct using image tools when needed, (3) Choose verdict: 'valid' (correct conclusion + good reasoning), 'imperfect' (correct conclusion + flawed reasoning), or 'invalid' (wrong conclusion). Only 'invalid' causes cascading errors."
            },
            {"role": "user", "content": prompt}
        ]

        result = await self.llm_service.chat(
            messages=messages,
            model=self.model,
            temperature=0.0
        )

        if "raw" in result:
            raw_content = result["raw"]
            # Strip markdown code fences if present
            if raw_content.startswith("```"):
                raw_content = raw_content.split('\n', 1)[1] if '\n' in raw_content else raw_content
                if raw_content.endswith("```"):
                    raw_content = raw_content.rsplit("```", 1)[0]
                raw_content = raw_content.strip()

            try:
                result = json.loads(raw_content)
            except json.JSONDecodeError:
                result = {"verdict": "valid", "justification": "Could not parse", "evidence_source": "reasoning"}

        tool_calls: List[ToolCall] = []

        # If image verification is needed, make tool call
        if result.get("needs_image_verification") and result.get("verification_query"):
            query = result["verification_query"]
            evidence_source = result.get("evidence_source", "problem_image")

            if evidence_source == "student_image":
                tool_result = await tool_handler.handle_tool_call(
                    "verify_in_student_image",
                    {"query": query, "context": step.normalized_claim}
                )
                tool_calls.append(ToolCall(
                    tool_name="verify_in_student_image",
                    arguments={"query": query},
                    result=tool_result
                ))
            else:
                tool_result = await tool_handler.handle_tool_call(
                    "verify_in_problem_image",
                    {"query": query, "expected_answer": step.normalized_claim}
                )
                tool_calls.append(ToolCall(
                    tool_name="verify_in_problem_image",
                    arguments={"query": query},
                    result=tool_result
                ))

            # Re-evaluate based on tool result
            if tool_result.get("answer") == "no":
                result["verdict"] = "invalid"
                result["error_type"] = "incorrect_claim"
                result["error_details"] = tool_result.get("evidence", "Image verification failed")

        return StepVerification(
            step_id=step.step_id,
            verdict=result.get("verdict", "valid"),
            justification=result.get("justification", ""),
            evidence_source=result.get("evidence_source", "reasoning"),
            error_type=result.get("error_type"),
            error_details=result.get("error_details"),
            tool_calls_made=tool_calls,
            points_deducted=result.get("points_deducted", 0)
        )

    async def _phase4_score(
        self,
        problem_analysis: ProblemAnalysis,
        student_work: StudentWorkExtraction,
        verifications: List[StepVerification],
        construction_verifications: List[ConstructionVerification],
        max_points: int
    ) -> GradingResult:
        """
        Phase 4: Calculate final score with cascading error tracking.
        """
        # Count errors by type (only count root causes, not cascading)
        root_errors = [v for v in verifications if v.verdict == "invalid"]
        cascading_errors = [v for v in verifications if v.verdict == "cascading_error"]
        valid_steps = [v for v in verifications if v.verdict == "valid"]
        imperfect_steps = [v for v in verifications if v.verdict == "imperfect"]

        # Build cascading chains
        cascading_chains: List[List[str]] = []
        for root in root_errors:
            chain = [root.step_id]
            for cascade in cascading_errors:
                if cascade.root_cause_step == root.step_id:
                    chain.append(cascade.step_id)
            if len(chain) > 1:
                cascading_chains.append(chain)

        # Calculate deductions
        # Base deduction per root error: varies by error type
        deduction_map = {
            "computational_error": 10,
            "logical_error": 20,
            "missing_justification": 5,
            "incorrect_claim": 15,
        }

        total_deduction = 0

        # Deductions from invalid steps (root errors)
        for v in root_errors:
            deduction = deduction_map.get(v.error_type, 10)
            v.points_deducted = deduction
            total_deduction += deduction

        # Deductions from imperfect steps (correct conclusion, flawed reasoning)
        for v in imperfect_steps:
            if v.points_deducted > 0:
                total_deduction += v.points_deducted

        # Deductions from valid steps with minor issues
        for v in valid_steps:
            if v.points_deducted > 0:
                total_deduction += v.points_deducted

        # Invalid constructions also cost points
        for cv in construction_verifications:
            if not cv.is_valid:
                total_deduction += 10

        # Check if goal was achieved
        goal_achieved = self._check_goal_achieved(
            student_work.final_answer, problem_analysis.goal, verifications
        )

        # If goal not achieved and no other errors, deduct for incomplete solution
        if not goal_achieved and total_deduction == 0:
            total_deduction = max(20, max_points // 5)  # At least 20% for not reaching goal

        # Calculate final score
        total_score = max(0, max_points - total_deduction)

        # Generate summary
        summary = self._generate_summary(
            valid_steps, imperfect_steps, root_errors, cascading_errors, goal_achieved, total_score, max_points
        )

        return GradingResult(
            total_score=total_score,
            max_score=max_points,
            goal_achieved=goal_achieved,
            steps_feedback=verifications,
            construction_feedback=construction_verifications,
            summary=summary,
            cascading_chains=cascading_chains,
            problem_analysis=problem_analysis,
            student_work=student_work
        )

    def _check_goal_achieved(
        self,
        final_answer: Optional[str],
        goal: str,
        verifications: List[StepVerification]
    ) -> bool:
        """Check if the student achieved the problem's goal."""
        # If there are any root errors in the logical chain leading to the conclusion,
        # the goal is not properly achieved
        has_root_error = any(v.verdict == "invalid" for v in verifications)

        # If there's no final answer, goal is not achieved
        if not final_answer:
            return False

        # If there are root errors, goal is compromised
        if has_root_error:
            return False

        # Otherwise, assume goal is achieved if we have a final answer and no errors
        return True

    def _generate_summary(
        self,
        valid_steps: List[StepVerification],
        imperfect_steps: List[StepVerification],
        root_errors: List[StepVerification],
        cascading_errors: List[StepVerification],
        goal_achieved: bool,
        score: int,
        max_score: int
    ) -> str:
        """Generate a human-readable summary of the grading."""
        parts = []

        # Score summary
        if score == max_score:
            parts.append(f"Excellent work! Full marks ({score}/{max_score}).")
        elif score >= max_score * 0.8:
            parts.append(f"Good solution with minor issues ({score}/{max_score}).")
        elif score >= max_score * 0.6:
            parts.append(f"Partial credit ({score}/{max_score}). Some significant errors found.")
        else:
            parts.append(f"Solution needs improvement ({score}/{max_score}).")

        # Step summary
        total_steps = len(valid_steps) + len(imperfect_steps) + len(root_errors) + len(cascading_errors)
        correct_steps = len(valid_steps) + len(imperfect_steps)  # Both have correct conclusions
        parts.append(f"{correct_steps} of {total_steps} steps had correct conclusions.")

        if imperfect_steps:
            parts.append(f"{len(imperfect_steps)} steps were correct but had minor reasoning issues.")

        # Error summary
        if root_errors:
            error_types = [e.error_type for e in root_errors if e.error_type]
            if error_types:
                parts.append(f"Root errors: {', '.join(set(error_types))}.")

        if cascading_errors:
            parts.append(f"{len(cascading_errors)} steps were affected by previous errors (cascading).")

        # Goal summary
        if goal_achieved:
            parts.append("The problem goal was achieved.")
        else:
            parts.append("The problem goal was not fully achieved.")

        return " ".join(parts)
