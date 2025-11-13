"""
Simple Cloud Run API service using FastAPI.
"""
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Gmail Agent API", version="0.1.0")


class HealthResponse(BaseModel):
    status: str
    message: str


class EchoRequest(BaseModel):
    message: str


class EchoResponse(BaseModel):
    echo: str
    original: str


@app.get("/", response_model=HealthResponse)
def root():
    """Root endpoint."""
    return HealthResponse(status="ok", message="Gmail Agent API is running")


@app.get("/health", response_model=HealthResponse)
def health():
    """Health check endpoint."""
    return HealthResponse(status="ok", message="Healthy")


@app.post("/echo", response_model=EchoResponse)
def echo(request: EchoRequest):
    """Echo endpoint for testing."""
    return EchoResponse(echo=f"Echo: {request.message}", original=request.message)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

