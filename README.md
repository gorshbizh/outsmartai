# OutSmartAI Whiteboard

An intelligent whiteboard application that allows users to draw, write, and get AI-powered analysis of their content.

## Features

- **Interactive Whiteboard**: Draw with pen/eraser tools, adjustable colors and sizes
- **Formal User Flow**: Login, home, user info, rolling progress list, and problem/solution launch into the whiteboard
- **MySQL-backed Progress**: Each user can keep multiple drafts per problem, branch with Save As Draft, and finalize each draft once with grading
- **AI Analysis**: Send drawings to LLM for content recognition and analysis
- **Multiple Export Formats**: Save as PNG or SVG
- **Responsive Design**: Works on desktop, tablet, and mobile devices
- **Real-time Processing**: Get instant AI feedback on your drawings

## Setup Instructions

### 1. Install Dependencies

**Frontend (TypeScript):**
```bash
npm install
```

**Backend (Python):**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd ..
```

### 2. Configure LLM Provider (Optional)

Copy the example environment file:
```bash
cp .env.example .env
```

Edit `.env` and add your API key for your preferred LLM provider:

**For OpenAI GPT-4 Vision:**
```env
LLM_PROVIDER=openai
LLM_API_KEY=your_openai_api_key_here
```

**For Anthropic Claude:**
```env
LLM_PROVIDER=anthropic
LLM_API_KEY=your_anthropic_api_key_here
```

**For Google Gemini:**
```env
LLM_PROVIDER=google
LLM_API_KEY=your_google_api_key_here
```

> **Note**: If no API key is provided, the application will use mock responses for testing.

Add MySQL settings to `.env` as needed:

```env
PORT=3000
BACKEND_PORT=5055
BACKEND_URL=http://localhost:5055
ENABLE_FORMALGEO=False

MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=outsmartai
MYSQL_PASSWORD=outsmartai_dev_password
MYSQL_DATABASE=outsmartai
MYSQL_ROOT_PASSWORD=outsmartai_dev_root
DB_AUTO_INIT=True
DB_AUTO_SEED=True
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin1234
ADMIN_DISPLAY_NAME="Admin User"
ADMIN_EMAIL=
```

For a fresh environment, the first successful MySQL/bootstrap run should use:

```env
DB_AUTO_INIT=True
DB_AUTO_SEED=True
```

That creates the schema and inserts the seeded admin user plus demo problem data. After the first successful login, switch to regular mode:

```env
DB_AUTO_SEED=False
```

That keeps the existing MySQL data and avoids reseeding on every backend restart.

The backend defaults to port `5055` because macOS AirPlay Receiver often occupies port `5000` and returns `403 Forbidden` responses. If login shows `Request failed with 403`, make sure the frontend `BACKEND_URL` is not pointing at `http://localhost:5000`.

### 3. Start MySQL Locally

The recommended local setup is Docker Compose. It mirrors the way production will later point the same app at a managed MySQL service such as Cloud SQL or RDS.

```bash
docker-compose up -d mysql
docker-compose ps
```

Expected status:

```text
outsmartai-mysql   mysql:8.0   Up ... (healthy)   0.0.0.0:3306->3306/tcp
```

If Docker reports a socket permission problem on macOS, confirm `/var/run/docker.sock` points at your current user:

```bash
whoami
ls -l /var/run/docker.sock
docker ps
```

For this repo, the socket should resolve under your home directory, for example `/Users/diyu/.docker/run/docker.sock`. If it points at another macOS user, start Docker Desktop as your user or create your own runtime with Colima:

```bash
brew install colima
colima start --cpu 4 --memory 4 --disk 20
docker context use colima
docker-compose up -d mysql
```

To reset local MySQL data completely:

```bash
docker-compose down -v
docker-compose up -d mysql
```

### 4. Initialize and Smoke-Test the Database

Flask initializes the schema and seeds test data on startup when `DB_AUTO_INIT=True` and `DB_AUTO_SEED=True`. You can verify it directly:

```bash
PYTHONPYCACHEPREFIX=/tmp/outsmartai_pycache backend/.venv/bin/python - <<'PY'
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(".env"))
from backend.db import initialize_database, seed_test_data, get_connection
initialize_database()
seeded = seed_test_data()
with get_connection() as conn:
    with conn.cursor() as cursor:
        for table in ["users", "problems", "solutions", "solution_events"]:
            cursor.execute(f"SELECT COUNT(*) AS count FROM {table}")
            print(f"{table}={cursor.fetchone()['count']}")
print(f"seeded={seeded}")
PY
```

Expected fresh output includes:

```text
users=1
problems=18
solutions=34
seeded={'problems': 18, 'solutions': 34}
```

The seeded admin account owns the test-data draft solutions. New users see all problems, but only their own draft and final history.

For the GCP single-VM deployment, the repo also includes:

- `scripts/bootstrap-vm-mysql.sh`: resets the Docker MySQL volume, enables seeding, and bootstraps the VM for first-time login
- `scripts/set-vm-regular-mode.sh`: flips `.env` back to `DB_AUTO_SEED=False` and restarts the backend

### 5. Start the Servers

**Option A: Use the convenience script (recommended for development):**
```bash
./start-dev.sh
```

**Option B: Start servers manually:**

Terminal 1 (Backend):
```bash
cd backend
source .venv/bin/activate
BACKEND_PORT=5055 python app.py
```

Terminal 2 (Frontend):
```bash
npm run build
BACKEND_URL=http://localhost:5055 npm start
```

### 6. Open the Application

Navigate to `http://localhost:3000` in your browser. The seeded admin account is `admin` / `admin1234` when `DB_AUTO_SEED=True`.

## Local E2E Checklist

Use this when you want to test the full local stack before pushing changes:

1. Start Docker MySQL:

```bash
docker-compose up -d mysql
docker-compose ps
```

2. Install dependencies:

```bash
npm install
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..
```

3. Build the frontend:

```bash
npm run build
```

4. Start backend and frontend in separate terminals:

```bash
cd backend
source .venv/bin/activate
BACKEND_PORT=5055 LLM_PROVIDER=mock python app.py
```

```bash
BACKEND_URL=http://localhost:5055 npm start
```

5. In the browser:

- Open `http://localhost:3000`.
- Login as `admin` / `admin1234` to see the seeded test drafts.
- Create a new user to verify a user-specific progress page.
- Open `progress`, click a problem, write on the problem image, and click **Save Progress**.
- Click **Save As Draft** to branch the current work into another draft.
- Click **Submit for Grading** on one draft. That draft should become final and open the grading dialog.
- Try grading the same final again. The backend should reject the second grading attempt.

For an API-level smoke test against Docker MySQL without using real LLM credits, run:

```bash
cd backend
LLM_PROVIDER=mock LLM_API_KEY= PYTHONPYCACHEPREFIX=/tmp/outsmartai_pycache .venv/bin/python - <<'PY'
import base64
import time
from pathlib import Path
import app

repo_root = Path("..").resolve()
client = app.app.test_client()
username = f"e2e_{int(time.time())}"

assert client.post("/api/auth/register", json={
    "username": username,
    "password": "password123",
    "display_name": "E2E User",
}).status_code == 200

progress = client.get("/api/progress?limit=3&offset=0")
assert progress.status_code == 200
problem = progress.json["items"][0]
assert problem["draft_solutions"] == []
assert problem["final_solutions"] == []

image_bytes = (repo_root / "backend/tests/data" / f"{problem['id']}.png").read_bytes()
image_data = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
saved = client.post("/api/solutions", json={
    "problem_id": problem["id"],
    "title": "E2E saved solution",
    "canvas_data": {"strokes": [], "text_boxes": [], "bg_color": "#ffffff"},
    "image_data": image_data,
})
assert saved.status_code == 200
solution_id = saved.json["solution"]["id"]

graded = client.post(f"/api/solutions/{solution_id}/grade", json={"grading_mode": "formalgeo"})
assert graded.status_code == 200
assert graded.json["solution"]["solution_type"] == "graded"

graded_again = client.post(f"/api/solutions/{solution_id}/grade", json={"grading_mode": "formalgeo"})
assert graded_again.status_code == 409

context = client.get(f"/api/whiteboard/context?problem_id={problem['id']}")
assert context.status_code == 200
assert any(item["id"] == solution_id for item in context.json["final_solutions"])
print("local e2e smoke passed")
PY
```

## Usage

1. **Login**: Sign in or create an account
2. **Open Progress**: Choose a problem, resume any draft, or open a past final solution
3. **Solve**: Work directly on the problem image inside the whiteboard, like an exam paper
4. **Save**: Click "Save Progress" to update the current draft
5. **Branch**: Click "Save As Draft" to create a new draft from the current draft or final solution
6. **Grade**: Click "Submit for Grading" once to finalize the current draft
7. **Analyze**: Click "Analyze with AI" for separate exploratory feedback

## API Endpoints

**Frontend Server (TypeScript/Express):**
- `GET /` - Serves the login page and static frontend assets
- `/api/*` - Proxies browser API calls to Flask

**Backend Server (Python/Flask):**
- `POST /api/auth/register` - Create a user
- `POST /api/auth/login` - Login with username/password
- `POST /api/auth/logout` - Logout
- `GET /api/auth/me` - Current user
- `GET /api/progress` - Rolling problem list with all of the user's drafts and final solutions per problem
- `GET /api/whiteboard/context` - Problem context plus the selected solution and other drafts/finals for that problem
- `POST /api/solutions` - Save a draft or branch the current work into a new draft with `save_as`
- `POST /api/solutions/:id/grade` - Finalize one draft with grading; final solutions are immutable
- `POST /analyze` - Analyzes images with LLM
- `POST /api/process-image` - Accepts whiteboard images for LLM analysis
- `GET /health` - Backend health check

## LLM Providers Supported

- **OpenAI** - GPT-4 Vision Preview
- **Anthropic** - Claude 3 Sonnet
- **Google** - Gemini Pro Vision

## Project Structure

```
├── src/
│   └── server.ts       # TypeScript Express server
├── backend/
│   ├── app.py          # Python Flask backend
│   └── requirements.txt # Python dependencies
├── dist/               # Compiled TypeScript
├── package.json        # Node.js dependencies and scripts
├── tsconfig.json       # TypeScript configuration
├── start-dev.sh        # Development startup script
├── whiteboard/         # Frontend application
│   ├── index.html      # Login page
│   ├── home.html       # Home page
│   ├── progress.html   # Rolling progress page
│   ├── user_info.html  # User profile page
│   ├── whiteboard.html # Whiteboard workspace
│   ├── styles.css      # Styling
│   ├── ux.js           # Login/home/progress/user-info logic
│   └── app.js          # Whiteboard logic
└── uploads/           # Temporary image storage
```

## Development

The application consists of:

1. **Frontend**: Vanilla JavaScript whiteboard application
2. **Web Server**: TypeScript/Express server for serving frontend and image handling
3. **Backend API**: Python/Flask server for LLM processing
4. **LLM Service**: Configurable AI analysis service in Python

## Deployment to GCP

For production deployment to Google Cloud Platform:

1. Update `app.yaml` with your configuration
2. Set environment variables in Cloud Console
3. Deploy with `gcloud app deploy`

For the current single-machine dev-stage deployment, use Docker on one Compute Engine VM instead. The repo now includes:

- `Dockerfile.frontend`
- `Dockerfile.backend`
- `docker-compose.prod.yml`
- `deploy-gcp-vm.sh`
- `.env.gcp.example`
- `docs/GCP_FREE_VM_DEPLOY.md`

That path keeps the whole stack on one VM with three containers: frontend, backend, and MySQL.

## Cloud Migration Notes

The local Docker MySQL setup uses the same environment variables that a public deployment should use. To move toward GCP or AWS:

- Use a managed MySQL database: **Cloud SQL for MySQL** on GCP or **Amazon RDS/Aurora MySQL** on AWS.
- Keep the application contract unchanged: set `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_DATABASE` from the cloud database connection details.
- Store secrets outside the repo: Secret Manager on GCP, Secrets Manager or SSM Parameter Store on AWS.
- Set `FLASK_SECRET_KEY` from a secret value and set `SESSION_COOKIE_SECURE=True` behind HTTPS.
- In production, set `DB_AUTO_SEED=False` so test images and the admin demo password are not automatically inserted.
- Keep `DB_AUTO_INIT=True` only for early deployments. Before public launch, move schema changes to a migration tool such as Alembic or Flyway.
- Store uploaded solution images outside the container filesystem before launch: GCS on GCP or S3 on AWS. Keep only metadata and object paths in MySQL.
- Run Flask behind a production WSGI server such as Gunicorn, and put Express/static assets behind a managed load balancer or CDN.
- Use separate environments and databases for local, staging, and production.

## License

MIT License - see LICENSE file for details.
