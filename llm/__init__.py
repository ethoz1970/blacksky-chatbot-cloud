"""
LLM Provider factory.
Creates the appropriate Llama provider based on LLAMA_PROVIDER environment variable.
"""
import os
from .base import LlamaProvider


def create_llama_provider() -> LlamaProvider:
    """
    Factory function to create the appropriate Llama provider.

    Set LLAMA_PROVIDER environment variable:
    - "local" (default): Use local llama-cpp-python
    - "together": Use Together.ai API
    """
    provider = os.getenv("LLAMA_PROVIDER", "local").lower()

    if provider == "local":
        from .local_provider import LocalLlamaProvider
        return LocalLlamaProvider()
    elif provider == "together":
        from .together_provider import TogetherLlamaProvider
        return TogetherLlamaProvider()
    else:
        raise ValueError(
            f"Unknown LLAMA_PROVIDER: {provider}. "
            f"Valid options: local, together"
        )
