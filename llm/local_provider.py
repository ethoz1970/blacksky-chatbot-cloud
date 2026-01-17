"""
Local Llama inference using llama-cpp-python.
"""
from typing import Generator
from llama_cpp import Llama
from .base import LlamaProvider
from config import MODEL_PATH, N_GPU_LAYERS, N_THREADS, N_CTX, N_BATCH
from download_model import download_model


class LocalLlamaProvider(LlamaProvider):
    """Local Llama inference using llama-cpp-python with GPU acceleration."""

    def __init__(self):
        self.model = None

    def load(self) -> None:
        """Load the local GGUF model."""
        if not MODEL_PATH.exists():
            print("Model not found locally, downloading...")
            download_model()

        print(f"Loading model from {MODEL_PATH}...")
        print(f"  GPU layers: {N_GPU_LAYERS}")
        print(f"  Threads: {N_THREADS}")
        print(f"  Context: {N_CTX}")

        self.model = Llama(
            model_path=str(MODEL_PATH),
            n_gpu_layers=N_GPU_LAYERS,
            n_threads=N_THREADS,
            n_ctx=N_CTX,
            n_batch=N_BATCH,
            verbose=False
        )
        print("Model loaded successfully!")

    def chat(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        repeat_penalty: float,
        stop: list[str]
    ) -> str:
        """Generate a response using local model."""
        output = self.model(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            repeat_penalty=repeat_penalty,
            stop=stop,
            echo=False
        )
        return output["choices"][0]["text"].strip()

    def chat_stream(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        repeat_penalty: float,
        stop: list[str]
    ) -> Generator[str, None, None]:
        """Generate a streaming response using local model."""
        for output in self.model(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            repeat_penalty=repeat_penalty,
            stop=stop,
            echo=False,
            stream=True
        ):
            yield output["choices"][0]["text"]

    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self.model is not None
