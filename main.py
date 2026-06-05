from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from core.app import create_app

app: FastAPI = create_app()

app.mount("/static", StaticFiles(directory="static"), name="static")
