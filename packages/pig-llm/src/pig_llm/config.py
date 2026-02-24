"""Configuration for LLM clients."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class Config(BaseModel):
    """Configuration for LLM client."""

    provider: Literal[
        "openai",
        "anthropic",
        "google",
        "azure",
        "groq",
        "mistral",
        "openrouter",
        "bedrock",
        "xai",
        "cerebras",
        "cohere",
        "perplexity",
        "deepseek",
        "together",
    ] = "openai"
    model: str = "gpt-4"
    api_key: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    timeout: int = Field(default=30, ge=1)
    max_retries: int = Field(default=3, ge=0)
    base_url: Optional[str] = None

    class Config:
        """Pydantic config."""

        frozen = True
