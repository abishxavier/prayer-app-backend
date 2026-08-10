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