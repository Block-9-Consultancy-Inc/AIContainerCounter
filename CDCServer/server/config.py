from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    db_url: str
    api_key: str
    python_env: str = 'DEVELOPMENT'
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_s3_bucket: Optional[str] = None
    aws_s3_prefix: Optional[str] = None
    pulse_access_key: Optional[str] = None
    temp_data_dir: str = './temp_data_dir'
    
    model_config = SettingsConfigDict(env_file=".env")