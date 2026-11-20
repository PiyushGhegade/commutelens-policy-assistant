from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    jwt_secret: str = Field(default="local-case-study-change-this-secret-32-chars", min_length=32)
    demo_mode: bool = True
    demo_password: str = "commute-demo"
    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    embedding_model: str = "minilm"
    # Total budget includes retrieval, provider HTTP call, validation and rendering.
    answer_timeout: float = Field(default=2.8, gt=0, le=30)
    retrieval_timeout: float = Field(default=0.65, gt=0, le=10)
    first_llm_timeout: float = Field(default=1.4, gt=0, le=10)
