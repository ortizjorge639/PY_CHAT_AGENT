"""Application settings loaded from .env via pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralised configuration — every value comes from an env var or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Data source
    datasource: str = "excel"
    excel_folder_path: str = "./data/mock"

    # SQL Server (production)
    sql_server: str = ""
    sql_port: str = "1433"
    sql_database: str = ""
    sql_table: str = ""
    sql_trusted_connection: str = "yes"
    sql_username: str = ""
    sql_password: str = ""

    # Azure OpenAI
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment_name: str = "gpt-4.1-mini"

    # Bot Framework
    microsoft_app_id: str = ""
    microsoft_app_password: str = ""
    microsoft_app_tenant_id: str = ""
    bot_port: int = 3978

    # Access control
    require_auth: bool = False
    file_download_group_id: str = ""

    # General
    log_level: str = "INFO"
