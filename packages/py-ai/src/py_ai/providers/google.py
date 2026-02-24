"""Google Gemini provider implementation."""

import warnings
from typing import AsyncIterator, Iterator, Optional

with warnings.catch_warnings():
    warnings.simplefilter("ignore", FutureWarning)
    import google.generativeai as genai

from ..config import Config
from ..models import Message, Response, StreamChunk
from ._base import Provider


class GoogleProvider(Provider):
    """Google Gemini provider implementation."""

    def __init__(self, config: Config):
        """Initialize Google provider."""
        self.config = config
        
        # Configure API
        genai.configure(api_key=config.api_key)
        
        # Create model
        self.model = genai.GenerativeModel(config.model)

    def _convert_messages(self, messages: list[Message]) -> list[dict]:
        """Convert internal messages to Google format.
        
        Returns:
            List of messages in Google format
        """
        # Google uses 'user' and 'model' roles
        google_messages = []
        system_parts = []
        
        for msg in messages:
            if msg.role == "system":
                system_parts.append(msg.content)
            elif msg.role == "assistant":
                google_messages.append({
                    "role": "model",
                    "parts": [msg.content]
                })
            else:  # user
                google_messages.append({
                    "role": "user",
                    "parts": [msg.content]
                })
        
        # Prepend system message as first user message if present
        if system_parts:
            system_content = "\n".join(system_parts)
            if google_messages:
                # Insert at beginning
                google_messages.insert(0, {
                    "role": "user",
                    "parts": [f"System instructions: {system_content}"]
                })
        
        return google_messages

    def complete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Response:
        """Generate a completion."""
        google_messages = self._convert_messages(messages)
        
        # Build chat
        chat = self.model.start_chat(history=google_messages[:-1] if len(google_messages) > 1 else [])
        
        # Get last message
        last_message = google_messages[-1]["parts"][0] if google_messages else ""
        
        # Generate response
        response = chat.send_message(
            last_message,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
        )

        # Extract usage if available
        usage = {}
        if hasattr(response, "usage_metadata"):
            usage = {
                "prompt_tokens": response.usage_metadata.prompt_token_count,
                "completion_tokens": response.usage_metadata.candidates_token_count,
                "total_tokens": response.usage_metadata.total_token_count,
            }

        return Response(
            content=response.text,
            model=model,
            usage=usage if usage else None,
            finish_reason=str(response.candidates[0].finish_reason) if response.candidates else None,
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
        google_messages = self._convert_messages(messages)
        
        chat = self.model.start_chat(history=google_messages[:-1] if len(google_messages) > 1 else [])
        last_message = google_messages[-1]["parts"][0] if google_messages else ""
        
        response = chat.send_message(
            last_message,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
            stream=True,
        )

        for chunk in response:
            if chunk.text:
                yield StreamChunk(
                    content=chunk.text,
                    finish_reason=None,
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
        # Google SDK doesn't have native async, use sync version
        return self.complete(messages, model, temperature, max_tokens, **kwargs)

    async def astream(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """Async stream a completion."""
        # Google SDK doesn't have native async, use sync version
        for chunk in self.stream(messages, model, temperature, max_tokens, **kwargs):
            yield chunk
