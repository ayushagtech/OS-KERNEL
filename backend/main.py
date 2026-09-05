import os
import sys
import json
import logging
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from backend.daemon import guardian_daemon
from backend.simulator.stress_gen import workload_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("KernelGuardianServer")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# Safe Dynamic Import Check for FastAPI
try:
    import fastapi
    from fastapi import FastAPI, WebSocket
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

if HAS_FASTAPI:
    app = FastAPI(title="Agentic OS Kernel Guardian", version="1.0.0")

    if os.path.exists(FRONTEND_DIR):
        app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def get_dashboard():
        index_path = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.exists(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                return f.read()
        return "<h1>Agentic OS Kernel Guardian API Running</h1>"

    @app.get("/api/status")
    async def get_status():
        data = guardian_daemon.run_cycle()
        return JSONResponse(content=data)

    @app.post("/api/stress/memory")
    async def trigger_memory_stress(mb: int = 500):
        res = workload_manager.trigger_memory_leak(mb_to_allocate=mb)
        return JSONResponse(content=res)

    @app.post("/api/stress/cpu")
    async def trigger_cpu_stress(duration: int = 30):
        res = workload_manager.trigger_cpu_spike(duration_sec=duration)
        return JSONResponse(content=res)

    @app.post("/api/stress/stop")
    async def stop_stress():
        res = workload_manager.stop_all_stressors()
        return JSONResponse(content=res)

    @app.websocket("/ws/telemetry")
    async def websocket_telemetry(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                cycle_data = guardian_daemon.run_cycle()
                await websocket.send_json(cycle_data)
                await asyncio.sleep(1.0)
        except Exception:
            pass

# Native Standard Library HTTP Server Fallback (Zero External Dependencies)
class BuiltinGuardianHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ["/", "/index.html"]:
            index_path = os.path.join(FRONTEND_DIR, "index.html")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            if os.path.exists(index_path):
                with open(index_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.wfile.write(b"<h1>Agentic OS Kernel Guardian Dashboard</h1>")
        elif parsed.path.startswith("/static/"):
            rel_path = parsed.path.replace("/static/", "")
            file_path = os.path.join(FRONTEND_DIR, rel_path)
            if os.path.exists(file_path):
                self.send_response(200)
                if file_path.endswith(".css"):
                    self.send_header("Content-Type", "text/css")
                elif file_path.endswith(".js"):
                    self.send_header("Content-Type", "application/javascript")
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404)
        elif parsed.path == "/api/status":
            data = guardian_daemon.run_cycle()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        res = {}
        if parsed.path == "/api/stress/memory":
            res = workload_manager.trigger_memory_leak(500)
        elif parsed.path == "/api/stress/cpu":
            res = workload_manager.trigger_cpu_spike(30)
        elif parsed.path == "/api/stress/stop":
            res = workload_manager.stop_all_stressors()
        
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(res).encode("utf-8"))

    def log_message(self, format, *args):
        return

def start_app(host="127.0.0.1", port=5000):
    if HAS_FASTAPI:
        logger.info(f"Starting FastAPI + Uvicorn server on http://{host}:{port}")
        uvicorn.run("backend.main:app", host=host, port=port, reload=False)
    else:
        logger.info(f"FastAPI not detected. Starting Built-in Native HTTP Server on http://{host}:{port}")
        server = HTTPServer((host, port), BuiltinGuardianHandler)
        server.serve_forever()

if __name__ == "__main__":
    start_app()
