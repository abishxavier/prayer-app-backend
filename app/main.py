from fastapi import FastAPI
from app.core import firebase  # triggers Firebase Admin init on startup
from app.api.auth import router as auth_router
from app.api.chats import router as chats_router
from app.api.prayers import router as prayers_router
from app.api.calls import router as calls_router
from app.api.testimonies import router as testimonies_router
from app.api.gallery import router as gallery_router
from app.ws.chat import router as ws_chat_router
from app.db.session import Base, engine
import app.models.testimony  # noqa: F401 — registers Testimony with Base.metadata
import app.models.call        # noqa: F401 — registers ScheduledCall, CallLog
import app.models.user        # noqa: F401 — registers User
import app.models.chat        # noqa: F401 — registers Chat, ChatMember
import app.models.message     # noqa: F401 — registers Message
import app.models.gallery     # noqa: F401 — registers GalleryItem

# Ensure all tables are created
Base.metadata.create_all(bind=engine)

# Run Alembic migrations programmatically on startup
import os
import sys
from alembic.config import Config
from alembic import command

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

run_migrations()

app = FastAPI(title="Prayer App API")

app.include_router(auth_router)
app.include_router(chats_router)
app.include_router(prayers_router)
app.include_router(calls_router)
app.include_router(testimonies_router)
app.include_router(gallery_router)
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