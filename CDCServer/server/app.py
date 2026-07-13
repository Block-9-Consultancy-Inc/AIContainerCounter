from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from server.dependencies import db
from server.auth import handle_api_key
from server.routers import counti, dataset_snapshots, images, trained_models, tasks, metrics

# --- FastAPI Application Setup ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Connect the Prisma client on application startup
    print("Connecting to database...")
    await db.connect()
    yield
    # Disconnect the Prisma client on application shutdown
    print("Disconnecting from database...")
    if db.is_connected():
        await db.disconnect()

# Create FastAPI app instance with lifespan management
app = FastAPI(
    title="Counti API",
    description="API for managing Counti datasets and models.",
    dependencies=[Depends(handle_api_key)],
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(counti.router)
app.include_router(dataset_snapshots.router)
app.include_router(images.router)
app.include_router(trained_models.router)
app.include_router(tasks.router)
app.include_router(metrics.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# --- Root Endpoint for Health Check/Welcome ---
@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "Welcome to the Counti API"}