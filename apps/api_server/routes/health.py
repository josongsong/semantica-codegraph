from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def health_check():
    """헬스 체크"""
    return {"status": "ok"}


@router.get("/ready")
async def readiness_check():
    """레디니스 체크"""
    # TODO: DB 연결 확인
    return {"status": "ready"}

