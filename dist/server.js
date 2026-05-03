"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const express_1 = __importDefault(require("express"));
const http_1 = __importDefault(require("http"));
const https_1 = __importDefault(require("https"));
const path_1 = __importDefault(require("path"));
const url_1 = require("url");
const app = (0, express_1.default)();
const PORT = process.env.PORT || 3000;
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:5055';
const whiteboardDir = path_1.default.join(__dirname, '../whiteboard');
function proxyToBackend(req, res) {
    const target = new url_1.URL(req.originalUrl, BACKEND_URL);
    const transport = target.protocol === 'https:' ? https_1.default : http_1.default;
    const headers = {
        ...req.headers,
        host: target.host,
    };
    const proxyReq = transport.request({
        protocol: target.protocol,
        hostname: target.hostname,
        port: target.port,
        method: req.method,
        path: `${target.pathname}${target.search}`,
        headers,
    }, proxyRes => {
        res.statusCode = proxyRes.statusCode || 500;
        Object.entries(proxyRes.headers).forEach(([key, value]) => {
            if (value !== undefined) {
                res.setHeader(key, value);
            }
        });
        proxyRes.pipe(res);
    });
    proxyReq.on('error', error => {
        console.error('Backend proxy error:', error);
        if (!res.headersSent) {
            res.status(502).json({
                success: false,
                error: 'Backend is unavailable',
                timestamp: new Date().toISOString(),
            });
        }
    });
    req.pipe(proxyReq);
}
app.use('/api', proxyToBackend);
app.use('/health', proxyToBackend);
app.use(express_1.default.static(whiteboardDir));
app.get('/', (_req, res) => {
    res.sendFile(path_1.default.join(whiteboardDir, 'index.html'));
});
app.listen(PORT, () => {
    console.log(`OutSmartAI frontend available at http://localhost:${PORT}`);
    console.log(`Proxying API requests to ${BACKEND_URL}`);
});
exports.default = app;
//# sourceMappingURL=server.js.map