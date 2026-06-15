from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging

from backend.core.config import settings
from backend.core.database import Base, engine

# Import routers (assuming they will be created)
# from backend.api.routes import router as api_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logger.info("Starting up OpenSource AI Engineer...")
    async with engine.begin() as conn:
        # Create all tables (in a real app, use Alembic)
        # await conn.run_sync(Base.metadata.create_all)
        pass
        
    yield
    
    # Shutdown actions
    logger.info("Shutting down OpenSource AI Engineer...")
    await engine.dispose()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"message": "An unexpected error occurred. Please try again later."},
    )

# Include API router
# app.include_router(api_router, prefix="/api")

@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.VERSION}
