import json
import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from .agent import run
from .history import History
from .models import RunRequest, RunResult
from .store import ROOT

load_dotenv(ROOT / ".env", override=False)


def create_app(history_path=None):
    app = FastAPI(title="Sunrise Front Desk", version="1.0.0")
    history = History(history_path or os.getenv("UI_DB_PATH", str(ROOT / "workbench.sqlite3")))
    app.state.history = history

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        # Payload bounds complement strict per-field limits. No model key or
        # raw provider errors ever appear in responses.
        try:
            if int(request.headers.get("content-length", "0")) > 160000:
                from fastapi.responses import JSONResponse

                return JSONResponse({"detail": "Request exceeds 160000 bytes"}, status_code=413)
        except ValueError:
            raise HTTPException(400, "Invalid content-length") from None
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "storage": "sqlite",
            "evaluation_isolation": True,
            "model_enabled": os.getenv("GEMINI_ENABLED", "false").lower() == "true",
        }

    @app.post("/agent/run", response_model=RunResult)
    def evaluation(payload: RunRequest):
        detail = run(payload)
        history.add(payload, detail)
        return detail["result"]

    @app.post("/api/run")
    def interactive(payload: RunRequest):
        detail = run(payload)
        run_id = history.add(payload, detail)
        return {"run_id": run_id, **detail}

    @app.get("/api/runs")
    def runs():
        records = history.list()
        return {
            "runs": records,
            "counters": {
                "total": len(records),
                "completed": sum(r["terminal_state"] in ["booked", "cancelled", "rescheduled"] for r in records),
                "escalated": sum(r["terminal_state"] == "escalated" for r in records),
                "urgent": sum(r["escalation_reason"] == "clinical_urgent" and not r["resolved"] for r in records),
                "open": sum(r["terminal_state"] == "escalated" and not r["resolved"] for r in records),
            },
        }

    @app.get("/api/runs/{run_id}")
    def detail(run_id: str):
        record = history.get(run_id)
        if not record:
            raise HTTPException(404, "Conversation run not found")
        return record

    @app.post("/api/runs/{run_id}/resolve")
    def resolve(run_id: str):
        if not history.resolve(run_id):
            raise HTTPException(404, "Open or resolved handoff not found")
        return {"resolved": True}

    @app.get("/api/samples")
    def samples():
        return [
            json.loads(p.read_text(encoding="utf-8"))
            for directory in ["conversations", "adversarial"]
            for p in sorted((ROOT / directory).glob("*.json"))
        ]

    dist = ROOT / "frontend" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/")
        def index():
            return FileResponse(dist / "index.html")

    return app


app = create_app()
