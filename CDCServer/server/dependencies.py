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

settings = get_settings()

roboflow_project: roboflow.Roboflow | None = None

if settings.roboflow_api_key is not None and settings.roboflow_project is not None and settings.roboflow_workspace is not None:
    roboflow_project = roboflow.Roboflow(api_key=settings.roboflow_api_key).workspace(settings.roboflow_workspace).project(settings.roboflow_project)

s3_session: aioboto3.Session | None = None

if settings.aws_access_key_id is not None and settings.aws_s3_bucket is not None and settings.aws_secret_access_key is not None:
    s3_session = aioboto3.Session(aws_access_key_id=settings.aws_access_key_id, aws_secret_access_key=settings.aws_secret_access_key)