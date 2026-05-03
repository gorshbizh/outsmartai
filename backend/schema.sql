CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(80) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  display_name VARCHAR(120) NOT NULL,
  email VARCHAR(255) NULL UNIQUE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS problems (
  id VARCHAR(80) PRIMARY KEY,
  title VARCHAR(255) NOT NULL,
  prompt TEXT NULL,
  category VARCHAR(80) NULL,
  difficulty VARCHAR(40) NULL,
  image_path VARCHAR(500) NOT NULL,
  source VARCHAR(120) NOT NULL DEFAULT 'backend_tests',
  sort_order INT NOT NULL DEFAULT 0,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_problems_active_sort (active, sort_order, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS solutions (
  id VARCHAR(120) PRIMARY KEY,
  problem_id VARCHAR(80) NOT NULL,
  user_id INT NULL,
  title VARCHAR(255) NOT NULL,
  image_path VARCHAR(500) NULL,
  canvas_data JSON NULL,
  solution_type ENUM('draft', 'graded') NOT NULL DEFAULT 'draft',
  parent_solution_id VARCHAR(120) NULL,
  progress_slot TINYINT NULL,
  grading_steps JSON NULL,
  grading_result JSON NULL,
  points_taken JSON NULL,
  major_points JSON NULL,
  minor_points JSON NULL,
  graded_at TIMESTAMP NULL,
  source_kind ENUM('seed', 'user') NOT NULL DEFAULT 'user',
  is_public BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_solutions_problem FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE CASCADE,
  CONSTRAINT fk_solutions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
  CONSTRAINT fk_solutions_parent FOREIGN KEY (parent_solution_id) REFERENCES solutions(id) ON DELETE SET NULL,
  INDEX idx_solutions_problem_type (problem_id, solution_type, updated_at),
  INDEX idx_solutions_user_problem (user_id, problem_id, updated_at),
  INDEX idx_solutions_user_problem_type_time (user_id, problem_id, solution_type, updated_at, id),
  INDEX idx_solutions_parent_time (parent_solution_id, created_at),
  INDEX idx_solutions_progress_slot (user_id, problem_id, progress_slot)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS solution_events (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  solution_id VARCHAR(120) NULL,
  problem_id VARCHAR(80) NOT NULL,
  user_id INT NULL,
  event_type VARCHAR(40) NOT NULL,
  payload JSON NULL,
  image_path VARCHAR(500) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_solution_events_solution FOREIGN KEY (solution_id) REFERENCES solutions(id) ON DELETE SET NULL,
  CONSTRAINT fk_solution_events_problem FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE CASCADE,
  CONSTRAINT fk_solution_events_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
  INDEX idx_solution_events_solution_time (solution_id, created_at),
  INDEX idx_solution_events_user_problem_time (user_id, problem_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
