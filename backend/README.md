# Backend Server

Python Flask backend server for whiteboard image analysis using various LLM providers.

## Setup

### 1. Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment (macOS/Linux)
source .venv/bin/activate

# On Windows
# .venv\Scripts\activate
```

### 2. Install Dependencies

```bash
# Upgrade pip
pip install --upgrade pip

# Install requirements
pip install -i https://pypi.org/simple/ -r requirements.txt
```

### 3. Configure Environment

Create a `.env` file in the root directory (one level up from backend/) with:

```env
# LLM Configuration
LLM_PROVIDER=openai
LLM_API_KEY=your_api_key_here

# Server Configuration  
PORT=3000
BACKEND_PORT=5000
BACKEND_URL=http://localhost:5000
FLASK_DEBUG=False
```

**Supported LLM Providers:**
- `openai` - OpenAI GPT-4o (requires OpenAI API key)
- `anthropic` - Claude 3.5 Sonnet (requires Anthropic API key)
- `google` - Google Gemini (requires Google AI API key)
- `mock` - Mock responses for testing (no API key required)

## Running the Server

### Start the Backend

```bash
# Make sure virtual environment is activated
source .venv/bin/activate

# Start the server
python app.py
```

The server will start on `http://localhost:5000`

### Verify Server

Check if the server is running:

```bash
curl http://localhost:5000/health
```

Expected response:
```json
{
  "status": "OK",
  "timestamp": "2025-01-XX...",
  "provider": "openai",
  "has_api_key": true
}
```

## API Endpoints

### Health Check
- **GET** `/health`
- Returns server status and configuration

### Image Analysis
- **POST** `/analyze`
- Analyzes whiteboard images using configured LLM provider

**Request Body:**
```json
{
  "image": "base64_encoded_image_data"
}
```

**Response:**
```json
{
  "text_recognition": "Detected text content",
  "visual_elements": "Description of visual elements",
  "content_analysis": "Analysis and interpretation",
  "suggestions": ["Improvement suggestion 1", "Suggestion 2"],
  "confidence": 0.85
}
```

## Development

### Running Tests

Use the backend virtualenv (so dependencies like Pillow are available), then run tests from either location:

```bash
# From repo root:
backend/venv/Scripts/python.exe -m unittest discover -s backend/tests -p "test_*.py"

# Or from backend/:
# venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py"
```

To run the tests against a specific image, set `TEST_IMAGE_PATH` (or drop a file at `backend/tests/fixtures/test.png`).

To run a real (networked) LLM call as an integration test, also set `RUN_LLM_INTEGRATION=1` plus your `LLM_PROVIDER` and `LLM_API_KEY`.

### Project Structure

```
backend/
├── app.py              # Main Flask application
├── requirements.txt    # Python dependencies
├── tests/              # Unit tests (unittest)
├── .venv/             # Virtual environment (ignored by git)
└── README.md          # This file
```

### Adding New LLM Providers

1. Add provider configuration to the `LLMService` class
2. Implement `_analyze_with_newprovider()` method
3. Update the provider selection logic in `analyze_image()`
4. Add provider to the supported list in this README

### Error Handling

The server includes comprehensive error handling:
- Invalid image data
- API key issues
- Provider-specific errors
- Automatic fallback to mock responses

### Logging

Server logs include:
- Request processing timestamps
- API errors with details
- Fallback notifications

## Troubleshooting

### Common Issues

1. **ModuleNotFoundError**: Make sure virtual environment is activated and dependencies are installed
2. **API Key errors**: Check that your API key is correctly set in `.env`
3. **Model not found**: Ensure you're using supported model names for your provider
4. **Port conflicts**: Change `BACKEND_PORT` in `.env` if port 5000 is busy

### Virtual Environment Issues

If you encounter issues with the virtual environment:

```bash
# Remove and recreate
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Dependencies

Current dependencies include:
- Flask 2.3.2 (web framework)
- Flask-CORS 4.0.0 (CORS handling)
- OpenAI client (latest)
- Anthropic client (latest)
- Google Generative AI client
- Pillow 10.0.0 (image processing)
- python-dotenv 1.0.0 (environment variables)
