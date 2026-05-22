from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    db_url: str
    api_key: str
    python_env: str = 'DEVELOPMENT'
    roboflow_api_key: str
    roboflow_workspace: str
    roboflow_project: str
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_s3_bucket: str
    pulse_access_key: str
    temp_data_dir: str = './temp_data_dir'
    
    model_config = SettingsConfigDict(env_file=".env")