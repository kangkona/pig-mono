"""Configuration for LLM clients."""

from pydantic import BaseModel, Field


class Config(BaseModel):
    """Configuration for LLM client."""

    provider: str = "openai"
    model: str = "gpt-4"
    api_key: str | None = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1)
    timeout: int = Field(default=30, ge=1)
    max_retries: int = Field(default=3, ge=0)
    base_url: str | None = None

    class Config:
        """Pydantic config."""

        frozen = True
