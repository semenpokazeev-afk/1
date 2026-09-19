"""
ARBITER Provider Pool (Module 4)
Registers and manages all providers (Mock, OpenAI, Anthropic, Gemini) with fallback mechanisms.
"""

from typing import Dict, List, Optional, Tuple
from arbiter.core.config import settings
from arbiter.providers.base import BaseProvider, HealthStatus
from arbiter.providers.mock_provider import MockProvider
from arbiter.providers.openai_provider import OpenAIProvider
from arbiter.providers.anthropic_provider import AnthropicProvider
from arbiter.providers.gemini_provider import GeminiProvider
from arbiter.providers.multiplexer import StreamMultiplexer


class ProviderPool:
    def __init__(self):
        self.providers: Dict[str, BaseProvider] = {}
        self.multiplexer = StreamMultiplexer(
            min_timeout=settings.stream_multiplexer_min_timeout_seconds,
            max_timeout=settings.consensus_timeout_seconds
        )
        self._initialize_providers()

    def _initialize_providers(self) -> None:
        # Always register MockProvider
        mock = MockProvider()
        self.providers["mock"] = mock

        # Register OpenAI
        openai_p = OpenAIProvider(api_key=settings.openai_api_key)
        self.providers["openai"] = openai_p

        # Register Anthropic
        anthropic_p = AnthropicProvider(api_key=settings.anthropic_api_key)
        self.providers["anthropic"] = anthropic_p

        # Register Gemini
        gemini_p = GeminiProvider(api_key=settings.gemini_api_key)
        self.providers["gemini"] = gemini_p

    def get_provider(self, name: str) -> Optional[BaseProvider]:
        return self.providers.get(name)

    def get_provider_for_model(self, model_name: str) -> Tuple[BaseProvider, str]:
        """
        Resolves (Provider, actual_model_id). If provider is not available or circuit is open,
        gracefully falls back to MockProvider.
        """
        # Exact matching
        for p in self.providers.values():
            if model_name in p.models:
                if getattr(p, "api_key", True):
                    return p, model_name
                return self.providers["mock"], "mock-gpt-4o"

        # Prefix matching
        if "gpt" in model_name:
            p = self.providers.get("openai")
            if p and getattr(p, "api_key", None):
                return p, model_name
            return self.providers["mock"], "mock-gpt-4o"
        elif "claude" in model_name:
            p = self.providers.get("anthropic")
            if p and getattr(p, "api_key", None):
                return p, model_name
            return self.providers["mock"], "mock-claude-3-5-sonnet"
        elif "gemini" in model_name:
            p = self.providers.get("gemini")
            if p and getattr(p, "api_key", None):
                return p, model_name
            return self.providers["mock"], "mock-gemini-1.5-flash"

        # Default fallback
        return self.providers["mock"], "mock-gpt-4o"

    async def get_all_health_statuses(self) -> List[HealthStatus]:
        statuses = []
        for p in self.providers.values():
            statuses.append(await p.health_check())
        return statuses


pool = ProviderPool()
