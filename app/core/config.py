from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ENVIRONMENT: str = "development"
    GROQ_API_KEY: str = ""
    AUDIO_MAX_SIZE_MB: int = 25

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
