from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.ranking import ItemRankingPublico
from app.services.ranking import ranking_service

router = APIRouter()


@router.get("/ranking", response_model=list[ItemRankingPublico])
def ranking(
    categoria: str | None = None,
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return ranking_service.listar(db, categoria=categoria, limit=limit)
