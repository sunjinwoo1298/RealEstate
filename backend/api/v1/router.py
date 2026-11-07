from fastapi import APIRouter
from backend.api.v1.endpoints.health import router as health_router
from backend.api.v1.endpoints.auth import router as auth_router
from backend.api.v1.endpoints.admin_users import router as admin_users_router
from backend.api.v1.endpoints.leads import router as leads_router
from backend.api.v1.endpoints.chat import router as chat_router
from backend.api.v1.endpoints.conversations import router as conversations_router
from backend.api.v1.endpoints.projects import router as projects_router
from backend.api.v1.endpoints.knowledge import router as knowledge_router
from backend.api.v1.endpoints.availability import (
    router as availability_router,
    admin_rules_router,
    admin_blocked_router,
    admin_capacity_router,
)
from backend.api.v1.endpoints.bookings import router as bookings_router
from backend.api.v1.endpoints.handoffs import router as handoffs_router
from backend.api.v1.endpoints.reminders import router as reminders_router

api_v1_router = APIRouter()
api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(admin_users_router)
api_v1_router.include_router(leads_router)
api_v1_router.include_router(chat_router)
api_v1_router.include_router(conversations_router)
api_v1_router.include_router(projects_router)
api_v1_router.include_router(knowledge_router)
api_v1_router.include_router(availability_router)
api_v1_router.include_router(admin_rules_router)
api_v1_router.include_router(admin_blocked_router)
api_v1_router.include_router(admin_capacity_router)
api_v1_router.include_router(bookings_router)
api_v1_router.include_router(handoffs_router)
api_v1_router.include_router(reminders_router)
