import express from 'express';
import http from 'http';
import https from 'https';
import path from 'path';
import { URL } from 'url';

const app = express();
const PORT = process.env.PORT || 3000;
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:5055';
const whiteboardDir = path.join(__dirname, '../whiteboard');

function proxyToBackend(req: express.Request, res: express.Response): void {
  const target = new URL(req.originalUrl, BACKEND_URL);
  const transport = target.protocol === 'https:' ? https : http;
  const headers = {
    ...req.headers,
    host: target.host,
  };

  const proxyReq = transport.request(
    {
      protocol: target.protocol,
      hostname: target.hostname,
      port: target.port,
      method: req.method,
      path: `${target.pathname}${target.search}`,
      headers,
    },
    proxyRes => {
      res.statusCode = proxyRes.statusCode || 500;
      Object.entries(proxyRes.headers).forEach(([key, value]) => {
        if (value !== undefined) {
          res.setHeader(key, value);
        }
      });
      proxyRes.pipe(res);
    }
  );

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
app.use(express.static(whiteboardDir));

app.get('/', (_req, res) => {
  res.sendFile(path.join(whiteboardDir, 'index.html'));
});

app.listen(PORT, () => {
  console.log(`OutSmartAI frontend available at http://localhost:${PORT}`);
  console.log(`Proxying API requests to ${BACKEND_URL}`);
});

export default app;
