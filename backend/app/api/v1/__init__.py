from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.categorias import router as categorias_router
from app.api.v1.ranking import router as ranking_router
from app.api.v1.partidas import router as partidas_router
from app.api.v1.perguntas import router as perguntas_router
from app.api.v1.nem_a_pato import router as nem_a_pato_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(categorias_router)
api_router.include_router(ranking_router)
api_router.include_router(partidas_router)
api_router.include_router(perguntas_router)
api_router.include_router(nem_a_pato_router)
