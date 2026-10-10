from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Usuario
from app.schemas.categorias import CategoriaPublica
from app.security import usuario_atual_opcional
from app.services.categorias import categorias_service


router = APIRouter()


@router.get("/categorias", response_model=list[CategoriaPublica])
def listar_categorias(db: Session = Depends(get_db)):
    return categorias_service.listar(db, somente_ativas=True)


@router.get("/categorias/jogaveis", response_model=list[CategoriaPublica])
def listar_categorias_jogaveis(
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(usuario_atual_opcional),
):
    return categorias_service.listar_jogaveis(db, usuario)
