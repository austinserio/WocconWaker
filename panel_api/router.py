"""Aggregate panel API routes."""
from fastapi import APIRouter

from panel_api.routes import admin, auth, documents, lexicon, pending, rules

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(pending.router)
api_router.include_router(rules.router)
api_router.include_router(lexicon.router)
api_router.include_router(admin.router)
