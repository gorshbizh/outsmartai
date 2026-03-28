"""
Simple LLM Vision Grader - Single-shot holistic evaluation

Instead of breaking down the problem into multiple phases (problem understanding,
step extraction, step verification, scoring), this grader sends the image(s)
directly to the LLM and asks: "Is this solution correct?"

Grading philosophy:
- Focus on whether the final answer is correct and reasoning is valid
- Minor issues (typos, informal language, wrong terminology): -3 points each
- Major issues (wrong calculations, invalid logic, root cause errors): -35 points each
- Cascade issues (errors caused by prior major issues): -10 points each
- Score starts at 100 and deducts points until reaching 0

Key features:
- Always uses two-image mode (problem image + solution image)
- Extracts givens from problem image with confidence scores
- Extracts steps from student solution with confidence scores
"""

import json
import base64
from typing import Dict, List, Any, Optional, TYPE_CHECKING
from dataclasses import dataclass, asdict, field

if TYPE_CHECKING:
    from app import LLMService


@dataclass
class GivenFact:
    """A fact extracted from the problem image."""
    fact: str
    confidence: float  # 0.0 to 1.0
    source: str  # "text" or "diagram" or "both"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StudentStep:
    """A step extracted from the student's solution."""
    step_number: int
    content: str
    confidence: float  # 0.0 to 1.0
    is_valid: Optional[bool] = None
    issue: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SimpleGradingResult:
    """Result from simple LLM grader."""
    total_score: int
    max_score: int
    is_correct: bool
    is_reasoning_valid: bool
    problem_goal: str
    student_answer: str
    correct_answer: str
    givens: List[GivenFact]
    steps: List[StudentStep]
    minor_issues: List[Dict[str, Any]]
    major_issues: List[Dict[str, Any]]
    cascade_issues: List[Dict[str, Any]]
    summary: str
    raw_response: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        # Convert nested dataclasses
        result['givens'] = [g if isinstance(g, dict) else g.to_dict() for g in self.givens]
        result['steps'] = [s if isinstance(s, dict) else s.to_dict() for s in self.steps]
        return result


# Tool definition for optional image inspection
IMAGE_INSPECTION_TOOL = {
    "type": "function",
    "function": {
        "name": "inspect_image",
        "description": "Re-examine the image to verify a specific detail you're uncertain about. Use this when you need to double-check a value, label, or geometric relationship.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Specific question about the image (e.g., 'What is the student's final answer?', 'Does point B lie on the arc?', 'What value did the student write for AC?')"
                }
            },
            "required": ["query"]
        }
    }
}


class SimpleLLMGrader:
    """
    Simple single-shot grader using two images: problem and solution.

    Always extracts:
    - Givens from the problem image (with confidence scores)
    - Steps from the student solution (with confidence scores)
    """

    def __init__(self, llm_service: "LLMService", model: str = "claude-opus-4-5"):
        self.llm_service = llm_service
        self.model = model

    async def grade(
        self,
        solution_image: bytes,
        problem_image: Optional[bytes] = None,
        max_points: int = 100,
        use_tool: bool = False
    ) -> SimpleGradingResult:
        """
        Grade a student's geometry solution.

        Args:
            solution_image: Image containing the student's solution
            problem_image: Problem image (required for best results)
            max_points: Maximum possible points
            use_tool: Whether to provide image inspection tool

        Returns:
            SimpleGradingResult with score and feedback
        """
        print(f"[SimpleLLMGrader] Starting grading with max_points={max_points}, use_tool={use_tool}")

        # Always require problem_image for two-image mode
        if problem_image is None:
            print("[SimpleLLMGrader] WARNING: No problem image provided, using solution image as both")
            problem_image = solution_image

        prompt = self._build_prompt()

        if use_tool:
            result = await self._grade_with_tool(prompt, solution_image, problem_image)
        else:
            result = await self._grade_direct(prompt, solution_image, problem_image)

        return self._parse_result(result, max_points)

    def _build_prompt(self) -> str:
        """Build the grading prompt."""
        return """You are grading a math/geometry solution. You are provided with TWO images:
- IMAGE 1 (First image): The PROBLEM - contains the problem statement and diagram
- IMAGE 2 (Second image): The STUDENT'S SOLUTION - contains the student's handwritten work

TASK: Extract information from both images and evaluate whether the student's solution is correct.

CRITICAL PRINCIPLE - VERIFY BEFORE ASSUMING:
Diagrams are often NOT drawn to scale and can be visually misleading. You must distinguish between:
- What is EXPLICITLY STATED in the problem (trustworthy)
- What is LOGICALLY DERIVABLE from given information (trustworthy)
- What merely APPEARS to be true visually (NOT trustworthy - must verify)

STEP 1: EXTRACT GIVENS FROM THE PROBLEM IMAGE (Image 1)
Carefully read the problem image and extract ALL given information:
- Read the problem text completely
- Identify all labeled points, lines, angles, and measurements
- Note all stated relationships (parallel, perpendicular, equal, etc.)
- For each given fact, provide a confidence score (0.0-1.0) based on how clearly you can read it
- Indicate whether each fact comes from "text", "diagram", or "both"

STEP 1.5: DERIVE CONSEQUENCES FROM GIVENS
Before evaluating the student's solution, derive ALL logical consequences from the extracted givens:
- If a point P is on a circle/arc with center O and radius r, then OP = r
- If WXYZ is a rectangle, the diagonals WY and XZ are equal
- If an arc is named "Arc XYZ", then X, Y, and Z are all on that arc
- Apply these derivations to get all implicit facts (e.g., if B is on an arc with center R and radius 6, then RB = 6)

STEP 2: EXTRACT STEPS FROM THE STUDENT'S SOLUTION (Image 2)
Carefully read the student's handwritten solution and extract ALL steps:
- Number each step sequentially
- Transcribe exactly what the student wrote (including any errors)
- For each step, provide a confidence score (0.0-1.0) based on how clearly you can read the handwriting
- Include the student's final answer as the last step

STEP 3: VERIFY THE SOLUTION
Using the extracted givens and steps:
- Compute the correct answer yourself using ONLY the given facts and valid derivations
- Compare with the student's answer
- Check if each step follows logically from the givens and previous steps

STEP 4: IDENTIFY ISSUES

CRITICAL GRADING PRINCIPLES:
1. **Benefit of the Doubt**: When evaluating reasoning:
   - Be VERY cautious before marking major issues
   - Alternative reasoning paths can be valid, even if different from your approach
   - Abbreviated steps that skip obvious details should not be penalized
   - If you're uncertain whether a step is valid, classify as minor issue at most

2. **Distinguish Valid Alternatives from Errors**:
   - VALID ALTERNATIVE: Different reasoning path that is mathematically sound (no penalty even if unconventional)
   - ACTUAL ERROR: Clear mathematical mistakes, invalid logic, or contradictions with given facts (major issue)
   - When in doubt: If you cannot identify a clear mathematical error or contradiction, assume it's a valid alternative

3. **Verify Your Own Understanding**: Before marking a major issue, double-check:
   - Did you correctly understand all the givens and derived facts?
   - Could the student be using a valid geometric relationship you haven't considered?
   - Is your "correct answer" actually correct, or did you make an error?
   - Are you penalizing a difference in approach rather than an actual error?

Classify each issue into one of three categories:

MAJOR ISSUES (-35 points each):
ONLY mark as major if you are CERTAIN the step contains a fundamental error:
- Wrong calculations or arithmetic errors that are clear root causes
- Incorrect geometric claims that directly contradict given information AND lead to wrong conclusions
- Using completely invalid formulas or relationships
- Clear logical fallacies or contradictions
**IMPORTANT**: Be extremely skeptical before marking major issues. Re-verify your assessment and ensure you're not penalizing an alternative valid approach.

CASCADE ISSUES (-10 points each):
- Errors caused by a prior major issue
- Steps that follow logically from a previous error but would be correct if the prior step were correct
- The local reasoning/calculation in the step itself is correct, but the input is wrong due to an earlier major error

MINOR ISSUES (-3 points each):
- Typos or writing errors that don't affect the math
- Informal language or abbreviations
- Wrong terminology that doesn't affect the calculation
- Skipped intermediate steps that are obvious
- Notation inconsistencies
- Unconventional but valid reasoning that seems unusual
- Steps that are hard to read or unclear but appear to reach correct intermediate results

Respond with JSON:
{
    "givens": [
        {
            "fact": "exact statement of the given fact",
            "confidence": 0.95,
            "source": "text" or "diagram" or "both"
        }
    ],
    "derived_facts": [
        "List facts derived from givens (e.g., 'RB = 6 because B is on arc with center R, radius 6')",
        "Include rectangle diagonal equalities, distances from center to points on circles, etc."
    ],
    "steps": [
        {
            "step_number": 1,
            "content": "exact transcription of student's step",
            "confidence": 0.9,
            "is_valid": true or false,
            "issue": null or "description of issue with this step"
        }
    ],
    "problem_goal": "Brief description of what the problem asks",
    "correct_answer": "What YOU calculate as the correct answer (using givens AND derived_facts)",
    "student_answer": "The student's final answer (exactly as written)",
    "is_correct": true or false,
    "is_reasoning_valid": true or false,
    "minor_issues": [
        {"description": "description of issue", "type": "minor", "step_number": 1}
    ],
    "major_issues": [
        {"description": "description of issue", "type": "major", "step_number": 1}
    ],
    "cascade_issues": [
        {"description": "description of issue", "type": "cascade", "step_number": 1, "caused_by_step": 1}
    ],
    "summary": "Brief overall assessment (1-2 sentences)"
}

IMPORTANT:
- Extract ALL givens from Image 1, even if some seem obvious
- Extract ALL steps from Image 2, even if handwriting is difficult
- Provide honest confidence scores - lower scores for unclear text/handwriting
- Classify issues correctly: major (root cause), cascade (caused by prior error), or minor (doesn't affect logic)
- For cascade issues, specify which step caused them
- If the solution is completely correct with no issues, use empty arrays for minor_issues, major_issues, and cascade_issues

AVOID FALSE NEGATIVES:
- Be extremely careful before marking major issues - ensure it's a true error, not just an alternative approach
- Alternative valid approaches should NOT be penalized - mathematics allows multiple solution paths
- If uncertain whether reasoning is "wrong" or "alternative", default to assuming it's alternative (no penalty or minor at most)
- Focus on identifying clear mathematical errors, logical contradictions, or invalid claims - not stylistic differences"""

    async def _grade_direct(
        self,
        prompt: str,
        solution_image: bytes,
        problem_image: bytes
    ) -> Dict[str, Any]:
        """Grade using two-image mode (always)."""

        messages = [
            {
                "role": "system",
                "content": "You are a fair and accurate math grader. You will receive two images: Image 1 is the PROBLEM, Image 2 is the STUDENT'S SOLUTION. Extract givens from Image 1, extract steps from Image 2, then evaluate the solution. Always provide confidence scores for your extractions. IMPORTANT: Be very cautious before marking major issues - distinguish between actual errors and alternative valid approaches."
            },
            {"role": "user", "content": prompt}
        ]

        # Always use two-image mode
        print("[SimpleLLMGrader] Using two-image mode (problem + solution)")
        result = await self.llm_service.chat_with_two_images(
            messages=messages,
            image1_data=problem_image,
            image2_data=solution_image,
            model=self.model,
            temperature=0.0
        )

        return result

    async def _grade_with_tool(
        self,
        prompt: str,
        solution_image: bytes,
        problem_image: bytes
    ) -> Dict[str, Any]:
        """Grade with optional image inspection tool available."""

        tool_prompt = prompt + """

If you need to verify a specific detail that you're uncertain about, you can use the inspect_image tool to ask a focused question about either image."""

        messages = [
            {
                "role": "system",
                "content": "You are a fair and accurate math grader. You will receive two images: Image 1 is the PROBLEM, Image 2 is the STUDENT'S SOLUTION. You can use the inspect_image tool if you need to verify specific details. IMPORTANT: Be very cautious before marking major issues - distinguish between actual errors and alternative valid approaches."
            },
            {"role": "user", "content": tool_prompt}
        ]

        # Always use two-image mode
        print("[SimpleLLMGrader] Using two-image mode with tools (problem + solution)")
        result = await self.llm_service.chat_with_two_images(
            messages=messages,
            image1_data=problem_image,
            image2_data=solution_image,
            model=self.model,
            temperature=0.0
        )

        # Handle tool calls if any
        if result.get("tool_calls"):
            print(f"[SimpleLLMGrader] LLM requested {len(result['tool_calls'])} tool call(s)")

            for tool_call in result["tool_calls"]:
                if tool_call.get("function", {}).get("name") == "inspect_image":
                    query = json.loads(tool_call["function"]["arguments"]).get("query", "")
                    print(f"[SimpleLLMGrader] Tool query: {query}")

                    # Make focused inspection call (use solution image by default)
                    inspection_result = await self._inspect_image(solution_image, query)
                    print(f"[SimpleLLMGrader] Inspection result: {inspection_result}")

                    # Continue conversation with tool result
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [tool_call]
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.get("id", ""),
                        "content": json.dumps(inspection_result)
                    })

            # Get final response after tool use
            result = await self.llm_service.chat_with_two_images(
                messages=messages,
                image1_data=problem_image,
                image2_data=solution_image,
                model=self.model,
                temperature=0.0
            )

        return result

    async def _inspect_image(self, image: bytes, query: str) -> Dict[str, Any]:
        """Focused image inspection for a specific query."""

        prompt = f"""Look at this image and answer this specific question:

Question: {query}

Respond with JSON:
{{
    "answer": "your direct answer",
    "confidence": "high" or "medium" or "low",
    "evidence": "what you see in the image that supports this answer"
}}"""

        messages = [
            {"role": "system", "content": "You are a precise image analyzer. Answer the question directly based on what you see."},
            {"role": "user", "content": prompt}
        ]

        result = await self.llm_service.chat(
            messages=messages,
            model=self.model,
            temperature=0.0,
            image_data=image
        )

        # Parse result
        if "raw" in result:
            raw = result["raw"]
            if raw.startswith("```"):
                raw = raw.split('\n', 1)[1] if '\n' in raw else raw
                if raw.endswith("```"):
                    raw = raw.rsplit("```", 1)[0]
                raw = raw.strip()
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"answer": raw, "confidence": "low", "evidence": "Could not parse structured response"}

        return result

    def _parse_result(self, result: Dict[str, Any], max_points: int) -> SimpleGradingResult:
        """Parse LLM response into SimpleGradingResult."""

        # Handle raw response
        if "raw" in result:
            raw = result["raw"]
            if raw.startswith("```"):
                raw = raw.split('\n', 1)[1] if '\n' in raw else raw
                if raw.endswith("```"):
                    raw = raw.rsplit("```", 1)[0]
                raw = raw.strip()
            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                print(f"[SimpleLLMGrader] Failed to parse response: {raw[:200]}...")
                return SimpleGradingResult(
                    total_score=0,
                    max_score=max_points,
                    is_correct=False,
                    is_reasoning_valid=False,
                    problem_goal="Could not parse",
                    student_answer="Could not parse",
                    correct_answer="Could not parse",
                    givens=[],
                    steps=[],
                    minor_issues=[],
                    major_issues=[{"description": "Failed to parse LLM response", "type": "major"}],
                    cascade_issues=[],
                    summary="Grading failed due to response parsing error",
                    raw_response={"raw": raw}
                )

        # Extract givens
        givens_raw = result.get("givens", [])
        givens = []
        for g in givens_raw:
            if isinstance(g, dict):
                givens.append(GivenFact(
                    fact=g.get("fact", ""),
                    confidence=g.get("confidence", 0.5),
                    source=g.get("source", "unknown")
                ))

        # Extract steps
        steps_raw = result.get("steps", [])
        steps = []
        for s in steps_raw:
            if isinstance(s, dict):
                steps.append(StudentStep(
                    step_number=s.get("step_number", 0),
                    content=s.get("content", ""),
                    confidence=s.get("confidence", 0.5),
                    is_valid=s.get("is_valid"),
                    issue=s.get("issue")
                ))

        # Log extracted information
        print(f"\n[SimpleLLMGrader] === EXTRACTED GIVENS ({len(givens)}) ===")
        for g in givens:
            conf_indicator = "HIGH" if g.confidence >= 0.8 else "MED" if g.confidence >= 0.5 else "LOW"
            print(f"  [{conf_indicator} {g.confidence:.2f}] [{g.source}] {g.fact}")

        print(f"\n[SimpleLLMGrader] === EXTRACTED STEPS ({len(steps)}) ===")
        for s in steps:
            conf_indicator = "HIGH" if s.confidence >= 0.8 else "MED" if s.confidence >= 0.5 else "LOW"
            valid_indicator = "VALID" if s.is_valid else "INVALID" if s.is_valid is False else "?"
            issue_text = f" -> {s.issue}" if s.issue else ""
            print(f"  Step {s.step_number}: [{conf_indicator} {s.confidence:.2f}] [{valid_indicator}] {s.content[:80]}...{issue_text}")

        # Extract other fields
        minor_issues = result.get("minor_issues", [])
        major_issues = result.get("major_issues", [])
        cascade_issues = result.get("cascade_issues", [])

        # Calculate score based on issue counts:
        # - Major issues: -35 points each
        # - Cascade issues: -10 points each
        # - Minor issues: -3 points each
        # - Deduct from 100 until score reaches 0
        major_deduction = len(major_issues) * 35
        cascade_deduction = len(cascade_issues) * 10
        minor_deduction = len(minor_issues) * 3

        total_deduction = major_deduction + cascade_deduction + minor_deduction
        total_score = max(0, max_points - total_deduction)

        print(f"\n[SimpleLLMGrader] Score: {total_score}/{max_points}")
        print(f"  - Major issues: {len(major_issues)} × -35 = -{major_deduction} pts")
        print(f"  - Cascade issues: {len(cascade_issues)} × -10 = -{cascade_deduction} pts")
        print(f"  - Minor issues: {len(minor_issues)} × -3 = -{minor_deduction} pts")
        print(f"  - Total deduction: -{total_deduction} pts")

        return SimpleGradingResult(
            total_score=total_score,
            max_score=max_points,
            is_correct=result.get("is_correct", False),
            is_reasoning_valid=result.get("is_reasoning_valid", False),
            problem_goal=result.get("problem_goal", ""),
            student_answer=result.get("student_answer", ""),
            correct_answer=result.get("correct_answer", ""),
            givens=givens,
            steps=steps,
            minor_issues=minor_issues,
            major_issues=major_issues,
            cascade_issues=cascade_issues,
            summary=result.get("summary", ""),
            raw_response=result
        )
