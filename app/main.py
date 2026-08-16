"""FastAPI application entry point for the CuraPharm skeleton."""

from fastapi import FastAPI

from app.api.routes import router


app = FastAPI(
    title="CuraPharm AI Process Intelligence Platform",
    version="0.1.0",
    description="Modular foundation for pharmaceutical process intelligence.",
)
app.include_router(router)

