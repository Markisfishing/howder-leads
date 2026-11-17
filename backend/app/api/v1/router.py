"""彙整 /api/v1 底下所有路由。"""

from fastapi import APIRouter

from app.api.v1 import campaigns, companies, contacts, imports, mail_connection, meta, reviews, templates, users

api_router = APIRouter()
api_router.include_router(users.router, tags=["users"])
api_router.include_router(imports.router, tags=["imports"])
api_router.include_router(companies.router, tags=["companies"])
api_router.include_router(contacts.router, tags=["contacts"])
api_router.include_router(reviews.router, tags=["reviews"])
api_router.include_router(templates.router, tags=["templates"])
api_router.include_router(campaigns.router, tags=["campaigns"])
api_router.include_router(mail_connection.router, tags=["mail"])
api_router.include_router(meta.router, tags=["meta"])
