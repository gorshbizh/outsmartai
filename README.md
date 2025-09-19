# OutSmartAI Whiteboard

An intelligent whiteboard application that allows users to draw, write, and get AI-powered analysis of their content.

## Features

- **Interactive Whiteboard**: Draw with pen/eraser tools, adjustable colors and sizes
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

### 3. Start the Servers

**Option A: Use the convenience script (recommended for development):**
```bash
./start-dev.sh
```

**Option B: Start servers manually:**

Terminal 1 (Backend):
```bash
cd backend
source .venv/bin/activate
python app.py
```

Terminal 2 (Frontend):
```bash
npm run build
npm start
```

### 4. Open the Application

Navigate to `http://localhost:3000` in your browser.

## Usage

1. **Draw**: Use the pen tool to draw on the whiteboard
2. **Customize**: Adjust pen color, size, and background color
3. **Analyze**: Click "Analyze with AI" to get AI-powered insights
4. **Export**: Save your work as PNG or SVG files

## API Endpoints

**Frontend Server (TypeScript/Express):**
- `GET /` - Serves the whiteboard application
- `POST /api/process-image` - Receives images and forwards to backend
- `GET /api/health` - Health check endpoint

**Backend Server (Python/Flask):**
- `POST /analyze` - Analyzes images with LLM
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
│   ├── index.html      # Main HTML file
│   ├── styles.css      # Styling
│   └── app.js         # JavaScript logic
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

## License

MIT License - see LICENSE file for details.
