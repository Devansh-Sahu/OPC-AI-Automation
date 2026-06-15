from fastapi import APIRouter
router = APIRouter()

@router.post("/")
async def receive_webhook():
    return {"status": "ok"}
