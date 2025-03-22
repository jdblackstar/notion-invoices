"""Main API router that combines all endpoints."""

from fastapi import APIRouter

from app.api import webhooks

# Create main router
api_router = APIRouter()

# Include sub-routers
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
