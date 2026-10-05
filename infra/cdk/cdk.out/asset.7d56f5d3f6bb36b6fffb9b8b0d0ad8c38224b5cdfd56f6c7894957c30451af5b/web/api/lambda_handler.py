"""AWS Lambda adapter for the FastAPI application."""

from mangum import Mangum

from web.api.app import app

handler = Mangum(app)
