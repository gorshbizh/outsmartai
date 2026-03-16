#!/usr/bin/env python3
"""
Tests for the LLM-Native Geometry Grader

Tests cover:
1. Unit tests for data models (no pytest required)
2. Unit tests for tool handler (requires pytest)
3. Unit tests for grader phases with mocked LLM responses (requires pytest)
4. Integration tests with real images (requires API key)
"""

import sys
import os
import json
from typing import Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graders.llm_grader_models import (
    ProblemAnalysis,
    StudentStep,
    StudentConstruction,
    StudentWorkExtraction,
    StepVerification,
    ConstructionVerification,
    GradingResult,
    ToolCall,
)
from graders.image_verification_tools import (
    ImageVerificationToolHandler,
    get_tool_definitions,
    IMAGE_VERIFICATION_TOOLS,
)
from graders.llm_native_grader import LLMNativeGeometryGrader


# ============================================================================
# Basic Tests (no pytest required)
# ============================================================================

def test_problem_analysis():
    """Test ProblemAnalysis dataclass"""
    pa = ProblemAnalysis(
        problem_text="Prove angle ABC = 90 degrees",
        givens=["AB is diameter", "C is on circle"],
        goal="Prove angle ABC = 90",
        required_method=None,
        diagram_elements={"points": ["A", "B", "C"], "circles": ["Circle with center O"]}
    )
    d = pa.to_dict()
    assert d["problem_text"] == "Prove angle ABC = 90 degrees"
    assert len(d["givens"]) == 2
    assert d["goal"] == "Prove angle ABC = 90"
    assert "A" in d["diagram_elements"]["points"]

    # Test from_dict
    data = {
        "problem_text": "Test problem",
        "givens": ["Given 1"],
        "goal": "Find X",
        "diagram_elements": {}
    }
    pa2 = ProblemAnalysis.from_dict(data)
    assert pa2.problem_text == "Test problem"
    assert pa2.givens == ["Given 1"]
    print("  ProblemAnalysis: OK")


def test_student_step():
    """Test StudentStep dataclass"""
    step = StudentStep(
        step_id="S1",
        raw_text="OA = OB = r",
        normalized_claim="OA equals OB equals radius",
        depends_on=["GIVEN"]
    )
    d = step.to_dict()
    assert d["step_id"] == "S1"
    assert d["depends_on"] == ["GIVEN"]

    # Test from_dict
    data = {
        "step_id": "S2",
        "raw_text": "Triangle is isosceles",
        "normalized_claim": "Triangle AOB is isosceles",
        "depends_on": ["S1"]
    }
    step2 = StudentStep.from_dict(data)
    assert step2.step_id == "S2"
    assert "S1" in step2.depends_on
    print("  StudentStep: OK")


def test_step_verification():
    """Test StepVerification dataclass"""
    # Valid step
    sv = StepVerification(
        step_id="S1",
        verdict="valid",
        justification="Follows from given",
        evidence_source="given"
    )
    d = sv.to_dict()
    assert d["verdict"] == "valid"
    assert "error_type" not in d  # Should not include None fields

    # Invalid step
    sv2 = StepVerification(
        step_id="S2",
        verdict="invalid",
        justification="Computation error",
        evidence_source="reasoning",
        error_type="computational_error",
        error_details="2 + 2 != 5",
        points_deducted=10
    )
    d2 = sv2.to_dict()
    assert d2["verdict"] == "invalid"
    assert d2["error_type"] == "computational_error"
    assert d2["points_deducted"] == 10

    # Cascading error
    sv3 = StepVerification(
        step_id="S3",
        verdict="cascading_error",
        justification="Depends on invalid step S2",
        evidence_source="reasoning",
        error_type="cascading_error",
        root_cause_step="S2"
    )
    d3 = sv3.to_dict()
    assert d3["verdict"] == "cascading_error"
    assert d3["root_cause_step"] == "S2"
    print("  StepVerification: OK")


def test_grading_result():
    """Test GradingResult dataclass"""
    # Full marks
    result = GradingResult(
        total_score=100,
        max_score=100,
        goal_achieved=True,
        steps_feedback=[
            StepVerification("S1", "valid", "Correct", "given"),
            StepVerification("S2", "valid", "Correct", "reasoning"),
        ],
        summary="Perfect solution"
    )
    d = result.to_dict()
    assert d["total_score"] == 100
    assert d["goal_achieved"] is True
    assert len(d["steps_feedback"]) == 2

    # With errors
    result2 = GradingResult(
        total_score=70,
        max_score=100,
        goal_achieved=False,
        steps_feedback=[
            StepVerification("S1", "valid", "Correct", "given"),
            StepVerification("S2", "invalid", "Error", "reasoning", "logical_error", "Wrong"),
            StepVerification("S3", "cascading_error", "Cascading", "reasoning", root_cause_step="S2"),
        ],
        summary="Errors found",
        cascading_chains=[["S2", "S3"]]
    )
    d2 = result2.to_dict()
    assert d2["total_score"] == 70
    assert d2["cascading_chains"] == [["S2", "S3"]]
    print("  GradingResult: OK")


def test_tool_definitions():
    """Test tool definitions structure"""
    tools = get_tool_definitions()
    assert len(tools) == 3

    tool_names = [t["function"]["name"] for t in tools]
    assert "verify_in_problem_image" in tool_names
    assert "verify_in_student_image" in tool_names
    assert "check_construction_validity" in tool_names

    # Check verify_in_problem_image schema
    verify_tool = next(t for t in tools if t["function"]["name"] == "verify_in_problem_image")
    assert verify_tool["type"] == "function"
    params = verify_tool["function"]["parameters"]
    assert "query" in params["properties"]
    assert "expected_answer" in params["properties"]
    assert "query" in params["required"]
    print("  Tool definitions: OK")


def run_basic_tests():
    """Run basic non-async tests without pytest"""
    print("\n" + "=" * 80)
    print("Running basic model tests")
    print("=" * 80)

    test_problem_analysis()
    test_student_step()
    test_step_verification()
    test_grading_result()
    test_tool_definitions()

    print("\n" + "=" * 80)
    print("All basic tests passed!")
    print("=" * 80)


# ============================================================================
# Pytest-based tests (only loaded when pytest is available)
# ============================================================================

try:
    import pytest
    from unittest.mock import AsyncMock, MagicMock, patch
    PYTEST_AVAILABLE = True
except ImportError:
    PYTEST_AVAILABLE = False


if PYTEST_AVAILABLE:

    class TestImageVerificationToolHandler:
        """Tests for ImageVerificationToolHandler with mocked LLM"""

        @pytest.fixture
        def mock_llm_service(self):
            """Create a mock LLM service"""
            service = MagicMock()
            service.chat = AsyncMock(return_value={
                "answer": "yes",
                "confidence": 0.9,
                "evidence": "Verified in image",
                "details": "Clear observation"
            })
            return service

        @pytest.fixture
        def handler(self, mock_llm_service):
            """Create a tool handler with mock service"""
            return ImageVerificationToolHandler(
                llm_service=mock_llm_service,
                problem_image=b"fake_problem_image_data",
                student_image=b"fake_student_image_data",
                model="claude-opus-4-5"
            )

        @pytest.mark.asyncio
        async def test_verify_in_problem_image(self, handler):
            result = await handler.handle_tool_call(
                "verify_in_problem_image",
                {"query": "Is O the center of the circle?", "expected_answer": "Yes"}
            )
            assert "answer" in result
            assert result["answer"] == "yes"

        @pytest.mark.asyncio
        async def test_verify_in_student_image(self, handler):
            result = await handler.handle_tool_call(
                "verify_in_student_image",
                {"query": "Did student draw perpendicular?", "context": "Step S2"}
            )
            assert "answer" in result

        @pytest.mark.asyncio
        async def test_check_construction_validity(self, handler, mock_llm_service):
            mock_llm_service.chat = AsyncMock(return_value={
                "is_valid": True,
                "reason": "Valid compass construction",
                "confidence": 0.95,
                "visible_in_diagram": True
            })

            result = await handler.handle_tool_call(
                "check_construction_validity",
                {"construction": "Draw perpendicular from C to AB", "justification": "Standard construction"}
            )
            assert result.get("is_valid") is True

        @pytest.mark.asyncio
        async def test_unknown_tool(self, handler):
            result = await handler.handle_tool_call(
                "unknown_tool",
                {}
            )
            assert "error" in result


    class TestLLMNativeGeometryGrader:
        """Tests for the main grader class with mocked LLM responses"""

        @pytest.fixture
        def mock_llm_service(self):
            """Create a comprehensive mock LLM service"""
            service = MagicMock()

            service.chat = AsyncMock(return_value={
                "problem_text": "Prove angle inscribed in semicircle is 90 degrees",
                "givens": ["AB is diameter of circle O", "C is on circle"],
                "goal": "Prove angle ACB = 90 degrees",
                "required_method": None,
                "diagram_elements": {
                    "points": ["A", "B", "C", "O"],
                    "circles": ["Circle with center O"],
                    "lines": ["AB", "AC", "BC"]
                }
            })

            service.chat_with_two_images = AsyncMock(return_value={
                "constructions": [
                    {
                        "construction_id": "C1",
                        "description": "Draw radius OC",
                        "justification": "Connect center to point on circle"
                    }
                ],
                "steps": [
                    {
                        "step_id": "S1",
                        "raw_text": "OA = OB = OC = r",
                        "normalized_claim": "All radii are equal",
                        "depends_on": ["GIVEN"]
                    },
                    {
                        "step_id": "S2",
                        "raw_text": "Triangle OAC is isosceles",
                        "normalized_claim": "Triangle OAC is isosceles because OA = OC",
                        "depends_on": ["S1"]
                    },
                    {
                        "step_id": "S3",
                        "raw_text": "angle ACB = 90",
                        "normalized_claim": "Angle ACB equals 90 degrees",
                        "depends_on": ["S2"]
                    }
                ],
                "final_answer": "angle ACB = 90 degrees"
            })

            return service

        @pytest.fixture
        def grader(self, mock_llm_service):
            return LLMNativeGeometryGrader(mock_llm_service, model="claude-opus-4-5")

        @pytest.mark.asyncio
        async def test_phase1_problem_understanding(self, grader, mock_llm_service):
            result = await grader._phase1_problem_understanding(b"fake_image")

            assert isinstance(result, ProblemAnalysis)
            assert "90" in result.goal
            assert len(result.givens) >= 1
            mock_llm_service.chat.assert_called_once()

        @pytest.mark.asyncio
        async def test_phase2_extract_student_work(self, grader, mock_llm_service):
            problem_analysis = ProblemAnalysis(
                problem_text="Test",
                givens=["Given"],
                goal="Prove X"
            )

            result = await grader._phase2_extract_student_work(
                b"problem_img", b"student_img", problem_analysis
            )

            assert isinstance(result, StudentWorkExtraction)
            assert len(result.steps) == 3
            assert len(result.constructions) == 1
            assert result.final_answer is not None

        @pytest.mark.asyncio
        async def test_cascading_error_detection(self, grader):
            """Test that cascading errors are properly detected"""
            problem_analysis = ProblemAnalysis(
                problem_text="Test", givens=["Given"], goal="Prove X"
            )
            student_work = StudentWorkExtraction(
                constructions=[],
                steps=[
                    StudentStep("S1", "Step 1", "Claim 1", ["GIVEN"]),
                    StudentStep("S2", "Step 2 (error)", "Wrong claim", ["S1"]),
                    StudentStep("S3", "Step 3", "Depends on S2", ["S2"]),
                ],
                final_answer="Answer"
            )

            mock_handler = MagicMock()
            mock_handler.handle_tool_call = AsyncMock(return_value={
                "is_valid": True, "reason": "OK"
            })

            grader.llm_service.chat = AsyncMock(side_effect=[
                {"verdict": "valid", "justification": "Correct", "evidence_source": "given"},
                {"verdict": "invalid", "justification": "Error", "evidence_source": "reasoning",
                 "error_type": "logical_error", "error_details": "Wrong"},
            ])

            verifications, _ = await grader._phase3_verify_steps(
                problem_analysis, student_work, mock_handler
            )

            assert verifications[2].verdict == "cascading_error"
            assert verifications[2].root_cause_step == "S2"


    class TestGraderScoring:
        """Test the scoring logic"""

        def test_check_goal_achieved_with_no_errors(self):
            grader = LLMNativeGeometryGrader(MagicMock())

            verifications = [
                StepVerification("S1", "valid", "OK", "given"),
                StepVerification("S2", "valid", "OK", "reasoning"),
            ]

            result = grader._check_goal_achieved("Answer = 90", "Prove X = 90", verifications)
            assert result is True

        def test_check_goal_achieved_with_errors(self):
            grader = LLMNativeGeometryGrader(MagicMock())

            verifications = [
                StepVerification("S1", "valid", "OK", "given"),
                StepVerification("S2", "invalid", "Error", "reasoning", "logical_error"),
            ]

            result = grader._check_goal_achieved("Answer = 90", "Prove X = 90", verifications)
            assert result is False

        def test_generate_summary_full_marks(self):
            grader = LLMNativeGeometryGrader(MagicMock())

            valid_steps = [StepVerification("S1", "valid", "OK", "given")]
            root_errors = []
            cascading_errors = []

            summary = grader._generate_summary(valid_steps, root_errors, cascading_errors, True, 100, 100)
            assert "100/100" in summary
            assert "Excellent" in summary

        def test_generate_summary_with_errors(self):
            grader = LLMNativeGeometryGrader(MagicMock())

            valid_steps = [StepVerification("S1", "valid", "OK", "given")]
            root_errors = [StepVerification("S2", "invalid", "Error", "reasoning", "logical_error")]
            cascading_errors = [StepVerification("S3", "cascading_error", "Cascade", "reasoning")]

            summary = grader._generate_summary(valid_steps, root_errors, cascading_errors, False, 60, 100)
            assert "60/100" in summary
            assert "1 steps were affected by previous errors" in summary


    @pytest.mark.skipif(
        not os.environ.get("LLM_API_KEY"),
        reason="Integration tests require LLM_API_KEY environment variable"
    )
    class TestIntegration:
        """Integration tests with real images and API calls"""

        @pytest.fixture
        def test_data_dir(self):
            return os.path.join(os.path.dirname(__file__), "data")

        @pytest.fixture
        def llm_service(self):
            """Create real LLM service"""
            from app import LLMService
            return LLMService()

        def load_image(self, path: str) -> bytes:
            with open(path, "rb") as f:
                return f.read()

        @pytest.mark.asyncio
        async def test_correct_solution(self, test_data_dir, llm_service):
            """Test grading a correct solution"""
            problem_image = self.load_image(os.path.join(test_data_dir, "geo_1.png"))
            student_image = self.load_image(os.path.join(test_data_dir, "geo_1_c_1.png"))

            grader = LLMNativeGeometryGrader(llm_service)
            result = await grader.grade(problem_image, student_image, max_points=100)

            assert result.total_score > 70
            assert isinstance(result.summary, str)

        @pytest.mark.asyncio
        async def test_incorrect_solution(self, test_data_dir, llm_service):
            """Test grading an incorrect solution"""
            if not os.path.exists(os.path.join(test_data_dir, "geo_2_w_1.png")):
                pytest.skip("Wrong solution image not available")

            problem_image = self.load_image(os.path.join(test_data_dir, "geo_2.png"))
            student_image = self.load_image(os.path.join(test_data_dir, "geo_2_w_1.png"))

            grader = LLMNativeGeometryGrader(llm_service)
            result = await grader.grade(problem_image, student_image, max_points=100)

            assert result.total_score < 100
            has_errors = any(sf.verdict in ["invalid", "cascading_error"] for sf in result.steps_feedback)
            assert has_errors or not result.goal_achieved


if __name__ == "__main__":
    run_basic_tests()

    print("\nTo run full test suite with pytest:")
    print("  pip install pytest pytest-asyncio")
    print("  pytest tests/test_llm_native_grader.py -v")
