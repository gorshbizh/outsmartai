"""
Image verification tools for the LLM-native geometry grader.

These tools allow the grading model to re-inspect images during step verification,
making fresh vision API calls focused on specific queries.
"""

import base64
import json
from typing import Dict, List, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app import LLMService


# OpenAI function definitions for tool calling
IMAGE_VERIFICATION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "verify_in_problem_image",
            "description": "Re-inspect the original problem image to verify a geometric fact, measurement, or relationship. Use this to check claims about the original diagram.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to verify in the problem image (e.g., 'Is point O the center of the circle?', 'Are lines AB and CD parallel?')"
                    },
                    "expected_answer": {
                        "type": "string",
                        "description": "The student's claim or expected answer to verify against"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "verify_in_student_image",
            "description": "Re-inspect the student's annotated solution image to verify their constructions, labels, or work shown.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to verify in the student's solution image"
                    },
                    "context": {
                        "type": "string",
                        "description": "Additional context about what step or construction this relates to"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_construction_validity",
            "description": "Verify that a student's geometric construction (auxiliary line, point, etc.) is mathematically valid and follows from the given information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "construction": {
                        "type": "string",
                        "description": "Description of the construction (e.g., 'Draw perpendicular from C to AB')"
                    },
                    "justification": {
                        "type": "string",
                        "description": "The student's stated justification for the construction, if any"
                    }
                },
                "required": ["construction"]
            }
        }
    }
]


class ImageVerificationToolHandler:
    """
    Handles tool calls during step verification by making fresh vision API calls.

    Each tool invocation results in a separate API call focused on the specific query,
    ensuring the model always has access to up-to-date image analysis.
    """

    def __init__(
        self,
        llm_service: "LLMService",
        problem_image: bytes,
        student_image: bytes,
        model: str = "claude-opus-4-5"
    ):
        """
        Initialize the tool handler.

        Args:
            llm_service: The LLM service for making API calls
            problem_image: Raw bytes of the problem image
            student_image: Raw bytes of the student's solution image
            model: Model to use for vision queries
        """
        self.llm_service = llm_service
        self.problem_image = problem_image
        self.student_image = student_image
        self.model = model

    async def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle a tool call by making the appropriate vision API call.

        Args:
            tool_name: Name of the tool being called
            arguments: Arguments passed to the tool

        Returns:
            Result dictionary with verification findings
        """
        if tool_name == "verify_in_problem_image":
            return await self._verify_in_problem_image(arguments)
        elif tool_name == "verify_in_student_image":
            return await self._verify_in_student_image(arguments)
        elif tool_name == "check_construction_validity":
            return await self._check_construction_validity(arguments)
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    async def _verify_in_problem_image(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Make a focused vision query on the problem image."""
        query = arguments.get("query", "")
        expected_answer = arguments.get("expected_answer", "")

        prompt = f"""Examine this geometry problem image carefully and answer the following question:

Question: {query}
{f"Student's claim to verify: {expected_answer}" if expected_answer else ""}

Provide a JSON response with:
{{
    "answer": "yes" | "no" | "unclear",
    "confidence": 0.0-1.0,
    "evidence": "What you observed in the image that supports your answer",
    "details": "Any additional relevant observations"
}}

Be precise and only report what you can actually observe in the diagram."""

        result = await self._make_vision_call(self.problem_image, prompt)
        return result

    async def _verify_in_student_image(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Make a focused vision query on the student's solution image."""
        query = arguments.get("query", "")
        context = arguments.get("context", "")

        prompt = f"""Examine this student's geometry solution image carefully and answer the following question:

Question: {query}
{f"Context: {context}" if context else ""}

Provide a JSON response with:
{{
    "answer": "yes" | "no" | "unclear",
    "confidence": 0.0-1.0,
    "evidence": "What you observed in the image that supports your answer",
    "details": "Any additional relevant observations about the student's work"
}}

Focus on the student's annotations, constructions, and written work."""

        result = await self._make_vision_call(self.student_image, prompt)
        return result

    async def _check_construction_validity(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verify if a construction is mathematically valid.
        This checks both images to see if the construction is consistent.
        """
        construction = arguments.get("construction", "")
        justification = arguments.get("justification", "")

        prompt = f"""Evaluate the validity of this geometric construction:

Construction: {construction}
{f"Student's justification: {justification}" if justification else "No justification provided"}

Provide a JSON response with:
{{
    "is_valid": true | false,
    "reason": "Why the construction is or isn't valid",
    "confidence": 0.0-1.0,
    "visible_in_diagram": true | false,
    "notes": "Any additional observations"
}}

A construction is valid if:
1. It can be performed with compass and straightedge (or is explicitly allowed)
2. It follows from the given information
3. It doesn't introduce unwarranted assumptions"""

        # Check construction in student image
        result = await self._make_vision_call(self.student_image, prompt)
        return result

    async def _make_vision_call(self, image_data: bytes, prompt: str) -> Dict[str, Any]:
        """Make a vision API call with the given image and prompt."""
        try:
            messages = [
                {
                    "role": "system",
                    "content": "You are a precise geometry image analyzer. Always respond with valid JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]

            result = await self.llm_service.chat(
                messages=messages,
                model=self.model,
                temperature=0.0,
                image_data=image_data
            )

            # If we got a raw response, try to parse it
            if "raw" in result:
                raw_content = result["raw"]
                # Strip markdown code fences if present
                if raw_content.startswith("```"):
                    raw_content = raw_content.split('\n', 1)[1] if '\n' in raw_content else raw_content
                    if raw_content.endswith("```"):
                        raw_content = raw_content.rsplit("```", 1)[0]
                    raw_content = raw_content.strip()

                try:
                    return json.loads(raw_content)
                except json.JSONDecodeError:
                    return {"raw_response": result["raw"], "parsed": False}

            return result

        except Exception as e:
            return {"error": str(e), "success": False}


def get_tool_definitions() -> List[Dict[str, Any]]:
    """Return the OpenAI function definitions for image verification tools."""
    return IMAGE_VERIFICATION_TOOLS
