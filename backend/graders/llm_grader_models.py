"""
Data models for the LLM-native geometry grader.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional


@dataclass
class ProblemAnalysis:
    """Result of Phase 1: Understanding the problem from the problem image"""
    problem_text: str
    givens: List[str]
    goal: str
    required_method: Optional[str] = None
    diagram_elements: Dict[str, List[str]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "problem_text": self.problem_text,
            "givens": self.givens,
            "goal": self.goal,
            "required_method": self.required_method,
            "diagram_elements": self.diagram_elements,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProblemAnalysis":
        return cls(
            problem_text=data.get("problem_text", ""),
            givens=data.get("givens", []),
            goal=data.get("goal", ""),
            required_method=data.get("required_method"),
            diagram_elements=data.get("diagram_elements", {}),
        )


@dataclass
class StudentStep:
    """A single step extracted from the student's solution"""
    step_id: str
    raw_text: str
    normalized_claim: str
    depends_on: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "raw_text": self.raw_text,
            "normalized_claim": self.normalized_claim,
            "depends_on": self.depends_on,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StudentStep":
        return cls(
            step_id=data.get("step_id", ""),
            raw_text=data.get("raw_text", ""),
            normalized_claim=data.get("normalized_claim", ""),
            depends_on=data.get("depends_on", []),
        )


@dataclass
class StudentConstruction:
    """A geometric construction made by the student"""
    construction_id: str
    description: str
    justification: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "construction_id": self.construction_id,
            "description": self.description,
            "justification": self.justification,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StudentConstruction":
        return cls(
            construction_id=data.get("construction_id", ""),
            description=data.get("description", ""),
            justification=data.get("justification"),
        )


@dataclass
class StudentWorkExtraction:
    """Result of Phase 2: Extracting student's work from their solution image"""
    constructions: List[StudentConstruction]
    steps: List[StudentStep]
    final_answer: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "constructions": [c.to_dict() for c in self.constructions],
            "steps": [s.to_dict() for s in self.steps],
            "final_answer": self.final_answer,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StudentWorkExtraction":
        return cls(
            constructions=[StudentConstruction.from_dict(c) for c in data.get("constructions", [])],
            steps=[StudentStep.from_dict(s) for s in data.get("steps", [])],
            final_answer=data.get("final_answer"),
        )


@dataclass
class ToolCall:
    """Record of a tool call made during verification"""
    tool_name: str
    arguments: Dict[str, Any]
    result: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool": self.tool_name,
            "arguments": self.arguments,
            "result": self.result,
        }


@dataclass
class StepVerification:
    """Result of verifying a single step in Phase 3"""
    step_id: str
    verdict: str  # "valid" | "imperfect" | "invalid" | "cascading_error"
    justification: str
    evidence_source: str  # "problem_image" | "student_image" | "reasoning" | "given"
    error_type: Optional[str] = None  # "computational_error" | "logical_error" | "missing_justification" | "incorrect_claim"
    error_details: Optional[str] = None
    root_cause_step: Optional[str] = None
    tool_calls_made: List[ToolCall] = field(default_factory=list)
    points_deducted: int = 0

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "step_id": self.step_id,
            "verdict": self.verdict,
            "justification": self.justification,
            "evidence_source": self.evidence_source,
        }

        if self.error_type:
            result["error_type"] = self.error_type
        if self.error_details:
            result["error_details"] = self.error_details
        if self.root_cause_step:
            result["root_cause_step"] = self.root_cause_step
        if self.tool_calls_made:
            result["tool_calls_made"] = [tc.to_dict() for tc in self.tool_calls_made]
        if self.points_deducted > 0:
            result["points_deducted"] = self.points_deducted

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepVerification":
        tool_calls = []
        for tc_data in data.get("tool_calls_made", []):
            tool_calls.append(ToolCall(
                tool_name=tc_data.get("tool", ""),
                arguments=tc_data.get("arguments", {}),
                result=tc_data.get("result", {}),
            ))

        return cls(
            step_id=data.get("step_id", ""),
            verdict=data.get("verdict", ""),
            justification=data.get("justification", ""),
            evidence_source=data.get("evidence_source", "reasoning"),
            error_type=data.get("error_type"),
            error_details=data.get("error_details"),
            root_cause_step=data.get("root_cause_step"),
            tool_calls_made=tool_calls,
            points_deducted=data.get("points_deducted", 0),
        )


@dataclass
class ConstructionVerification:
    """Result of verifying a student construction"""
    construction_id: str
    is_valid: bool
    justification: str
    tool_calls_made: List[ToolCall] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "construction_id": self.construction_id,
            "is_valid": self.is_valid,
            "justification": self.justification,
            "tool_calls_made": [tc.to_dict() for tc in self.tool_calls_made],
        }


@dataclass
class GradingResult:
    """Final result of the LLM-native grading pipeline"""
    total_score: int
    max_score: int
    goal_achieved: bool
    steps_feedback: List[StepVerification]
    construction_feedback: List[ConstructionVerification] = field(default_factory=list)
    summary: str = ""
    cascading_chains: List[List[str]] = field(default_factory=list)
    problem_analysis: Optional[ProblemAnalysis] = None
    student_work: Optional[StudentWorkExtraction] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "total_score": self.total_score,
            "max_score": self.max_score,
            "goal_achieved": self.goal_achieved,
            "steps_feedback": [sf.to_dict() for sf in self.steps_feedback],
            "summary": self.summary,
            "cascading_chains": self.cascading_chains,
        }

        if self.construction_feedback:
            result["construction_feedback"] = [cf.to_dict() for cf in self.construction_feedback]
        if self.problem_analysis:
            result["problem_analysis"] = self.problem_analysis.to_dict()
        if self.student_work:
            result["student_work"] = self.student_work.to_dict()

        return result
