from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.ranking import ItemRankingPublico
from app.schemas.temporadas import TemporadaPublica
from app.services.ranking import ranking_service
from app.services.temporadas import (
    TemporadaAtivaAusente,
    TemporadaInexistente,
    temporadas_service,
)


router = APIRouter()


@router.get("/ranking", response_model=list[ItemRankingPublico])
def ranking(
    categoria: str | None = None,
    temporada: str | None = None,
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    try:
        return ranking_service.listar(
            db, categoria=categoria, temporada=temporada, limit=limit
        )
    except TemporadaAtivaAusente as erro:
        raise HTTPException(status_code=503, detail=str(erro)) from erro
    except TemporadaInexistente as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro


@router.get("/ranking/temporadas", response_model=list[TemporadaPublica])
def listar_temporadas(db: Session = Depends(get_db)):
    return temporadas_service.listar_publicas(db)
