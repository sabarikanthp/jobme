from typing import Literal

from jobme.config.settings import ProviderConfig
from jobme.llm.anthropic_provider import AnthropicProvider
from jobme.llm.openai_provider import OpenAICompatibleProvider
from jobme.llm.search import BraveSearch, SearchBackend, SearchError, TavilySearch
from jobme.llm.types import Provider
from jobme.secrets import get_secret


def build_provider(cfg: ProviderConfig) -> Provider:
    api_key = get_secret(f"provider:{cfg.id}")
    if cfg.kind == "anthropic":
        return AnthropicProvider(cfg.id, api_key)
    if cfg.kind == "openai_compatible":
        return OpenAICompatibleProvider(
            cfg.id, api_key, cfg.base_url, structured_output=cfg.structured_output
        )
    raise ValueError(f"Unknown provider kind: {cfg.kind!r}")


def build_search(backend: Literal["tavily", "brave", "builtin"]) -> SearchBackend:
    if backend == "builtin":
        raise ValueError("Built-in search has no separate key")
    api_key = get_secret(f"search:{backend}")
    if not api_key:
        raise SearchError("No search key saved")
    if backend == "tavily":
        return TavilySearch(api_key)
    if backend == "brave":
        return BraveSearch(api_key)
    raise ValueError(f"Unknown search backend: {backend!r}")
