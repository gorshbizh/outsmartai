"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const express_1 = __importDefault(require("express"));
const multer_1 = __importDefault(require("multer"));
const cors_1 = __importDefault(require("cors"));
const path_1 = __importDefault(require("path"));
const fs_1 = __importDefault(require("fs"));
const axios_1 = __importDefault(require("axios"));
const app = (0, express_1.default)();
const PORT = process.env.PORT || 3000;
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:5000';
// Middleware
app.use((0, cors_1.default)());
app.use(express_1.default.json({ limit: '10mb' }));
app.use(express_1.default.urlencoded({ extended: true, limit: '10mb' }));
// Serve static files from whiteboard directory
app.use(express_1.default.static(path_1.default.join(__dirname, '../whiteboard')));
// Configure multer for file uploads
const storage = multer_1.default.memoryStorage();
const upload = (0, multer_1.default)({
    storage: storage,
    limits: { fileSize: 10 * 1024 * 1024 } // 10MB limit
});
// Create uploads directory if it doesn't exist
const uploadsDir = path_1.default.join(__dirname, '../uploads');
if (!fs_1.default.existsSync(uploadsDir)) {
    fs_1.default.mkdirSync(uploadsDir, { recursive: true });
}
// Routes
app.get('/', (req, res) => {
    res.sendFile(path_1.default.join(__dirname, '../whiteboard', 'index.html'));
});
// Endpoint to receive whiteboard images
app.post('/api/process-image', upload.single('image'), async (req, res) => {
    try {
        if (!req.file) {
            return res.status(400).json({
                success: false,
                error: 'No image file provided',
                timestamp: new Date().toISOString()
            });
        }
        console.log('Received image for processing:', req.file.originalname);
        // Save the uploaded file temporarily
        const filename = `whiteboard-${Date.now()}.png`;
        const filepath = path_1.default.join(uploadsDir, filename);
        fs_1.default.writeFileSync(filepath, req.file.buffer);
        // Process with Python backend
        const analysisResult = await processWithBackend(req.file.buffer);
        // Clean up temporary file
        fs_1.default.unlinkSync(filepath);
        res.json({
            success: true,
            analysis: analysisResult,
            timestamp: new Date().toISOString()
        });
    }
    catch (error) {
        console.error('Error processing image:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to process image',
            timestamp: new Date().toISOString()
        });
    }
});
// Process image with Python backend
async function processWithBackend(imageBuffer) {
    try {
        // Convert buffer to base64 for JSON transport
        const base64Image = imageBuffer.toString('base64');
        const response = await axios_1.default.post(`${BACKEND_URL}/analyze`, {
            image: base64Image,
            format: 'png'
        }, {
            timeout: 30000, // 30 second timeout
            headers: {
                'Content-Type': 'application/json'
            }
        });
        return response.data;
    }
    catch (error) {
        console.error('Backend processing error:', error);
        // Fallback to mock response if backend is unavailable
        console.log('Backend unavailable, using mock response');
        return getMockResponse();
    }
}
function getMockResponse() {
    const responses = [
        {
            text_recognition: "MOCKED PYTHON BACKEND RETURN: Mathematical equations and formulas related to calculus",
            visual_elements: "Hand-drawn graphs, coordinate axes, and geometric shapes",
            content_analysis: "This appears to be study notes for a calculus course, showing derivative calculations and graphical representations",
            suggestions: [
                "Add more color coding to distinguish different concepts",
                "Include step-by-step solutions for better understanding",
                "Consider organizing formulas in a reference section"
            ],
            confidence: 0.85
        },
        {
            text_recognition: "MOCKED PYTHON BACKEND RETURN: Flowchart with decision points and process steps",
            visual_elements: "Rectangular boxes connected by arrows, diamond-shaped decision nodes",
            content_analysis: "A workflow diagram showing a business process or algorithm logic",
            suggestions: [
                "Add labels to clarify the purpose of each step",
                "Use consistent shapes for similar types of operations",
                "Consider adding a legend for different symbol meanings"
            ],
            confidence: 0.90
        },
        {
            text_recognition: "MOCKED PYTHON BACKEND RETURN: Project timeline with dates and milestones",
            visual_elements: "Horizontal timeline with markers and connecting lines",
            content_analysis: "Project planning document showing key deliverables and deadlines",
            suggestions: [
                "Add resource allocation information",
                "Include dependency relationships between tasks",
                "Consider using different colors for different project phases"
            ],
            confidence: 0.88
        }
    ];
    // Return a random response for variety
    return responses[Math.floor(Math.random() * responses.length)];
}
// Health check endpoint
app.get('/api/health', (req, res) => {
    res.json({
        status: 'OK',
        timestamp: new Date().toISOString(),
        backend_url: BACKEND_URL
    });
});
// Start server
app.listen(PORT, () => {
    console.log(`TypeScript server running on http://localhost:${PORT}`);
    console.log(`Whiteboard available at http://localhost:${PORT}`);
    console.log(`Backend URL: ${BACKEND_URL}`);
});
exports.default = app;
//# sourceMappingURL=server.js.map