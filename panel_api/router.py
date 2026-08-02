"""Aggregate panel API routes."""
from fastapi import APIRouter

from panel_api.routes import admin, auth, comparative, documents, lexicon, pending, pronunciation_audio, rules, users

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(documents.router)
api_router.include_router(pending.router)
api_router.include_router(rules.router)
api_router.include_router(lexicon.router)
api_router.include_router(comparative.router)
api_router.include_router(pronunciation_audio.router)
api_router.include_router(admin.router)
