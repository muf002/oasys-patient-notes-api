from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constants import DEFAULT_AUDIO_MAX_SIZE_MB, DEFAULT_ENVIRONMENT


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ENVIRONMENT: str = DEFAULT_ENVIRONMENT
    GROQ_API_KEY: str = ""
    AUDIO_MAX_SIZE_MB: int = DEFAULT_AUDIO_MAX_SIZE_MB

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
