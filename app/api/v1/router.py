from fastapi import APIRouter

from app.api.v1.patients import router as patients_router
from app.api.v1.providers import router as providers_router

router = APIRouter()
router.include_router(providers_router)
router.include_router(patients_router)
