from fastapi import FastAPI
from app.core import firebase  # triggers Firebase Admin init on startup
from app.api.auth import router as auth_router
from app.api.prayers import router as prayers_router
from app.api.calls import router as calls_router
from app.api.testimonies import router as testimonies_router
from app.api.gallery import router as gallery_router
from app.api.monthly_plans import router as monthly_plans_router
from app.api.media import router as media_router
from app.db.session import Base, engine
import app.models.testimony  # noqa: F401 — registers Testimony with Base.metadata
import app.models.call        # noqa: F401 — registers ScheduledCall, CallLog
import app.models.user        # noqa: F401 — registers User
import app.models.gallery     # noqa: F401 — registers GalleryItem
import app.models.monthly_plan # noqa: F401 — registers MonthlyPlan

# Ensure all tables are created
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"Table creation note (non-fatal): {e}")

# Run Alembic migrations programmatically on startup
import os
import sys
from alembic.config import Config
from alembic import command

from sqlalchemy import text

def run_migrations():
    try:
        print("Starting Alembic migrations...")
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # Append base_dir to sys.path so alembic can load modules properly
        if base_dir not in sys.path:
            sys.path.insert(0, base_dir)
        ini_path = os.path.join(base_dir, "alembic.ini")
        alembic_cfg = Config(ini_path)
        command.upgrade(alembic_cfg, "head")
        print("Alembic migrations completed successfully!")
    except Exception as e:
        print(f"Error during Alembic migration: {e}")

    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            migration_statements = [
                "ALTER TABLE scheduled_calls ADD COLUMN IF NOT EXISTS is_rung BOOLEAN DEFAULT FALSE;",
                "ALTER TABLE scheduled_calls ADD COLUMN IF NOT EXISTS meeting_code VARCHAR(64);",
                "ALTER TABLE scheduled_calls ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);",
                "ALTER TABLE scheduled_calls ADD COLUMN IF NOT EXISTS access_type VARCHAR(32) DEFAULT 'public';",
                "ALTER TABLE scheduled_calls ADD COLUMN IF NOT EXISTS status VARCHAR(32) DEFAULT 'active';",
                "ALTER TABLE scheduled_calls ADD COLUMN IF NOT EXISTS waiting_room_enabled BOOLEAN DEFAULT FALSE;",
                "ALTER TABLE scheduled_calls ADD COLUMN IF NOT EXISTS chat_enabled BOOLEAN DEFAULT TRUE;",
                "ALTER TABLE scheduled_calls ADD COLUMN IF NOT EXISTS screen_share_enabled BOOLEAN DEFAULT TRUE;",
                "ALTER TABLE scheduled_calls ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ;",
            ]
            for stmt in migration_statements:
                try:
                    conn.execute(text(stmt))
                except Exception as stmt_err:
                    print(f"Schema migration statement note ({stmt[:40]}...): {stmt_err}")
            print("PostgreSQL scheduled_calls Google Meet columns ensured successfully!")
    except Exception as e:
        print(f"Schema update note (non-fatal): {e}")

try:
    run_migrations()
except Exception as e:
    print(f"Startup migrations note (non-fatal): {e}")

from fastapi.responses import JSONResponse

class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"

app = FastAPI(title="Prayer App API", default_response_class=UTF8JSONResponse)

import asyncio
from app.services.call_scheduler import scheduled_call_ringer_worker

@app.on_event("startup")
async def on_startup():
    # Start background auto-ringer task to ring all app users at scheduled meeting times
    asyncio.create_task(scheduled_call_ringer_worker())

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(prayers_router)
app.include_router(calls_router)
app.include_router(testimonies_router)
app.include_router(gallery_router)
app.include_router(monthly_plans_router, prefix="/plans", tags=["Monthly Plans"])
app.include_router(media_router)
from app.api.bible import router as bible_router
app.include_router(bible_router)
from app.api.websocket import router as websocket_router
app.include_router(websocket_router)
from app.api.app_update import router as app_update_router
app.include_router(app_update_router)


import traceback
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal Server Error: {str(exc)}\n{traceback.format_exc()}"}
    )

@app.get("/health")
def health_check():
    return {"status": "ok"}


# Mount Flutter Web App (PWA) static assets so root URL serves the Web App
from fastapi.staticfiles import StaticFiles

class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if path.endswith((".html", "flutter_bootstrap.js", "flutter_service_worker.js", "main.dart.js", ".json")):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if os.path.exists(static_dir):
    app.mount("/", NoCacheStaticFiles(directory=static_dir, html=True), name="static")