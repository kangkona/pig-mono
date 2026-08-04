"""Cohere provider implementation."""

from collections.abc import AsyncIterator, Iterator
from typing import Any

from .._extras import missing_provider_dependency, provider_sdk_is_available
from ..config import Config
from ..models import Message, Response, StreamChunk
from ._base import Provider

if not provider_sdk_is_available("cohere"):
    raise missing_provider_dependency("cohere")
from cohere import AsyncClient, Client


class CohereProvider(Provider):
    """Cohere provider implementation (Command models)."""

    def __init__(self, config: Config):
        """Initialize Cohere provider."""
        self.config = config

        self.client: Any = Client(
            api_key=config.api_key,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )
        self.async_client: Any = AsyncClient(
            api_key=config.api_key,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    def _convert_messages(self, messages: list[Message]) -> tuple[str, str, list[dict[str, Any]]]:
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
        max_tokens: int | None = None,
        **kwargs: Any,
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
        max_tokens: int | None = None,
        **kwargs: Any,
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
                # Usage lives on the final response in the stream-end event.
                usage = None
                response = getattr(event, "response", None)
                meta = getattr(response, "meta", None) if response is not None else None
                tokens = getattr(meta, "tokens", None) if meta is not None else None
                if tokens is not None:
                    inp = int(getattr(tokens, "input_tokens", 0) or 0)
                    out = int(getattr(tokens, "output_tokens", 0) or 0)
                    usage = {
                        "input_tokens": inp,
                        "output_tokens": out,
                        "total_tokens": inp + out,
                    }
                yield StreamChunk(
                    content="",
                    finish_reason=event.finish_reason
                    if hasattr(event, "finish_reason")
                    else "stop",
                    usage=usage,
                    metadata={},
                )

    async def acomplete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
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
        max_tokens: int | None = None,
        **kwargs: Any,
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
                # Usage lives on the final response in the stream-end event.
                usage = None
                response = getattr(event, "response", None)
                meta = getattr(response, "meta", None) if response is not None else None
                tokens = getattr(meta, "tokens", None) if meta is not None else None
                if tokens is not None:
                    inp = int(getattr(tokens, "input_tokens", 0) or 0)
                    out = int(getattr(tokens, "output_tokens", 0) or 0)
                    usage = {
                        "input_tokens": inp,
                        "output_tokens": out,
                        "total_tokens": inp + out,
                    }
                yield StreamChunk(
                    content="",
                    finish_reason=event.finish_reason
                    if hasattr(event, "finish_reason")
                    else "stop",
                    usage=usage,
                    metadata={},
                )
