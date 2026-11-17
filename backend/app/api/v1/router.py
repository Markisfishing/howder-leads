"""彙整 /api/v1 底下所有路由。"""

from fastapi import APIRouter

from app.api.v1 import users

api_router = APIRouter()
api_router.include_router(users.router, tags=["users"])
