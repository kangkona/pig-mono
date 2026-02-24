"""Cohere provider implementation."""

from typing import AsyncIterator, Iterator, Optional

try:
    import cohere
    from cohere import AsyncClient, Client
except ImportError:
    raise ImportError("cohere is required. Install with: pip install cohere")

from ..config import Config
from ..models import Message, Response, StreamChunk
from ._base import Provider


class CohereProvider(Provider):
    """Cohere provider implementation (Command models)."""

    def __init__(self, config: Config):
        """Initialize Cohere provider."""
        self.config = config
        
        self.client = Client(
            api_key=config.api_key,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )
        self.async_client = AsyncClient(
            api_key=config.api_key,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    def _convert_messages(self, messages: list[Message]) -> tuple[str, str, list[dict]]:
        """Convert internal messages to Cohere format.
        
        Returns:
            Tuple of (preamble/system, final_message, chat_history)
        """
        preamble = ""
        chat_history = []
        final_message = ""
        
        for i, msg in enumerate(messages):
            if msg.role == "system":
                preamble = msg.content
            elif msg.role == "user":
                if i == len(messages) - 1:
                    # Last user message is the prompt
                    final_message = msg.content
                else:
                    chat_history.append({"role": "USER", "message": msg.content})
            elif msg.role == "assistant":
                chat_history.append({"role": "CHATBOT", "message": msg.content})
        
        return preamble, final_message, chat_history

    def complete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Response:
        """Generate a completion."""
        preamble, message, chat_history = self._convert_messages(messages)
        
        params = {
            "model": model,
            "message": message,
            "temperature": temperature,
        }
        
        if preamble:
            params["preamble"] = preamble
        if chat_history:
            params["chat_history"] = chat_history
        if max_tokens:
            params["max_tokens"] = max_tokens
        
        response = self.client.chat(**params)
        
        usage = {
            "prompt_tokens": response.meta.tokens.input_tokens if response.meta else 0,
            "completion_tokens": response.meta.tokens.output_tokens if response.meta else 0,
            "total_tokens": (
                response.meta.tokens.input_tokens + response.meta.tokens.output_tokens
                if response.meta
                else 0
            ),
        }
        
        return Response(
            content=response.text,
            model=model,
            usage=usage,
            finish_reason=response.finish_reason,
            metadata={"generation_id": response.generation_id},
        )

    def stream(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Iterator[StreamChunk]:
        """Stream a completion."""
        preamble, message, chat_history = self._convert_messages(messages)
        
        params = {
            "model": model,
            "message": message,
            "temperature": temperature,
        }
        
        if preamble:
            params["preamble"] = preamble
        if chat_history:
            params["chat_history"] = chat_history
        if max_tokens:
            params["max_tokens"] = max_tokens
        
        stream = self.client.chat_stream(**params)
        
        for event in stream:
            if event.event_type == "text-generation":
                yield StreamChunk(
                    content=event.text,
                    finish_reason=None,
                    metadata={},
                )
            elif event.event_type == "stream-end":
                yield StreamChunk(
                    content="",
                    finish_reason=event.finish_reason if hasattr(event, "finish_reason") else "stop",
                    metadata={},
                )

    async def acomplete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Response:
        """Async generate a completion."""
        preamble, message, chat_history = self._convert_messages(messages)
        
        params = {
            "model": model,
            "message": message,
            "temperature": temperature,
        }
        
        if preamble:
            params["preamble"] = preamble
        if chat_history:
            params["chat_history"] = chat_history
        if max_tokens:
            params["max_tokens"] = max_tokens
        
        response = await self.async_client.chat(**params)
        
        usage = {
            "prompt_tokens": response.meta.tokens.input_tokens if response.meta else 0,
            "completion_tokens": response.meta.tokens.output_tokens if response.meta else 0,
            "total_tokens": (
                response.meta.tokens.input_tokens + response.meta.tokens.output_tokens
                if response.meta
                else 0
            ),
        }
        
        return Response(
            content=response.text,
            model=model,
            usage=usage,
            finish_reason=response.finish_reason,
            metadata={"generation_id": response.generation_id},
        )

    async def astream(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """Async stream a completion."""
        preamble, message, chat_history = self._convert_messages(messages)
        
        params = {
            "model": model,
            "message": message,
            "temperature": temperature,
        }
        
        if preamble:
            params["preamble"] = preamble
        if chat_history:
            params["chat_history"] = chat_history
        if max_tokens:
            params["max_tokens"] = max_tokens
        
        stream = self.async_client.chat_stream(**params)
        
        async for event in stream:
            if event.event_type == "text-generation":
                yield StreamChunk(
                    content=event.text,
                    finish_reason=None,
                    metadata={},
                )
            elif event.event_type == "stream-end":
                yield StreamChunk(
                    content="",
                    finish_reason=event.finish_reason if hasattr(event, "finish_reason") else "stop",
                    metadata={},
                )
