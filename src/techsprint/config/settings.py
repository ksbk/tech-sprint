from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Runtime configuration for TechSprint.

    All settings are loaded from environment variables with the
    `TECHSPRINT_` prefix and optional `.env` support.

    This class is intentionally flat and explicit to keep runtime
    behavior predictable and debuggable.
    """

    model_config = SettingsConfigDict(
        env_prefix="TECHSPRINT_",
        env_file=".env",
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------
    workdir: str = Field(
        default=".techsprint",
        description="Root directory for pipeline outputs.",
    )
    anchor: str = Field(
        default="tech",
        description="Anchor id to run (e.g. tech, finance, gossip).",
    )
    language: str = Field(
        default="en",
        description="Language code for generated content (e.g. en, fr, is).",
    )
    locale: str = Field(
        default="en-US",
        description="Locale for language/voice selection (e.g. en-US, fr-FR).",
    )
    subtitles_mode: str = Field(
        default="auto",
        description="Subtitle generation mode: auto, asr, or heuristic.",
    )

    # ------------------------------------------------------------------
    # News
    # ------------------------------------------------------------------
    rss_url: str = Field(
        default="https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
        description="RSS feed source for news.",
    )
    max_items: int = Field(
        default=5,
        description="Maximum number of RSS items to ingest.",
    )

    # ------------------------------------------------------------------
    # Script generation (LLM)
    # ------------------------------------------------------------------
    model: str = Field(
        default="gpt-4o-mini",
        description="LLM model name.",
    )
    temperature: float = Field(
        default=0.6,
        description="Sampling temperature for script generation.",
    )
    max_tokens: int = Field(
        default=800,
        description="Maximum tokens for script output.",
    )

    # ------------------------------------------------------------------
    # Audio generation
    # ------------------------------------------------------------------
    voice: str = Field(
        default="Microsoft Server Speech Text to Speech Voice (en-US, JennyNeural)",
        description="Voice identifier for audio generation. Must be a valid edge-tts voice name.",
    )

    # ------------------------------------------------------------------
    # Video rendering
    # ------------------------------------------------------------------
    background_video: str | None = Field(
        default=None,
        description="Path to background video used for final rendering.",
    )
    burn_subtitles: bool = Field(
        default=True,
        description="Whether subtitles should be burned into the video.",
    )
    subtitle_layout_strict: bool = Field(
        default=False,
        description="Fail rendering if subtitle layout exceeds safe-area constraints.",
    )

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR).",
    )

    # ------------------------------------------------------------------
    # Public / safe export
    # ------------------------------------------------------------------
    def to_public_dict(self) -> dict:
        """
        Return a dictionary of non-sensitive settings suitable
        for logging or CLI display.
        """
        return {
            "workdir": self.workdir,
            "anchor": self.anchor,
            "language": self.language,
            "locale": self.locale,
            "subtitles_mode": self.subtitles_mode,
            "rss_url": self.rss_url,
            "max_items": self.max_items,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "voice": self.voice,
            "background_video": self.background_video,
            "burn_subtitles": self.burn_subtitles,
            "subtitle_layout_strict": self.subtitle_layout_strict,
            "log_level": self.log_level,
        }
