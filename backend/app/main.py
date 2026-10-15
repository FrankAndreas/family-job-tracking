import logging

from fastapi import FastAPI

from . import database, models

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Family Job Tracking API", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok"}
