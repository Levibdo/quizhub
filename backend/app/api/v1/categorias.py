from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.categorias import CategoriaPublica
from app.services.categorias import categorias_service


router = APIRouter()


@router.get("/categorias", response_model=list[CategoriaPublica])
def listar_categorias(db: Session = Depends(get_db)):
    return categorias_service.listar(db, somente_ativas=True)
