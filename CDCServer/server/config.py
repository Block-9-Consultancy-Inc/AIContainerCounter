from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    db_url: str
    api_key: str
    python_env: str = 'DEVELOPMENT'

    model_config = SettingsConfigDict(env_file=".env")