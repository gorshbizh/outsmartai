#!/usr/bin/env python3
"""
Test script for OpenAI vision API integration
"""

import base64
import requests
import json
from PIL import Image, ImageDraw, ImageFont
import io

def create_test_image():
    """Create a simple test image with text"""
    # Create a white image
    img = Image.new('RGB', (800, 600), color='white')
    draw = ImageDraw.Draw(img)
    
    # Try to use a default font, fallback to basic font
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 40)
    except:
        font = ImageFont.load_default()
    
    # Add some text
    draw.text((50, 50), "Hello World!", fill='black', font=font)
    draw.text((50, 120), "This is a test image", fill='blue', font=font)
    draw.text((50, 190), "Math: 2 + 2 = 4", fill='red', font=font)
    
    # Add some shapes
    draw.rectangle([50, 250, 200, 350], outline='green', width=3)
    draw.ellipse([250, 250, 400, 350], outline='purple', width=3)
    draw.line([50, 400, 400, 450], fill='orange', width=5)
    
    # Save to bytes
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    return img_bytes.getvalue()

def test_local_api():
    """Test the local Flask API"""
    # Create test image
    image_data = create_test_image()
    base64_image = base64.b64encode(image_data).decode('utf-8')
    
    # Test API
    url = "http://localhost:5000/analyze"
    payload = {
        "image": base64_image
    }
    
    try:
        response = requests.post(url, json=payload, timeout=60)
        if response.status_code == 200:
            result = response.json()
            print("✅ API call successful!")
            print(f"Text Recognition: {result.get('text_recognition', 'N/A')}")
            print(f"Visual Elements: {result.get('visual_elements', 'N/A')}")
            print(f"Confidence: {result.get('confidence', 'N/A')}")
        else:
            print(f"❌ API call failed with status {response.status_code}")
            print(f"Response: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Connection error: {e}")
        print("Make sure your Flask server is running on port 5000")

if __name__ == "__main__":
    print("Creating test image with text and shapes...")
    test_local_api()
