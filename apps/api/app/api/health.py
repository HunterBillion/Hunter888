from fastapi import APIRouter

router = APIRouter()


@router.get("/monitoring/health")
async def health_check():
    return {
        "status": "ok",
        "service": "ai-trainer-api",
        "version": "0.1.0",
    }
