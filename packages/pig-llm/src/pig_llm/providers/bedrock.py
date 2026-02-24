"""Amazon Bedrock provider implementation."""

from typing import AsyncIterator, Iterator, Optional
import json

try:
    import boto3
    from botocore.config import Config as BotoConfig
except ImportError:
    raise ImportError("boto3 is required for Bedrock. Install with: pip install boto3")

from ..config import Config
from ..models import Message, Response, StreamChunk
from ._base import Provider


class BedrockProvider(Provider):
    """Amazon Bedrock provider implementation."""

    def __init__(self, config: Config):
        """Initialize Bedrock provider.
        
        Note: Bedrock uses AWS credentials from environment or ~/.aws/credentials
        api_key can be used to pass AWS region (default: us-east-1)
        """
        self.config = config
        self.region = config.api_key or "us-east-1"
        
        boto_config = BotoConfig(
            read_timeout=config.timeout,
            retries={"max_attempts": config.max_retries},
        )
        
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=self.region,
            config=boto_config,
        )

    def _convert_messages(self, messages: list[Message]) -> tuple[str, list[dict]]:
        """Convert internal messages to Bedrock format.
        
        Returns:
            Tuple of (system_prompt, messages_list)
        """
        system_prompt = ""
        converted = []
        
        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            else:
                converted.append({
                    "role": msg.role,
                    "content": [{"text": msg.content}]
                })
        
        return system_prompt, converted

    def _build_request_body(
        self,
        messages: list[Message],
        model: str,
        temperature: float,
        max_tokens: Optional[int],
    ) -> dict:
        """Build request body for Bedrock."""
        system_prompt, converted_messages = self._convert_messages(messages)
        
        body = {
            "messages": converted_messages,
            "inferenceConfig": {
                "temperature": temperature,
            }
        }
        
        if max_tokens:
            body["inferenceConfig"]["maxTokens"] = max_tokens
        
        if system_prompt:
            body["system"] = [{"text": system_prompt}]
        
        return body

    def complete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Response:
        """Generate a completion."""
        body = self._build_request_body(messages, model, temperature, max_tokens)
        
        response = self.client.converse(
            modelId=model,
            **body,
        )
        
        output = response["output"]["message"]
        content = output["content"][0]["text"]
        
        usage = response.get("usage", {})
        usage_dict = {
            "prompt_tokens": usage.get("inputTokens", 0),
            "completion_tokens": usage.get("outputTokens", 0),
            "total_tokens": usage.get("totalTokens", 0),
        }
        
        return Response(
            content=content,
            model=model,
            usage=usage_dict,
            finish_reason=response.get("stopReason", "stop"),
            metadata={"request_id": response["ResponseMetadata"]["RequestId"]},
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
        body = self._build_request_body(messages, model, temperature, max_tokens)
        
        response = self.client.converse_stream(
            modelId=model,
            **body,
        )
        
        stream = response.get("stream")
        if stream:
            for event in stream:
                if "contentBlockDelta" in event:
                    delta = event["contentBlockDelta"]["delta"]
                    if "text" in delta:
                        yield StreamChunk(
                            content=delta["text"],
                            finish_reason=None,
                            metadata={},
                        )
                elif "messageStop" in event:
                    stop_reason = event["messageStop"].get("stopReason", "stop")
                    yield StreamChunk(
                        content="",
                        finish_reason=stop_reason,
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
        """Async generate a completion.
        
        Note: Bedrock doesn't have native async support, this uses sync client.
        For true async, use aioboto3 library.
        """
        # For now, use sync client (true async would require aioboto3)
        return self.complete(messages, model, temperature, max_tokens, **kwargs)

    async def astream(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """Async stream a completion.
        
        Note: Bedrock doesn't have native async support, this uses sync client.
        For true async, use aioboto3 library.
        """
        # For now, use sync client (true async would require aioboto3)
        for chunk in self.stream(messages, model, temperature, max_tokens, **kwargs):
            yield chunk
