import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI

from .auth.routes import router as auth_router
from .chat.routes import router as chat_router
from .friends.routes import router as friends_router

load_dotenv()

server = FastAPI(title="Chat Server")

server.include_router(auth_router)
server.include_router(friends_router)
server.include_router(chat_router)


def start():
    uvicorn.run("src.server:server", host="0.0.0.0", port=8000, reload=True)
