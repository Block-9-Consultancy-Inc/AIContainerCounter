from prisma import Prisma
from functools import lru_cache
from server import config

# Initialize Prisma Client
db = Prisma(
    http={
        'timeout': None
    },
    auto_register=True
)


@lru_cache
def get_settings():
    return config.Settings()