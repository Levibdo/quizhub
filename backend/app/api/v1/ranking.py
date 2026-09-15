from fastapi import APIRouter

router = APIRouter()


@router.get("/ranking")
def ranking():
    return []