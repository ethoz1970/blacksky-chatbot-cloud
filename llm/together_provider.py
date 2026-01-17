"""
Together.ai Llama inference via OpenAI-compatible API.
"""
import os
from typing import Generator
from openai import OpenAI
from .base import LlamaProvider


class TogetherLlamaProvider(LlamaProvider):
    """Together.ai Llama inference via OpenAI-compatible API."""

    def __init__(self):
        self.client = None
        self.model = "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"

    def load(self) -> None:
        """Initialize the Together.ai client."""
        api_key = os.getenv("TOGETHER_API_KEY")
        if not api_key:
            raise ValueError("Missing TOGETHER_API_KEY environment variable")

        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.together.xyz/v1"
        )
        print(f"Connected to Together.ai API")
        print(f"  Model: {self.model}")

    def _parse_llama_prompt(self, prompt: str) -> list[dict]:
        """
        Convert Llama 3.1 format prompt to OpenAI messages array.

        Parses format like:
        <|start_header_id|>system<|end_header_id|>

        content<|eot_id|>
        """
        messages = []

        # Extract system message
        system_marker = "<|start_header_id|>system<|end_header_id|>"
        if system_marker in prompt:
            system_start = prompt.find(system_marker) + len(system_marker)
            system_end = prompt.find("<|eot_id|>", system_start)
            if system_end > system_start:
                system_content = prompt[system_start:system_end].strip()
                messages.append({"role": "system", "content": system_content})

        # Extract user/assistant turns
        remaining = prompt
        user_marker = "<|start_header_id|>user<|end_header_id|>"
        asst_marker = "<|start_header_id|>assistant<|end_header_id|>"

        while user_marker in remaining:
            # Find user message
            user_start = remaining.find(user_marker) + len(user_marker)
            user_end = remaining.find("<|eot_id|>", user_start)
            if user_end > user_start:
                user_content = remaining[user_start:user_end].strip()
                messages.append({"role": "user", "content": user_content})
            remaining = remaining[user_end + len("<|eot_id|>"):]

            # Check for assistant response (complete turn, not the final prompt)
            if asst_marker in remaining:
                asst_start = remaining.find(asst_marker) + len(asst_marker)
                asst_end = remaining.find("<|eot_id|>", asst_start)

                # Only add if there's actual content (not just the prompt ending)
                if asst_end > asst_start:
                    asst_content = remaining[asst_start:asst_end].strip()
                    if asst_content:  # Has content
                        messages.append({"role": "assistant", "content": asst_content})
                    remaining = remaining[asst_end + len("<|eot_id|>"):]
                else:
                    # This is the final assistant prompt marker, no more content
                    break

        return messages

    def chat(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        repeat_penalty: float,
        stop: list[str]
    ) -> str:
        """Generate a response using Together.ai API."""
        messages = self._parse_llama_prompt(prompt)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            frequency_penalty=repeat_penalty - 1.0,  # Convert repeat_penalty to frequency_penalty
        )
        return response.choices[0].message.content.strip()

    def chat_stream(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        repeat_penalty: float,
        stop: list[str]
    ) -> Generator[str, None, None]:
        """Generate a streaming response using Together.ai API."""
        messages = self._parse_llama_prompt(prompt)

        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            frequency_penalty=repeat_penalty - 1.0,
            stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def is_loaded(self) -> bool:
        """Check if client is initialized."""
        return self.client is not None
