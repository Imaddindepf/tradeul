"""
Dilution Tracker Service
Análisis de dilución de acciones
"""

import sys
sys.path.append('/app')

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.utils.logger import get_logger
from routers import analysis_router, sec_dilution_router

logger = get_logger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Dilution Tracker",
    description="Análisis de dilución de acciones y cash runway",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(analysis_router)
app.include_router(sec_dilution_router)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "dilution-tracker",
        "version": "1.0.0"
    }


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Dilution Tracker API",
        "version": "1.0.0",
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

