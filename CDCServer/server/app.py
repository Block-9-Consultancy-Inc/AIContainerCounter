from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from server.dependencies import db
from server.routers import counti, dataset_snapshots, images, trained_models

# Load environment variables from .env file
load_dotenv()

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
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(counti.router)
app.include_router(dataset_snapshots.router)
app.include_router(images.router)
app.include_router(trained_models.router)

# --- Root Endpoint for Health Check/Welcome ---
@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "Welcome to the Counti API"}