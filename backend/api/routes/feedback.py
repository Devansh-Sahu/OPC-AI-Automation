from fastapi import APIRouter
router = APIRouter()

@router.get("/")
async def get_feedback():
    return {"data": []}
