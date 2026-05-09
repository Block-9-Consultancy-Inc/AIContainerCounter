# auth.py

from fastapi import Security, HTTPException, status, Depends
from typing_extensions import Annotated
from fastapi.security import APIKeyHeader
from server import config
from server.dependencies import get_settings

api_key = APIKeyHeader(name="api-key")

def handle_api_key(settings: Annotated[config.Settings, Depends(get_settings)], key: str = Security(api_key)):
    if settings.api_key != key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API Key is not valid!"
        )