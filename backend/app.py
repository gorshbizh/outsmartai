#!/usr/bin/env python3

import os
import io
import base64
import random
import shutil
from datetime import datetime
from typing import Dict, List, Any, Optional
from flask import Flask, request, jsonify
from flask_cors import CORS
from PIL import Image
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuration
LLM_PROVIDER = os.getenv('LLM_PROVIDER', 'mock')
LLM_API_KEY = os.getenv('LLM_API_KEY')

class LLMService:
    def __init__(self):
        self.provider = LLM_PROVIDER
        self.api_key = LLM_API_KEY
        
    async def analyze_image(self, image_data: bytes) -> Dict[str, Any]:
        """Analyze image with configured LLM provider"""
        if not self.api_key or self.provider == 'mock':
            print("No API key provided or using mock provider, returning mock response")
            return self._get_mock_response()
        
        try:
            if self.provider == 'openai':
                return await self._analyze_with_openai(image_data)
            elif self.provider == 'anthropic':
                return await self._analyze_with_anthropic(image_data)
            elif self.provider == 'google':
                return await self._analyze_with_google(image_data)
            else:
                raise ValueError(f"Unsupported LLM provider: {self.provider}")
                
        except Exception as e:
            print(f"LLM API error: {e}")
            print("Falling back to mock response")
            return self._get_mock_response()
    
    async def _analyze_with_openai(self, image_data: bytes) -> Dict[str, Any]:
        """Analyze image using OpenAI GPT-4 Vision"""
        try:
            # Detect image format
            image_format = self._detect_image_format(image_data)
            base64_image = base64.b64encode(image_data).decode('utf-8')
            # debugging purposes
            # print(f"Image format: {image_format}")
            # print(f"Base64 image: {base64_image}")
            # save base64_image to a file
            # with open('se_image.txt', 'w') as f:
            #     f.write(base64_image)
            from openai import OpenAI
            # Initialize client with explicit parameters
            client = OpenAI(
                api_key=self.api_key,
                timeout=30.0
            )
            
            response = client.chat.completions.create(
                model="gpt-4o",  # Using gpt-4o as it's the latest available vision model
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful math teacher that can read text from images created from hand written notes and analyze diagrams to understand the content of the notes."
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Analyze this whiteboard image carefully. Please provide detailed text recognition of ALL written content you can see, including handwritten text, printed text, numbers, symbols, and equations. Also describe visual elements like diagrams, shapes, arrows, and drawings. Format as JSON with: text_recognition (string with all text found), visual_elements (string), content_analysis (string), suggestions (array), confidence (0-1)."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/{image_format};base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=1500,
                temperature=0.1
            )
            
            content = response.choices[0].message.content
            return self._parse_response(content)
            
        except ImportError:
            raise Exception("OpenAI library not installed. Run: pip install openai>=1.12.0")
        except Exception as e:
            print(f"OpenAI API error details: {str(e)}")
            # Log more details about the error for debugging
            if hasattr(e, 'response'):
                print(f"API response status: {getattr(e.response, 'status_code', 'N/A')}")
                print(f"API response body: {getattr(e.response, 'text', 'N/A')}")
            raise Exception(f"OpenAI API error: {str(e)}")
    
    async def _analyze_with_anthropic(self, image_data: bytes) -> Dict[str, Any]:
        """Analyze image using Anthropic Claude"""
        try:
            import anthropic
            
            client = anthropic.Anthropic(api_key=self.api_key)
            base64_image = base64.b64encode(image_data).decode('utf-8')
            
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",  # Updated to latest model
                max_tokens=1000,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": base64_image
                                }
                            },
                            {
                                "type": "text",
                                "text": "Please analyze this whiteboard drawing and provide: 1) Text recognition of any written content, 2) Description of visual elements (diagrams, shapes, arrows), 3) Content analysis and interpretation, 4) Suggestions for improvement or organization. Format your response as JSON with keys: text_recognition, visual_elements, content_analysis, suggestions (array), confidence (0-1)."
                            }
                        ]
                    }
                ]
            )
            
            content = response.content[0].text
            return self._parse_response(content)
            
        except ImportError:
            raise Exception("Anthropic library not installed. Run: pip install anthropic>=0.18.0")
        except Exception as e:
            raise Exception(f"Anthropic API error: {str(e)}")
    
    async def _analyze_with_google(self, image_data: bytes) -> Dict[str, Any]:
        """Analyze image using Google Gemini"""
        import google.generativeai as genai
        
        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel('gemini-pro-vision')
        
        # Convert bytes to PIL Image
        image = Image.open(io.BytesIO(image_data))
        
        prompt = """Please analyze this whiteboard drawing and provide: 
        1) Text recognition of any written content
        2) Description of visual elements (diagrams, shapes, arrows)
        3) Content analysis and interpretation
        4) Suggestions for improvement or organization
        
        Format your response as JSON with keys: text_recognition, visual_elements, content_analysis, suggestions (array), confidence (0-1)."""
        
        response = model.generate_content([prompt, image])
        return self._parse_response(response.text)
    
    def _detect_image_format(self, image_data: bytes) -> str:
        """Detect image format from image data"""
        # Check magic bytes to determine format
        if image_data.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'png'
        elif image_data.startswith(b'RIFF') and b'WEBP' in image_data[:12]:
            return 'webp'
        elif image_data.startswith(b'GIF87a') or image_data.startswith(b'GIF89a'):
            return 'gif'
        else:
            # Default to png if format cannot be determined
            return 'png'
    
    def _parse_response(self, content: str) -> Dict[str, Any]:
        """Parse LLM response into structured format"""
        import json
        
        try:
            # Try to parse as JSON first
            return json.loads(content)
        except json.JSONDecodeError:
            # If not valid JSON, create structured response from text
            return {
                "text_recognition": self._extract_section(content, 'text'),
                "visual_elements": self._extract_section(content, 'visual'),
                "content_analysis": self._extract_section(content, 'analysis'),
                "suggestions": self._extract_suggestions(content),
                "confidence": 0.8,
                "raw_response": content
            }
    
    def _extract_section(self, content: str, section_type: str) -> str:
        """Extract specific section from text response"""
        lines = content.split('\n')
        relevant_lines = []
        
        for line in lines:
            lower_line = line.lower()
            if section_type == 'text' and any(keyword in lower_line for keyword in ['text', 'written', 'words']):
                relevant_lines.append(line)
            elif section_type == 'visual' and any(keyword in lower_line for keyword in ['visual', 'diagram', 'shape']):
                relevant_lines.append(line)
            elif section_type == 'analysis' and any(keyword in lower_line for keyword in ['analysis', 'interpretation', 'meaning']):
                relevant_lines.append(line)
        
        return ' '.join(relevant_lines).strip() or f"No {section_type} content identified"
    
    def _extract_suggestions(self, content: str) -> List[str]:
        """Extract suggestions from text response"""
        lines = content.split('\n')
        suggestions = []
        
        for line in lines:
            if any(keyword in line.lower() for keyword in ['suggest', 'recommend', 'improve']) or \
               line.strip().startswith(('-', '•', '*')):
                suggestions.append(line.strip())
        
        return suggestions if suggestions else ['Consider adding more details to clarify the content']
    
    def _get_mock_response(self) -> Dict[str, Any]:
        """Generate mock analysis response"""
        responses = [
            {
                "text_recognition": "MOCKED LLM RETURN: Mathematical equations and formulas related to calculus",
                "visual_elements": "Hand-drawn graphs, coordinate axes, and geometric shapes",
                "content_analysis": "This appears to be study notes for a calculus course, showing derivative calculations and graphical representations",
                "suggestions": [
                    "Add more color coding to distinguish different concepts",
                    "Include step-by-step solutions for better understanding",
                    "Consider organizing formulas in a reference section"
                ],
                "confidence": 0.85
            },
            {
                "text_recognition": "MOCKED LLM RETURN: Flowchart with decision points and process steps",
                "visual_elements": "Rectangular boxes connected by arrows, diamond-shaped decision nodes",
                "content_analysis": "A workflow diagram showing a business process or algorithm logic",
                "suggestions": [
                    "Add labels to clarify the purpose of each step",
                    "Use consistent shapes for similar types of operations",
                    "Consider adding a legend for different symbol meanings"
                ],
                "confidence": 0.90
            },
            {
                "text_recognition": "MOCKED LLM RETURN: Project timeline with dates and milestones",
                "visual_elements": "Horizontal timeline with markers and connecting lines",
                "content_analysis": "Project planning document showing key deliverables and deadlines",
                "suggestions": [
                    "Add resource allocation information",
                    "Include dependency relationships between tasks",
                    "Consider using different colors for different project phases"
                ],
                "confidence": 0.88
            }
        ]
        
        return random.choice(responses)

# Initialize LLM service
llm_service = LLMService()

# Backup functionality
BACKUP_DIR = os.getenv('BACKUP_DIR', 'backups/images')

def ensure_backup_directory():
    """Ensure backup directory exists"""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR, exist_ok=True)

def save_image_backup(image_data: bytes, filename_prefix: str = "backup") -> str:
    """Save image backup and return the backup file path"""
    ensure_backup_directory()
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]  # milliseconds
    backup_filename = f"{filename_prefix}_{timestamp}.png"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)
    
    with open(backup_path, 'wb') as f:
        f.write(image_data)
    
    print(f"Image backup saved: {backup_path}")
    return backup_path

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'OK',
        'timestamp': datetime.now().isoformat(),
        'provider': LLM_PROVIDER,
        'has_api_key': bool(LLM_API_KEY)
    })

@app.route('/analyze', methods=['POST'])
def analyze_image():
    """Analyze whiteboard image"""
    try:
        data = request.get_json()
        
        if not data or 'image' not in data:
            return jsonify({
                'error': 'No image data provided'
            }), 400
        
        # Decode base64 image
        try:
            image_data = base64.b64decode(data['image'])
            # Debug: save the uploaded image for inspection
            os.makedirs("uploads", exist_ok=True)
            debug_path = os.path.join("uploads", "debug_latest.png")
            with open(debug_path, "wb") as f:
                f.write(image_data)
            print(f"Saved debug image to {debug_path}")
        except Exception as e:
            return jsonify({
                'error': f'Invalid base64 image data: {str(e)}'
            }), 400
        
        # Validate image
        try:
            image = Image.open(io.BytesIO(image_data))
            image.verify()  # Verify it's a valid image
        except Exception as e:
            return jsonify({
                'error': f'Invalid image format: {str(e)}'
            }), 400
        
        # Save backup of the image before processing
        backup_path = save_image_backup(image_data, "analyzed_image")
        
        print(f"Processing image analysis request at {datetime.now()}")
        print(f"Image backup saved to: {backup_path}")
        
        # Process with LLM (note: using sync call since Flask doesn't support async by default)
        # For production, consider using Flask with async support or Celery for async processing
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(llm_service.analyze_image(image_data))
        finally:
            loop.close()
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error processing image: {e}")
        return jsonify({
            'error': f'Internal server error: {str(e)}'
        }), 500

@app.route('/api/process-image', methods=['POST'])
def process_image():
    """Process image file for AI analysis"""
    try:
        # Check if image file is in the request
        if 'image' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No image file provided'
            }), 400
        
        image_file = request.files['image']
        
        if image_file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No image file selected'
            }), 400
        
        # Read image data
        image_data = image_file.read()
        
        # Validate image
        try:
            image = Image.open(io.BytesIO(image_data))
            image.verify()  # Verify it's a valid image
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Invalid image format: {str(e)}'
            }), 400
        
        # Save backup of the image before processing
        backup_path = save_image_backup(image_data, "analyzed_image")
        
        print(f"Processing image analysis request at {datetime.now()}")
        print(f"Image backup saved to: {backup_path}")
        
        # Process with LLM
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(llm_service.analyze_image(image_data))
        finally:
            loop.close()
        
        return jsonify({
            'success': True,
            'analysis': result
        })
        
    except Exception as e:
        print(f"Error processing image: {e}")
        return jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }), 500

@app.route('/api/backup-image', methods=['POST'])
def backup_image():
    """Save image backup"""
    try:
        # Check if image file is in the request
        if 'image' not in request.files:
            return jsonify({
                'error': 'No image file provided'
            }), 400
        
        image_file = request.files['image']
        backup_type = request.form.get('backup_type', 'general')
        
        if image_file.filename == '':
            return jsonify({
                'error': 'No image file selected'
            }), 400
        
        # Read image data
        image_data = image_file.read()
        
        # Validate image
        try:
            image = Image.open(io.BytesIO(image_data))
            image.verify()  # Verify it's a valid image
        except Exception as e:
            return jsonify({
                'error': f'Invalid image format: {str(e)}'
            }), 400
        
        # Save backup
        backup_path = save_image_backup(image_data, backup_type)
        
        return jsonify({
            'success': True,
            'backup_path': backup_path,
            'message': 'Image backup saved successfully'
        })
        
    except Exception as e:
        print(f"Error saving image backup: {e}")
        return jsonify({
            'error': f'Internal server error: {str(e)}'
        }), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.getenv('BACKEND_PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    print(f"Starting Python backend server on port {port}")
    print(f"LLM Provider: {LLM_PROVIDER}")
    print(f"Has API Key: {bool(LLM_API_KEY)}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)