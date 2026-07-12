import os
from contextlib import asynccontextmanager

from core.config import ALLOWED_ORIGINS, MOCK_MODE
from core.database import engine, init_db
from core.logger import setup_logger
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()
logger = setup_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info(f"🚀 Bidding service starting (mock_mode={MOCK_MODE})")
    yield


app = FastAPI(title="Tender Bidding Microservice", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check(response: Response):
    from sqlalchemy import text

    status = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"❌ Health DB failure: {e}")
        status = "degraded"
        response.status_code = 503
    return {"status": status, "service": "bidding", "mock_mode": MOCK_MODE}


@app.get("/version")
async def version():
    return {"version": os.getenv("DEPLOY_TIMESTAMP", "unknown"), "service": os.getenv("APP_NAME", "bidding")}


from api.v1 import bids, checklist, comments, config, documents, internal, library, matrix, stats  # noqa: E402

for r in (
    internal.router,
    bids.router,
    checklist.router,
    documents.router,
    comments.router,
    library.router,
    matrix.router,
    config.router,
    stats.router,
):
    app.include_router(r, prefix="/api/v1")


# Serve the React UI (dashboard style) when built.
ui_dist = os.path.join(os.path.dirname(__file__), "ui", "dist")
if os.path.exists(ui_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(ui_dist, "assets")), name="assets")

    @app.get("/")
    async def root():
        return FileResponse(os.path.join(ui_dist, "index.html"))

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        if full_path.startswith("api") or full_path in ("health", "version"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = os.path.join(ui_dist, full_path)
        if os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(ui_dist, "index.html"))
else:

    @app.get("/")
    async def root_placeholder():
        return {"service": "bidding", "ui": "not built — run npm build in ui/", "mock_mode": MOCK_MODE}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8014)))
