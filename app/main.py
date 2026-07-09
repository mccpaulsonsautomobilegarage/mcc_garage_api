from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import init_db
from app.features.auth.auth_router import router as auth_router
from app.features.customer.customer_router import router as customer_router
from app.features.vehicle.vehicle_router import router as vehicle_router
from app.features.job_card.job_card_router import router as job_card_router

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    print("Database connected successfully!")
    yield

app = FastAPI(title="MCC Garage API", lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins, modify in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth_router)
app.include_router(customer_router)
app.include_router(vehicle_router)
app.include_router(job_card_router)

@app.get("/")
async def root():
    return {"message": "Welcome to MCC Garage API"}

if __name__ == "__main__":
    import uvicorn
    import os
    # Read the port Render provides, default to 8000 locally
    port = int(os.environ.get("PORT", 8000))
    # Bind to 0.0.0.0 in production (Render), 127.0.0.1 locally
    host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    # Disable reload in production to optimize performance
    reload = False if os.environ.get("PORT") else True
    
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)
