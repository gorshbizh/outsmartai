from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from werkzeug.security import generate_password_hash


BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
SCHEMA_PATH = BACKEND_DIR / "schema.sql"
TEST_DATA_DIR = BACKEND_DIR / "tests" / "data"


class DatabaseUnavailable(RuntimeError):
    """Raised when MySQL or its driver is not reachable."""


def _import_pymysql():
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError as exc:
        raise DatabaseUnavailable(
            "PyMySQL is not installed. Run `pip install -r backend/requirements.txt`."
        ) from exc
    return pymysql, DictCursor


def _database_name() -> str:
    database_name = os.getenv("MYSQL_DATABASE", "outsmartai")
    if not re.match(r"^[A-Za-z0-9_]+$", database_name):
        raise DatabaseUnavailable("MYSQL_DATABASE can only contain letters, numbers, and underscores")
    return database_name


def _db_config(include_database: bool = True) -> Dict[str, Any]:
    _, dict_cursor = _import_pymysql()
    config: Dict[str, Any] = {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "charset": "utf8mb4",
        "cursorclass": dict_cursor,
        "autocommit": True,
    }
    if include_database:
        config["database"] = _database_name()
    return config


def get_connection(include_database: bool = True):
    pymysql, _ = _import_pymysql()
    try:
        return pymysql.connect(**_db_config(include_database=include_database))
    except Exception as exc:
        raise DatabaseUnavailable(f"MySQL connection failed: {exc}") from exc


def _split_sql(sql: str) -> List[str]:
    statements: List[str] = []
    current: List[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(current).rstrip(";"))
            current = []
    if current:
        statements.append("\n".join(current))
    return statements


def initialize_database() -> None:
    database_name = _database_name()
    try:
        with get_connection(include_database=False) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{database_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
    except DatabaseUnavailable as exc:
        print(f"MySQL database creation skipped: {exc}")

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection(include_database=True) as conn:
        with conn.cursor() as cursor:
            for statement in _split_sql(schema_sql):
                cursor.execute(statement)
            _ensure_column(cursor, "solutions", "grading_steps", "JSON NULL", after="canvas_data")
            _ensure_column(cursor, "solutions", "solution_type", "ENUM('draft', 'graded') NOT NULL DEFAULT 'draft'", after="canvas_data")
            _ensure_column(cursor, "solutions", "parent_solution_id", "VARCHAR(120) NULL", after="solution_type")
            _ensure_column(cursor, "solutions", "progress_slot", "TINYINT NULL", after="parent_solution_id")
            _ensure_column(cursor, "solutions", "points_taken", "JSON NULL", after="grading_result")
            _ensure_column(cursor, "solutions", "major_points", "JSON NULL", after="points_taken")
            _ensure_column(cursor, "solutions", "minor_points", "JSON NULL", after="major_points")
            _ensure_column(cursor, "solutions", "graded_at", "TIMESTAMP NULL", after="grading_result")
            _migrate_solution_model(cursor)


def _ensure_column(cursor, table_name: str, column_name: str, definition: str, after: Optional[str] = None) -> None:
    cursor.execute(
        """
        SELECT COUNT(*) AS count
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        """,
        (table_name, column_name),
    )
    if int(cursor.fetchone()["count"]) > 0:
        return
    after_clause = f" AFTER `{after}`" if after else ""
    cursor.execute(f"ALTER TABLE `{table_name}` ADD COLUMN `{column_name}` {definition}{after_clause}")


def _ensure_index(cursor, table_name: str, index_name: str, ddl: str) -> None:
    cursor.execute(
        """
        SELECT COUNT(*) AS count
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND INDEX_NAME = %s
        """,
        (table_name, index_name),
    )
    if int(cursor.fetchone()["count"]) > 0:
        return
    cursor.execute(ddl)


def _drop_index(cursor, table_name: str, index_name: str) -> None:
    cursor.execute(
        """
        SELECT COUNT(*) AS count
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND INDEX_NAME = %s
        """,
        (table_name, index_name),
    )
    if int(cursor.fetchone()["count"]) == 0:
        return
    cursor.execute(f"ALTER TABLE `{table_name}` DROP INDEX `{index_name}`")


def _migrate_solution_model(cursor) -> None:
    cursor.execute(
        """
        UPDATE solutions
        SET solution_type = CASE
            WHEN graded_at IS NOT NULL OR grading_result IS NOT NULL THEN 'graded'
            ELSE 'draft'
        END
        """
    )

    cursor.execute(
        """
        UPDATE solutions
        SET progress_slot = NULL
        """
    )

    _drop_index(cursor, "solutions", "uq_solutions_single_draft")

    _ensure_index(
        cursor,
        "solutions",
        "idx_solutions_problem_type",
        "CREATE INDEX idx_solutions_problem_type ON solutions (problem_id, solution_type, updated_at)",
    )
    _ensure_index(
        cursor,
        "solutions",
        "idx_solutions_user_problem_type_time",
        "CREATE INDEX idx_solutions_user_problem_type_time ON solutions (user_id, problem_id, solution_type, updated_at, id)",
    )
    _ensure_index(
        cursor,
        "solutions",
        "idx_solutions_progress_slot",
        "CREATE INDEX idx_solutions_progress_slot ON solutions (user_id, problem_id, progress_slot)",
    )
    _ensure_index(
        cursor,
        "solutions",
        "idx_solutions_parent_time",
        "CREATE INDEX idx_solutions_parent_time ON solutions (parent_solution_id, created_at)",
    )


def seed_test_data() -> Dict[str, int]:
    repo = AppRepository()
    admin_user = repo.ensure_seed_user(
        username=os.getenv("ADMIN_USERNAME", "admin"),
        password=os.getenv("ADMIN_PASSWORD", os.getenv("ADMIN_USER_PASSWORD", "admin1234")),
        display_name=os.getenv("ADMIN_DISPLAY_NAME", "Admin User"),
        email=os.getenv("ADMIN_EMAIL") or None,
    )

    problem_count = 0
    solution_count = 0
    for problem_path in _discover_problem_images():
        problem_id = problem_path.stem
        category = problem_id.split("_", 1)[0]
        sort_order = _sort_order(problem_id)
        repo.upsert_seed_problem(
            problem_id=problem_id,
            title=_titleize(problem_id),
            category=category,
            image_path=_repo_relative(problem_path),
            sort_order=sort_order,
        )
        problem_count += 1

        for solution_path in _discover_solution_images(problem_id):
            solution_id = f"seed_{solution_path.stem}"
            repo.upsert_seed_solution(
                solution_id=solution_id,
                problem_id=problem_id,
                user_id=admin_user["id"],
                title=_solution_title(solution_path.stem),
                image_path=_repo_relative(solution_path),
            )
            solution_count += 1

    return {"problems": problem_count, "solutions": solution_count}


def _discover_problem_images() -> List[Path]:
    if not TEST_DATA_DIR.exists():
        return []
    return sorted(
        path
        for path in TEST_DATA_DIR.glob("*.png")
        if not re.search(r"_[cw]_\d+$", path.stem)
    )


def _discover_solution_images(problem_id: str) -> List[Path]:
    if not TEST_DATA_DIR.exists():
        return []
    return sorted(TEST_DATA_DIR.glob(f"{problem_id}_[cw]_*.png"))


def _repo_relative(path: Path) -> str:
    return str(path.resolve().relative_to(REPO_ROOT))


def resolve_repo_path(stored_path: str) -> Path:
    candidate = Path(stored_path)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    resolved = candidate.resolve()
    root = REPO_ROOT.resolve()
    if root != resolved and root not in resolved.parents:
        raise ValueError("Stored path escapes the repository")
    return resolved


def _titleize(value: str) -> str:
    return value.replace("_", " ").title()


def _sort_order(problem_id: str) -> int:
    match = re.search(r"_(\d+)$", problem_id)
    category_order = {"geo": 1000, "alg": 2000, "psda": 3000, "advmath": 4000}
    base = category_order.get(problem_id.split("_", 1)[0], 9000)
    return base + (int(match.group(1)) if match else 0)


def _solution_title(solution_stem: str) -> str:
    if "_c_" in solution_stem:
        label = "Correct"
    elif "_w_" in solution_stem:
        label = "Needs Review"
    else:
        label = "Example"
    return f"{label} solution: {_titleize(solution_stem)}"


def _draft_solution_id(user_id: int, problem_id: str) -> str:
    safe_problem_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", problem_id)[:80]
    return f"draft_{user_id}_{safe_problem_id}"


def _json_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=True)


def _load_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_non_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _grading_container(grading_result: Any) -> Dict[str, Any]:
    if not isinstance(grading_result, dict):
        return {}

    candidates = [
        grading_result.get("result"),
        grading_result.get("grading"),
        grading_result.get("score"),
        grading_result.get("formalgeo_grading"),
    ]
    nested_result = grading_result.get("result")
    if isinstance(nested_result, dict):
        candidates.append(nested_result.get("formalgeo_grading"))
    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    return grading_result


def _score_summary(grading_result: Any) -> Dict[str, Optional[int]]:
    result = _grading_container(grading_result)
    candidates = [result]
    if isinstance(result.get("formalgeo_grading"), dict):
        candidates.append(result["formalgeo_grading"])
    if isinstance(grading_result, dict):
        if isinstance(grading_result.get("formalgeo_grading"), dict):
            candidates.append(grading_result["formalgeo_grading"])
        nested_result = grading_result.get("result")
        if isinstance(nested_result, dict) and isinstance(nested_result.get("formalgeo_grading"), dict):
            candidates.append(nested_result["formalgeo_grading"])

    score: Optional[int] = None
    max_score: Optional[int] = None
    for candidate in candidates:
        score = _first_non_none(
            _coerce_int(candidate.get("total_score")),
            _coerce_int(candidate.get("total_points")),
            _coerce_int(candidate.get("score")),
        )
        max_score = _first_non_none(
            _coerce_int(candidate.get("max_score")),
            _coerce_int(candidate.get("max_points")),
            100 if score is not None else None,
        )
        if score is not None:
            break
    return {
        "score": score,
        "max_score": max_score,
    }


def _normalize_point_item(
    item: Any,
    *,
    fallback_reason: Optional[str] = None,
    fallback_points: Optional[int] = None,
    issue_type: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if isinstance(item, str):
        item = {"description": item}
    if not isinstance(item, dict):
        return None

    points = _first_non_none(
        _coerce_int(item.get("deducted_points")),
        _coerce_int(item.get("points_deducted")),
        _coerce_int(item.get("deduction")),
        _coerce_int(item.get("points")),
        fallback_points,
        0,
    )
    reason = (
        item.get("deduction_reason")
        or item.get("reason")
        or item.get("description")
        or item.get("message")
        or item.get("error_details")
        or fallback_reason
        or "Point deduction recorded"
    )
    step = item.get("deduction_step") or item.get("step_number") or item.get("step_id")
    confidence = _first_non_none(
        _coerce_float(item.get("deduction_confidence_score")),
        _coerce_float(item.get("confidence_score")),
        _coerce_float(item.get("confidence")),
    )
    normalized: Dict[str, Any] = {
        "points_taken": points,
        "reason": reason,
    }
    if step is not None and step != "":
        normalized["step"] = step
    if confidence is not None:
        normalized["confidence"] = confidence
    normalized_issue_type = issue_type or item.get("type")
    if normalized_issue_type:
        normalized["issue_type"] = normalized_issue_type
    if item.get("note"):
        normalized["note"] = item["note"]
    return normalized


def _bucket_point_item(item: Dict[str, Any]) -> str:
    issue_type = str(item.get("issue_type") or "").lower()
    if issue_type in {"major", "cascade", "root"}:
        return "major"
    if issue_type == "minor":
        return "minor"
    return "major" if int(item.get("points_taken") or 0) >= 10 else "minor"


def _points_taken_details(grading_result: Any) -> Dict[str, List[Dict[str, Any]]]:
    major_points: List[Dict[str, Any]] = []
    minor_points: List[Dict[str, Any]] = []

    def add_item(item: Optional[Dict[str, Any]]) -> None:
        if not item:
            return
        bucket = _bucket_point_item(item)
        if bucket == "major":
            major_points.append(item)
        else:
            minor_points.append(item)

    result = _grading_container(grading_result)

    issue_sources = [
        ("major", result.get("major_issues"), 35),
        ("minor", result.get("minor_issues"), 3),
        ("major", result.get("cascade_issues"), 10),
    ]
    used_issue_arrays = False
    for issue_type, issue_list, default_points in issue_sources:
        if not isinstance(issue_list, list):
            continue
        used_issue_arrays = True
        for issue in issue_list:
            add_item(
                _normalize_point_item(
                    issue,
                    fallback_points=default_points,
                    issue_type=issue_type,
                )
            )

    if not used_issue_arrays:
        deductions = result.get("deductions")
        if not isinstance(deductions, list):
            deductions = None
            nested_candidates = [
                result.get("formalgeo_grading"),
                grading_result.get("formalgeo_grading") if isinstance(grading_result, dict) else None,
            ]
            for candidate in nested_candidates:
                if isinstance(candidate, dict) and isinstance(candidate.get("deductions"), list):
                    deductions = candidate.get("deductions")
                    break
        if isinstance(deductions, list):
            for deduction in deductions:
                add_item(_normalize_point_item(deduction))
        else:
            step_feedback = result.get("step_feedback")
            if not isinstance(step_feedback, list):
                nested_candidates = [
                    result.get("formalgeo_grading"),
                    grading_result.get("formalgeo_grading") if isinstance(grading_result, dict) else None,
                ]
                for candidate in nested_candidates:
                    if isinstance(candidate, dict) and isinstance(candidate.get("step_feedback"), list):
                        step_feedback = candidate.get("step_feedback")
                        break
            if isinstance(step_feedback, list):
                for step in step_feedback:
                    normalized = _normalize_point_item(step)
                    if normalized and int(normalized.get("points_taken") or 0) > 0:
                        add_item(normalized)

    return {
        "major": major_points,
        "minor": minor_points,
        "deductions": [*major_points, *minor_points],
    }


def _public_user(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "email": row.get("email"),
        "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
        "updated_at": row.get("updated_at").isoformat() if row.get("updated_at") else None,
    }


def _problem_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "prompt": row.get("prompt"),
        "category": row.get("category"),
        "difficulty": row.get("difficulty"),
        "source": row.get("source"),
        "sort_order": row.get("sort_order"),
        "active": bool(row.get("active")),
        "image_url": f"/api/problems/{row['id']}/image",
        "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
        "updated_at": row.get("updated_at").isoformat() if row.get("updated_at") else None,
    }


def _solution_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    owner_name = row.get("owner_display_name") or row.get("owner_username")
    has_canvas_data = row.get("has_canvas_data")
    if has_canvas_data is None:
        has_canvas_data = bool(row.get("canvas_data"))
    solution_type = row.get("solution_type")
    if not solution_type:
        solution_type = "graded" if row.get("graded_at") or row.get("grading_result") else "draft"
    grading_result = _load_json(row.get("grading_result"))
    points_taken = _load_json(row.get("points_taken"))
    major_points = _load_json(row.get("major_points"))
    minor_points = _load_json(row.get("minor_points"))
    if isinstance(points_taken, dict):
        major_points = points_taken.get("major") if major_points is None else major_points
        minor_points = points_taken.get("minor") if minor_points is None else minor_points
    if grading_result and not isinstance(points_taken, dict):
        derived_points = _points_taken_details(grading_result)
        points_taken = derived_points
        if major_points is None:
            major_points = derived_points["major"]
        if minor_points is None:
            minor_points = derived_points["minor"]
    score_summary = _score_summary(grading_result)
    is_graded = row.get("is_graded")
    if is_graded is None:
        is_graded = solution_type == "graded" or bool(row.get("graded_at") or grading_result)
    return {
        "id": row["id"],
        "problem_id": row["problem_id"],
        "user_id": row.get("user_id"),
        "owner_name": owner_name,
        "title": row["title"],
        "source_kind": row.get("source_kind"),
        "solution_type": solution_type,
        "parent_solution_id": row.get("parent_solution_id"),
        "is_public": bool(row.get("is_public")),
        "has_canvas_data": bool(has_canvas_data),
        "canvas_data": _load_json(row.get("canvas_data")),
        "grading_steps": _load_json(row.get("grading_steps")),
        "grading_result": grading_result,
        "points_taken": points_taken if isinstance(points_taken, dict) else {"major": major_points or [], "minor": minor_points or []},
        "major_points": major_points or [],
        "minor_points": minor_points or [],
        "graded_at": row.get("graded_at").isoformat() if row.get("graded_at") else None,
        "is_graded": bool(is_graded),
        "score": score_summary["score"],
        "max_score": score_summary["max_score"],
        "image_url": f"/api/solutions/{row['id']}/image" if row.get("image_path") else None,
        "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
        "updated_at": row.get("updated_at").isoformat() if row.get("updated_at") else None,
    }


class AppRepository:
    def ensure_seed_user(
        self,
        username: str,
        password: str,
        display_name: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Dict[str, Any]:
        existing = self.get_user_by_username(username)
        if existing:
            return existing
        return self.create_user(
            username=username,
            password=password,
            display_name=display_name or username,
            email=email,
        )

    def create_user(
        self,
        username: str,
        password: str,
        display_name: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Dict[str, Any]:
        username = username.strip()
        display_name = (display_name or username).strip()
        email = (email.strip() or None) if email else None
        password_hash = generate_password_hash(password)
        try:
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO users (username, password_hash, display_name, email)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (username, password_hash, display_name, email),
                    )
                    user_id = cursor.lastrowid
        except Exception as exc:
            if getattr(exc, "args", [None])[0] == 1062:
                raise ValueError("Username or email is already in use") from exc
            raise
        return self.get_user_by_id(user_id)

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, username, display_name, email, created_at, updated_at
                    FROM users WHERE id = %s
                    """,
                    (user_id,),
                )
                row = cursor.fetchone()
        return _public_user(row) if row else None

    def get_user_with_password(self, username: str) -> Optional[Dict[str, Any]]:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, username, password_hash, display_name, email, created_at, updated_at
                    FROM users WHERE username = %s
                    """,
                    (username.strip(),),
                )
                return cursor.fetchone()

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        row = self.get_user_with_password(username)
        return _public_user(row) if row else None

    def update_user(self, user_id: int, display_name: str, email: Optional[str]) -> Dict[str, Any]:
        email = (email.strip() or None) if email else None
        try:
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE users
                        SET display_name = %s, email = %s
                        WHERE id = %s
                        """,
                        (display_name.strip(), email, user_id),
                    )
        except Exception as exc:
            if getattr(exc, "args", [None])[0] == 1062:
                raise ValueError("Email is already in use") from exc
            raise
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")
        return user

    def upsert_seed_problem(
        self,
        problem_id: str,
        title: str,
        category: str,
        image_path: str,
        sort_order: int,
    ) -> None:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO problems (id, title, category, image_path, sort_order, source, active)
                    VALUES (%s, %s, %s, %s, %s, 'backend_tests', TRUE)
                    ON DUPLICATE KEY UPDATE
                      title = VALUES(title),
                      category = VALUES(category),
                      image_path = VALUES(image_path),
                      sort_order = VALUES(sort_order),
                      active = TRUE
                    """,
                    (problem_id, title, category, image_path, sort_order),
                )

    def upsert_seed_solution(
        self,
        solution_id: str,
        problem_id: str,
        user_id: int,
        title: str,
        image_path: str,
    ) -> None:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO solutions
                      (
                        id, problem_id, user_id, title, image_path, canvas_data,
                        solution_type, parent_solution_id, progress_slot,
                        grading_steps, grading_result, points_taken, major_points, minor_points, graded_at,
                        source_kind, is_public
                      )
                    VALUES (%s, %s, %s, %s, %s, NULL, 'draft', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'seed', FALSE)
                    ON DUPLICATE KEY UPDATE
                      user_id = VALUES(user_id),
                      title = VALUES(title),
                      image_path = VALUES(image_path),
                      canvas_data = NULL,
                      solution_type = 'draft',
                      parent_solution_id = NULL,
                      progress_slot = NULL,
                      grading_steps = NULL,
                      grading_result = NULL,
                      points_taken = NULL,
                      major_points = NULL,
                      minor_points = NULL,
                      graded_at = NULL,
                      source_kind = 'seed',
                      is_public = FALSE
                    """,
                    (solution_id, problem_id, user_id, title, image_path),
                )

    def list_progress(self, user_id: int, limit: int, offset: int) -> Dict[str, Any]:
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS total FROM problems WHERE active = TRUE")
                total = int(cursor.fetchone()["total"])
                cursor.execute(
                    """
                    SELECT *
                    FROM problems
                    WHERE active = TRUE
                    ORDER BY sort_order, id
                    LIMIT %s OFFSET %s
                    """,
                    (limit, offset),
                )
                problem_rows = cursor.fetchall()

        draft_lists_by_problem: Dict[str, List[Dict[str, Any]]] = {}
        final_lists_by_problem: Dict[str, List[Dict[str, Any]]] = {}
        if problem_rows:
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    for problem in problem_rows:
                        cursor.execute(
                            """
                            SELECT
                              s.id,
                              s.problem_id,
                              s.user_id,
                              s.title,
                              s.image_path,
                              s.canvas_data,
                              s.solution_type,
                              s.parent_solution_id,
                              s.grading_steps,
                              s.grading_result,
                              s.points_taken,
                              s.major_points,
                              s.minor_points,
                              s.source_kind,
                              s.is_public,
                              s.created_at,
                              s.updated_at,
                              s.graded_at,
                              (s.canvas_data IS NOT NULL) AS has_canvas_data,
                              (s.solution_type = 'graded') AS is_graded,
                              u.username AS owner_username,
                              u.display_name AS owner_display_name
                            FROM solutions s
                            LEFT JOIN users u ON u.id = s.user_id
                            WHERE s.problem_id = %s
                              AND s.user_id = %s
                              AND s.solution_type = 'draft'
                            ORDER BY s.updated_at DESC
                            """,
                            (problem["id"], user_id),
                        )
                        draft_lists_by_problem[problem["id"]] = [
                            _solution_payload(row) for row in cursor.fetchall()
                        ]

                        cursor.execute(
                            """
                            SELECT
                              s.id,
                              s.problem_id,
                              s.user_id,
                              s.title,
                              s.image_path,
                              s.canvas_data,
                              s.solution_type,
                              s.parent_solution_id,
                              s.grading_steps,
                              s.grading_result,
                              s.points_taken,
                              s.major_points,
                              s.minor_points,
                              s.source_kind,
                              s.is_public,
                              s.created_at,
                              s.updated_at,
                              s.graded_at,
                              (s.canvas_data IS NOT NULL) AS has_canvas_data,
                              (s.solution_type = 'graded') AS is_graded,
                              u.username AS owner_username,
                              u.display_name AS owner_display_name
                            FROM solutions s
                            LEFT JOIN users u ON u.id = s.user_id
                            WHERE s.problem_id = %s
                              AND s.user_id = %s
                              AND s.solution_type = 'graded'
                            ORDER BY s.updated_at DESC, s.id DESC
                            """,
                            (problem["id"], user_id),
                        )
                        final_lists_by_problem[problem["id"]] = [
                            _solution_payload(row) for row in cursor.fetchall()
                        ]

        items = []
        for problem in problem_rows:
            payload = _problem_payload(problem)
            draft_solutions = draft_lists_by_problem.get(problem["id"], [])
            final_solutions = final_lists_by_problem.get(problem["id"], [])
            scores_by_draft: Dict[str, List[Dict[str, Any]]] = {}
            unattached_scores: List[Dict[str, Any]] = []
            for score in final_solutions:
                parent_id = score.get("parent_solution_id")
                if parent_id:
                    scores_by_draft.setdefault(parent_id, []).append(score)
                else:
                    unattached_scores.append(score)
            for draft in draft_solutions:
                draft["score_solutions"] = scores_by_draft.pop(draft["id"], [])
            for scores in scores_by_draft.values():
                unattached_scores.extend(scores)
            payload["draft_solutions"] = draft_solutions
            payload["final_solutions"] = final_solutions
            payload["graded_solutions"] = payload["final_solutions"]
            payload["unattached_scores"] = unattached_scores
            payload["solutions"] = payload["draft_solutions"] + payload["final_solutions"]
            items.append(payload)

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(items) < total,
            "items": items,
        }

    def get_problem(self, problem_id: str) -> Optional[Dict[str, Any]]:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM problems WHERE id = %s AND active = TRUE", (problem_id,))
                row = cursor.fetchone()
        return _problem_payload(row) if row else None

    def get_problem_image_path(self, problem_id: str) -> Optional[str]:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT image_path FROM problems WHERE id = %s AND active = TRUE", (problem_id,))
                row = cursor.fetchone()
        return row["image_path"] if row else None

    def list_draft_solutions(self, user_id: int, problem_id: str) -> List[Dict[str, Any]]:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT s.*, u.username AS owner_username, u.display_name AS owner_display_name
                    FROM solutions s
                    LEFT JOIN users u ON u.id = s.user_id
                    WHERE s.user_id = %s
                      AND s.problem_id = %s
                      AND s.solution_type = 'draft'
                    ORDER BY s.updated_at DESC
                    """,
                    (user_id, problem_id),
                )
                rows = cursor.fetchall()
        return [_solution_payload(row) for row in rows]

    def list_final_solutions(self, user_id: int, problem_id: str) -> List[Dict[str, Any]]:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT s.*, u.username AS owner_username, u.display_name AS owner_display_name
                    FROM solutions s
                    LEFT JOIN users u ON u.id = s.user_id
                    WHERE s.user_id = %s
                      AND s.problem_id = %s
                      AND s.solution_type = 'graded'
                    ORDER BY s.updated_at DESC, s.id DESC
                    """,
                    (user_id, problem_id),
                )
                rows = cursor.fetchall()
        return [_solution_payload(row) for row in rows]

    def list_problem_solutions(self, user_id: int, problem_id: str) -> Dict[str, List[Dict[str, Any]]]:
        drafts = self.list_draft_solutions(user_id, problem_id)
        finals = self.list_final_solutions(user_id, problem_id)
        return {
            "draft_solutions": drafts,
            "final_solutions": finals,
            "solutions": drafts + finals,
        }

    def delete_solution(self, user_id: int, solution_id: str) -> Dict[str, Any]:
        solution = self.get_solution(solution_id, user_id=user_id)
        if not solution:
            raise ValueError("Solution not found")

        deleted_ids: List[str] = []
        image_paths: List[str] = []
        with get_connection() as conn:
            with conn.cursor() as cursor:
                if solution.get("solution_type") == "draft":
                    cursor.execute(
                        """
                        SELECT id, image_path
                        FROM solutions
                        WHERE user_id = %s
                          AND parent_solution_id = %s
                          AND solution_type = 'graded'
                        """,
                        (user_id, solution_id),
                    )
                    child_rows = cursor.fetchall()
                    deleted_ids.extend(row["id"] for row in child_rows)
                    image_paths.extend(row["image_path"] for row in child_rows if row.get("image_path"))

                    cursor.execute(
                        """
                        DELETE FROM solutions
                        WHERE user_id = %s
                          AND parent_solution_id = %s
                          AND solution_type = 'graded'
                        """,
                        (user_id, solution_id),
                    )
                elif solution.get("solution_type") != "graded":
                    raise ValueError("Only drafts and scores can be deleted")

                cursor.execute(
                    """
                    SELECT image_path
                    FROM solutions
                    WHERE id = %s AND user_id = %s
                    """,
                    (solution_id, user_id),
                )
                own_row = cursor.fetchone()
                if own_row and own_row.get("image_path"):
                    image_paths.append(own_row["image_path"])

                cursor.execute(
                    """
                    DELETE FROM solutions
                    WHERE id = %s AND user_id = %s
                    """,
                    (solution_id, user_id),
                )
                if cursor.rowcount != 1:
                    raise ValueError("Solution not found")
                deleted_ids.append(solution_id)

        return {
            "deleted_ids": deleted_ids,
            "image_paths": image_paths,
            "deleted_solution_type": solution.get("solution_type"),
        }

    def get_solution(
        self,
        solution_id: str,
        user_id: Optional[int] = None,
        require_access: bool = True,
    ) -> Optional[Dict[str, Any]]:
        access_sql = ""
        params: List[Any] = [solution_id]
        if require_access:
            access_sql = "AND s.user_id = %s"
            params.append(user_id)
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT s.*, u.username AS owner_username, u.display_name AS owner_display_name
                    FROM solutions s
                    LEFT JOIN users u ON u.id = s.user_id
                    WHERE s.id = %s {access_sql}
                    """,
                    tuple(params),
                )
                row = cursor.fetchone()
        return _solution_payload(row) if row else None

    def get_solution_image_path(self, solution_id: str, user_id: Optional[int] = None) -> Optional[str]:
        solution = self.get_solution(solution_id, user_id=user_id, require_access=user_id is not None)
        if not solution or not solution.get("image_url"):
            return None
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT image_path FROM solutions WHERE id = %s", (solution_id,))
                row = cursor.fetchone()
        return row["image_path"] if row else None

    def save_user_solution(
        self,
        user_id: int,
        problem_id: str,
        title: str,
        solution_id: Optional[str] = None,
        image_path: Optional[str] = None,
        canvas_data: Optional[Dict[str, Any]] = None,
        save_as: bool = False,
        parent_solution_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.get_problem(problem_id):
            raise ValueError("Problem not found")

        existing = None
        parent_solution = None
        if solution_id:
            requested_solution = self.get_solution(solution_id, user_id=user_id)
            if not requested_solution or requested_solution.get("user_id") != user_id:
                raise ValueError("Solution not found")
            if requested_solution.get("problem_id") != problem_id:
                raise ValueError("Solution problem mismatch")
            if save_as:
                parent_solution = requested_solution
            else:
                if requested_solution.get("solution_type") != "draft":
                    raise ValueError("Only draft solutions can be updated")
                existing = requested_solution

        if parent_solution_id:
            parent_solution = self.get_solution(parent_solution_id, user_id=user_id)
            if not parent_solution or parent_solution.get("problem_id") != problem_id:
                raise ValueError("Branch source not found")

        if save_as or not existing:
            solution_id = f"user_{user_id}_{problem_id}_{uuid.uuid4().hex[:12]}"
        else:
            solution_id = existing["id"]

        with get_connection() as conn:
            with conn.cursor() as cursor:
                if existing:
                    cursor.execute(
                        """
                        UPDATE solutions
                        SET title = %s,
                            image_path = COALESCE(%s, image_path),
                            canvas_data = %s,
                            solution_type = 'draft',
                            parent_solution_id = COALESCE(parent_solution_id, %s),
                            progress_slot = NULL,
                            grading_steps = NULL,
                            grading_result = NULL,
                            points_taken = NULL,
                            major_points = NULL,
                            minor_points = NULL,
                            graded_at = NULL,
                            source_kind = 'user'
                        WHERE id = %s AND user_id = %s
                        """,
                        (
                            title,
                            image_path,
                            _json_or_none(canvas_data),
                            parent_solution["id"] if parent_solution else None,
                            solution_id,
                            user_id,
                        ),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO solutions
                          (id, problem_id, user_id, title, image_path, canvas_data, solution_type, parent_solution_id, progress_slot, source_kind, is_public)
                        VALUES (%s, %s, %s, %s, %s, %s, 'draft', %s, NULL, 'user', FALSE)
                        """,
                        (
                            solution_id,
                            problem_id,
                            user_id,
                            title,
                            image_path,
                            _json_or_none(canvas_data),
                            parent_solution["id"] if parent_solution else None,
                        ),
                    )
                cursor.execute(
                    """
                    INSERT INTO solution_events
                      (solution_id, problem_id, user_id, event_type, payload, image_path)
                    VALUES (%s, %s, %s, 'save', %s, %s)
                    """,
                    (
                        solution_id,
                        problem_id,
                        user_id,
                        _json_or_none({
                            "title": title,
                            "has_canvas_data": bool(canvas_data),
                            "solution_type": "draft",
                            "save_as": bool(save_as),
                            "parent_solution_id": parent_solution["id"] if parent_solution else None,
                        }),
                        image_path,
                    ),
                )

        solution = self.get_solution(solution_id, user_id=user_id)
        if not solution:
            raise ValueError("Solution save failed")
        return solution

    def mark_solution_graded(
        self,
        draft_solution_id: str,
        user_id: int,
        image_path: str,
        grading_result: Dict[str, Any],
        grading_steps: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        existing = self.get_solution(draft_solution_id, user_id=user_id)
        if not existing:
            raise ValueError("Draft solution not found")
        if existing.get("solution_type") != "draft":
            raise ValueError("Only draft solutions can be submitted for grading")
        if not image_path:
            raise ValueError("Final solution image is required for grading")
        points_taken = _points_taken_details(grading_result)
        score_summary = _score_summary(grading_result)
        final_solution_id = f"user_{user_id}_{existing['problem_id']}_{uuid.uuid4().hex[:12]}"
        final_title = f"{existing['title']} (Final {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC)"

        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO solutions
                      (
                        id, problem_id, user_id, title, image_path, canvas_data,
                        solution_type, parent_solution_id, progress_slot,
                        grading_steps, grading_result, points_taken, major_points, minor_points, graded_at,
                        source_kind, is_public
                      )
                    VALUES (%s, %s, %s, %s, %s, %s, 'graded', %s, NULL, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, 'user', FALSE)
                    """,
                    (
                        final_solution_id,
                        existing["problem_id"],
                        user_id,
                        final_title,
                        image_path,
                        _json_or_none(existing.get("canvas_data")),
                        draft_solution_id,
                        _json_or_none(grading_steps),
                        _json_or_none(grading_result),
                        _json_or_none(points_taken),
                        _json_or_none(points_taken["major"]),
                        _json_or_none(points_taken["minor"]),
                    ),
                )
                cursor.execute(
                    """
                    INSERT INTO solution_events
                      (solution_id, problem_id, user_id, event_type, payload, image_path)
                    VALUES (%s, %s, %s, 'grade', %s, %s)
                    """,
                    (
                        final_solution_id,
                        existing["problem_id"],
                        user_id,
                        _json_or_none({
                            "score": score_summary["score"],
                            "max_score": score_summary["max_score"],
                            "grading_steps": grading_steps,
                            "points_taken": points_taken,
                            "draft_solution_id": draft_solution_id,
                        }),
                        image_path,
                    ),
                )

        solution = self.get_solution(final_solution_id, user_id=user_id)
        if not solution:
            raise ValueError("Grading save failed")
        return solution
