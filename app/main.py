# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.endpoints import chat, conversation
from app.config import settings
import logging

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="The backend API for the CookHero intelligent dietary assistant.",
    version="0.1.0",
)

# CORS middleware for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8000", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the API routers
app.include_router(chat.router, prefix=settings.API_V1_STR, tags=["Chat"])
app.include_router(conversation.router, prefix=settings.API_V1_STR, tags=["Conversation"])

@app.get("/")
async def root():
    """
    Root endpoint to check API status.
    """
    return {"message": "Welcome to CookHero API!"}
