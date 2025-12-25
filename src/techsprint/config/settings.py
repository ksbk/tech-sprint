from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TECHSPRINT_", env_file=".env", extra="ignore")

    # Runtime
    workdir: str = Field(default=".techsprint", description="Root directory for pipeline outputs.")
    anchor: str = Field(default="tech", description="Anchor id to run.")

    # News
    rss_url: str = Field(
        default="https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
        description="RSS feed source for news.",
    )
    max_items: int = Field(default=5, description="Max RSS items to ingest.")

    # Script (LLM)
    model: str = Field(default="gpt-4o-mini", description="LLM model name.")
    temperature: float = Field(default=0.6, description="Sampling temperature.")
    max_tokens: int = Field(default=800, description="Max output tokens.")

    # Media placeholders
    voice: str = Field(default="en-US", description="TTS voice id.")

    def to_public_dict(self) -> dict:
        return {
            "workdir": self.workdir,
            "anchor": self.anchor,
            "rss_url": self.rss_url,
            "max_items": self.max_items,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "voice": self.voice,
        }
