from fastapi import FastAPI
from app.core import firebase  # triggers Firebase Admin init on startup
from app.api.auth import router as auth_router
from app.api.chats import router as chats_router
from app.api.prayers import router as prayers_router
from app.ws.chat import router as ws_chat_router

app = FastAPI(title="Prayer App API")

app.include_router(auth_router)
app.include_router(chats_router)
app.include_router(prayers_router)
app.include_router(ws_chat_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}