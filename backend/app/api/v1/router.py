"""彙整 /api/v1 底下所有路由。"""

from fastapi import APIRouter

from app.api.v1 import companies, contacts, imports, meta, reviews, users

api_router = APIRouter()
api_router.include_router(users.router, tags=["users"])
api_router.include_router(imports.router, tags=["imports"])
api_router.include_router(companies.router, tags=["companies"])
api_router.include_router(contacts.router, tags=["contacts"])
api_router.include_router(reviews.router, tags=["reviews"])
api_router.include_router(meta.router, tags=["meta"])
