from fastapi import FastAPI
from app.core import firebase  # triggers Firebase Admin init on startup
from app.api.auth import router as auth_router
from app.api.chats import router as chats_router
from app.api.prayers import router as prayers_router
from app.api.calls import router as calls_router
from app.api.testimonies import router as testimonies_router
from app.api.gallery import router as gallery_router
from app.api.monthly_plans import router as monthly_plans_router
from app.api.media import router as media_router
from app.ws.chat import router as ws_chat_router
from app.db.session import Base, engine
import app.models.testimony  # noqa: F401 — registers Testimony with Base.metadata
import app.models.call        # noqa: F401 — registers ScheduledCall, CallLog
import app.models.user        # noqa: F401 — registers User
import app.models.chat        # noqa: F401 — registers Chat, ChatMember
import app.models.message     # noqa: F401 — registers Message
import app.models.gallery     # noqa: F401 — registers GalleryItem
import app.models.monthly_plan # noqa: F401 — registers MonthlyPlan

# Ensure all tables are created
Base.metadata.create_all(bind=engine)

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

    # Ensure PostgreSQL accepts any message type (audio, video, text, image) without enum errors
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            try:
                conn.execute(text("ALTER TABLE messages ALTER COLUMN message_type TYPE VARCHAR(50) USING message_type::text;"))
                print("PostgreSQL messages.message_type converted to VARCHAR(50) successfully!")
            except Exception as e:
                print(f"Note on converting message_type column: {e}")
            try:
                conn.execute(text("ALTER TYPE messagetype ADD VALUE IF NOT EXISTS 'audio'"))
                conn.execute(text("ALTER TYPE messagetype ADD VALUE IF NOT EXISTS 'video'"))
            except Exception:
                pass
            try:
                conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS reaction VARCHAR(50);"))
                conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS reply_to_id VARCHAR(100);"))
            except Exception as e:
                print(f"Note on adding reaction/reply_to_id columns: {e}")
            try:
                conn.execute(text("ALTER TABLE scheduled_calls ADD COLUMN IF NOT EXISTS is_rung BOOLEAN DEFAULT FALSE;"))
                print("PostgreSQL scheduled_calls.is_rung ensured successfully!")
            except Exception as e:
                print(f"Note on adding scheduled_calls.is_rung: {e}")
    except Exception as e:
        print(f"Schema update note (non-fatal): {e}")

run_migrations()

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
app.include_router(chats_router)
app.include_router(prayers_router)
app.include_router(calls_router)
app.include_router(testimonies_router)
app.include_router(gallery_router)
app.include_router(monthly_plans_router, prefix="/plans", tags=["Monthly Plans"])
app.include_router(media_router)
app.include_router(ws_chat_router)


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

static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")