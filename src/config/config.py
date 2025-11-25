"""
Configuration Management for News Generator

Centralized environment variable loading and validation.
"""

from __future__ import annotations
import os
from typing import Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Application configuration from environment variables"""

    # ===== TEMPORAL =====
    TEMPORAL_ADDRESS: str = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    TEMPORAL_NAMESPACE: str = os.getenv("TEMPORAL_NAMESPACE", "default")
    TEMPORAL_API_KEY: Optional[str] = os.getenv("TEMPORAL_API_KEY")
    TEMPORAL_TASK_QUEUE: str = os.getenv("TEMPORAL_TASK_QUEUE", "quest-content-queue")

    # ===== DATABASE =====
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # ===== AI SERVICES =====
    GOOGLE_API_KEY: Optional[str] = os.getenv("GOOGLE_API_KEY")
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY")

    # ===== SEARCH & RESEARCH =====
    DATAFORSEO_LOGIN: Optional[str] = os.getenv("DATAFORSEO_LOGIN")
    DATAFORSEO_PASSWORD: Optional[str] = os.getenv("DATAFORSEO_PASSWORD")
    SERPER_API_KEY: Optional[str] = os.getenv("SERPER_API_KEY")

    # ===== KNOWLEDGE GRAPH =====
    ZEP_API_KEY: Optional[str] = os.getenv("ZEP_API_KEY")

    # ===== APPLICATION SETTINGS =====
    DEFAULT_APP: str = os.getenv("DEFAULT_APP", "placement")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info")

    @classmethod
    def validate_required(cls) -> list[str]:
        """
        Validate required environment variables.

        Returns:
            List of missing required variables (empty if all present)
        """
        required = {
            "TEMPORAL_ADDRESS": cls.TEMPORAL_ADDRESS,
            "TEMPORAL_NAMESPACE": cls.TEMPORAL_NAMESPACE,
            "TEMPORAL_TASK_QUEUE": cls.TEMPORAL_TASK_QUEUE,
            "DATAFORSEO_LOGIN": cls.DATAFORSEO_LOGIN,
            "DATAFORSEO_PASSWORD": cls.DATAFORSEO_PASSWORD,
            "SERPER_API_KEY": cls.SERPER_API_KEY,
        }

        # At least one AI provider
        has_ai = any([
            cls.GOOGLE_API_KEY,
            cls.OPENAI_API_KEY,
            cls.ANTHROPIC_API_KEY
        ])

        missing = [
            key for key, value in required.items()
            if not value
        ]

        if not has_ai:
            missing.append("GOOGLE_API_KEY or OPENAI_API_KEY or ANTHROPIC_API_KEY")

        return missing

    @classmethod
    def get_ai_model(cls) -> tuple[str, str]:
        """
        Get preferred AI model.

        Returns:
            Tuple of (provider, model_name)
        """
        # Anthropic Claude for news assessment (Haiku for cost savings)
        if cls.ANTHROPIC_API_KEY:
            return ("anthropic", "claude-3-5-haiku-20241022")
        elif cls.GOOGLE_API_KEY:
            return ("google-gla", "gemini-1.5-flash")
        elif cls.OPENAI_API_KEY:
            return ("openai", "gpt-4o-mini")
        else:
            raise ValueError("No AI API key configured")

    @classmethod
    def is_production(cls) -> bool:
        """Check if running in production"""
        return cls.ENVIRONMENT.lower() == "production"

    @classmethod
    def as_dict(cls) -> dict[str, Any]:
        """Export config as dictionary (sanitized)"""
        return {
            "temporal_address": cls.TEMPORAL_ADDRESS,
            "temporal_namespace": cls.TEMPORAL_NAMESPACE,
            "task_queue": cls.TEMPORAL_TASK_QUEUE,
            "environment": cls.ENVIRONMENT,
            "default_app": cls.DEFAULT_APP,
            "has_database": bool(cls.DATABASE_URL),
            "has_dataforseo": bool(cls.DATAFORSEO_LOGIN and cls.DATAFORSEO_PASSWORD),
            "has_serper": bool(cls.SERPER_API_KEY),
            "has_zep": bool(cls.ZEP_API_KEY),
            "has_ai": bool(cls.GOOGLE_API_KEY or cls.OPENAI_API_KEY or cls.ANTHROPIC_API_KEY),
        }


# Singleton instance
config = Config()
