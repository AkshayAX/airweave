"""LLM provider adapters for vLLM and Ollama."""

from abc import ABC, abstractmethod
from typing import List, Optional
import httpx
import asyncio
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract LLM provider interface."""

    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate single response."""
        pass

    @abstractmethod
    async def generate_batch(self, prompts: List[str], **kwargs) -> List[str]:
        """Generate batch responses."""
        pass

    async def close(self):
        """Cleanup resources."""
        pass


class OllamaProvider(LLMProvider):
    """Ollama provider for local models."""

    def __init__(self, base_url: str = "http://localhost:11434", model_name: str = "qwen2.5:3b",
                 timeout: float = 210.0, temperature: float = 0.1, max_tokens: int = 512):
        self.base_url = base_url.rstrip('/')
        self.model_name = model_name
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client: Optional[httpx.AsyncClient] = None
        logger.info(f"OllamaProvider initialized: {base_url}, model={model_name}")

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
    async def generate(self, prompt: str, **kwargs) -> str:
        client = await self._get_client()
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", self.temperature),
                "num_predict": kwargs.get("max_tokens", self.max_tokens),
                "top_p": 0.9,
            }
        }
        try:
            response = await client.post(f"{self.base_url}/api/generate", json=payload,
                                        headers={"Content-Type": "application/json"})
            response.raise_for_status()
            return response.json()["response"].strip()
        except Exception as e:
            logger.error(f"Ollama generation error: {e}")
            raise

    async def generate_batch(self, prompts: List[str], **kwargs) -> List[str]:
        tasks = [self.generate(prompt, **kwargs) for prompt in prompts]
        return await asyncio.gather(*tasks)

    async def close(self):
        if self._client:
            await self._client.aclose()


class VLLMProvider(LLMProvider):
    """vLLM provider (OpenAI-compatible API)."""

    def __init__(self, base_url: str = "http://localhost:8000", model_name: str = "qwen2.5:3b",
                 timeout: float = 210.0, temperature: float = 0.1, max_tokens: int = 512):
        self.base_url = base_url.rstrip('/')
        self.model_name = model_name
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client: Optional[httpx.AsyncClient] = None
        logger.info(f"VLLMProvider initialized: {base_url}, model={model_name}")

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
    async def generate(self, prompt: str, **kwargs) -> str:
        client = await self._get_client()
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "stream": False
        }
        try:
            response = await client.post(f"{self.base_url}/v1/chat/completions", json=payload,
                                        headers={"Content-Type": "application/json"})
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"vLLM generation error: {e}")
            raise

    async def generate_batch(self, prompts: List[str], **kwargs) -> List[str]:
        tasks = [self.generate(prompt, **kwargs) for prompt in prompts]
        return await asyncio.gather(*tasks)

    async def close(self):
        if self._client:
            await self._client.aclose()


class LLMProviderFactory:
    """Factory for creating LLM providers."""

    @staticmethod
    def create(provider_type: str, base_url: str, model_name: str, **kwargs) -> LLMProvider:
        provider_type = provider_type.lower()
        if provider_type == "ollama":
            return OllamaProvider(base_url, model_name, **kwargs)
        elif provider_type == "vllm":
            return VLLMProvider(base_url, model_name, **kwargs)
        else:
            raise ValueError(f"Unknown provider type: {provider_type}")
