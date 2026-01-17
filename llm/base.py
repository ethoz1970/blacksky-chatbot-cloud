"""
Abstract base class for Llama model providers.
"""
from abc import ABC, abstractmethod
from typing import Generator


class LlamaProvider(ABC):
    """Abstract base class for Llama model providers."""

    @abstractmethod
    def load(self) -> None:
        """Initialize/load the model."""
        pass

    @abstractmethod
    def chat(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        repeat_penalty: float,
        stop: list[str]
    ) -> str:
        """Generate a response (non-streaming)."""
        pass

    @abstractmethod
    def chat_stream(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        repeat_penalty: float,
        stop: list[str]
    ) -> Generator[str, None, None]:
        """Generate a streaming response, yielding tokens."""
        pass

    @abstractmethod
    def is_loaded(self) -> bool:
        """Check if model is ready."""
        pass
