# app/main.py
from fastapi import FastAPI
from app.api.v1.endpoints import chat
from app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="The backend API for the CookHero intelligent dietary assistant.",
    version="0.1.0",
)

# Include the API router
app.include_router(chat.router, prefix=settings.API_V1_STR, tags=["Chat"])

@app.get("/")
async def root():
    """
    Root endpoint to check API status.
    """
    return {"message": "Welcome to CookHero API!"}
