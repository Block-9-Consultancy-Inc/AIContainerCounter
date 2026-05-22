from prisma import Prisma
from functools import lru_cache
from server import config
import roboflow
import aioboto3
from httpx import AsyncClient

@lru_cache
def get_settings():
    return config.Settings()

# Initialize Prisma Client
db = Prisma(
    http={
        'timeout': None
    },
    auto_register=True
)

http_client = AsyncClient()

roboflow_project = roboflow.Roboflow(api_key=get_settings().roboflow_api_key).workspace(get_settings().roboflow_workspace).project(get_settings().roboflow_project)

s3_session = aioboto3.Session(aws_access_key_id=get_settings().aws_access_key_id, aws_secret_access_key=get_settings().aws_secret_access_key)