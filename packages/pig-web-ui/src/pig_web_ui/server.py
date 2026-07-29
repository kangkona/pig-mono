"""Chat server with FastAPI."""

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from fastapi import FastAPI, File, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .models import ChatMessage, ChatRequest, StreamChunk


class ContentResponse(Protocol):
    """Response shape shared by supported LLM and agent clients."""

    content: str


class CompletionClient(Protocol):
    """Minimum non-streaming interface required by the web server."""

    def complete(self, prompt: str) -> ContentResponse: ...


@runtime_checkable
class StreamingClient(Protocol):
    """Optional streaming interface detected at runtime."""

    def stream(self, prompt: str) -> Iterator[ContentResponse]: ...


class AgentClient(Protocol):
    """Minimum agent interface required by the web server."""

    def run(self, message: str) -> ContentResponse: ...

    def clear_history(self) -> None: ...


class ChatServer:
    """Chat server with web UI."""

    def __init__(
        self,
        llm: CompletionClient | None = None,
        agent: AgentClient | None = None,
        title: str = "Chat",
        port: int = 8000,
        host: str = "127.0.0.1",
        cors: bool = False,
        theme: dict[str, str] | None = None,
    ) -> None:
        """Initialize chat server.

        Args:
            llm: LLM instance (from py-ai)
            agent: Agent instance (from py-agent-core)
            title: Page title
            port: Server port
            host: Server host
            cors: Enable CORS
            theme: UI theme customization
        """
        if not llm and not agent:
            raise ValueError("Must provide either llm or agent")

        self.llm = llm
        self.agent = agent
        self.title = title
        self.port = port
        self.host = host
        self.theme = theme or {}

        # Create FastAPI app
        self.app = FastAPI(title=title)

        # Enable CORS if requested
        if cors:
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )

        # Setup templates and static files
        self.base_dir = Path(__file__).parent
        self.templates = Jinja2Templates(directory=str(self.base_dir / "templates"))
        self.app.mount(
            "/static",
            StaticFiles(directory=str(self.base_dir / "static")),
            name="static",
        )

        # Conversation history
        self.history: list[ChatMessage] = []

        # Setup routes
        self._setup_routes()

    def _setup_routes(self) -> None:
        """Setup API routes."""

        @self.app.get("/", response_class=HTMLResponse)
        async def home(request: Request) -> Response:
            """Serve chat UI."""
            return self.templates.TemplateResponse(
                request,
                "chat.html",
                context={
                    "request": request,
                    "title": self.title,
                    "theme": self.theme,
                },
            )

        @self.app.post("/api/chat")
        async def chat(request: ChatRequest) -> StreamingResponse:
            """Handle chat message with SSE streaming."""
            return StreamingResponse(
                self._stream_response(request.message),
                media_type="text/event-stream",
            )

        @self.app.get("/api/history")
        async def get_history() -> dict[str, object]:
            """Get chat history."""
            return {"messages": [msg.model_dump() for msg in self.history]}

        @self.app.delete("/api/history")
        async def clear_history() -> dict[str, str]:
            """Clear chat history."""
            self.history.clear()
            if self.agent:
                self.agent.clear_history()
            return {"status": "ok"}

        @self.app.post("/api/upload")
        async def upload_file(file: UploadFile = File(...)) -> dict[str, str | int]:
            """Handle file upload."""
            try:
                content = await file.read()
                filename = file.filename
                if filename is None:
                    raise ValueError("Uploaded file must have a filename")

                # Store uploaded file (simplified - production would store properly)
                upload_dir = Path(".uploads")
                upload_dir.mkdir(exist_ok=True)

                file_path = upload_dir / filename
                file_path.write_bytes(content)

                return {
                    "status": "ok",
                    "filename": filename,
                    "size": len(content),
                    "path": str(file_path),
                }
            except Exception as e:
                return {"status": "error", "error": str(e)}

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket) -> None:
            """WebSocket endpoint for real-time chat."""
            await websocket.accept()

            try:
                while True:
                    # Receive message
                    data = await websocket.receive_json()
                    message = data.get("message", "")

                    if not message:
                        continue

                    # Add to history
                    self.history.append(ChatMessage(role="user", content=message))

                    # Send acknowledgment
                    await websocket.send_json({"type": "received"})

                    # Get response
                    if self.agent:
                        response = self.agent.run(message)
                        content = response.content
                    elif self.llm:
                        # Check if streaming
                        if isinstance(self.llm, StreamingClient):
                            # Stream via WebSocket
                            full_content = ""
                            for chunk in self.llm.stream(message):
                                await websocket.send_json(
                                    {
                                        "type": "token",
                                        "content": chunk.content,
                                    }
                                )
                                full_content += chunk.content
                            content = full_content
                        else:
                            response = self.llm.complete(message)
                            content = response.content
                            await websocket.send_json(
                                {
                                    "type": "token",
                                    "content": content,
                                }
                            )
                    else:
                        content = "No LLM configured"
                        await websocket.send_json(
                            {
                                "type": "token",
                                "content": content,
                            }
                        )

                    # Add to history
                    if content:
                        self.history.append(ChatMessage(role="assistant", content=content))

                    # Send done
                    await websocket.send_json({"type": "done"})

            except WebSocketDisconnect:
                pass
            except Exception as e:
                await websocket.send_json({"type": "error", "error": str(e)})

    async def _stream_response(self, message: str) -> AsyncIterator[str]:
        """Stream response as SSE.

        Args:
            message: User message

        Yields:
            SSE formatted chunks
        """
        # Add user message to history
        self.history.append(ChatMessage(role="user", content=message))

        try:
            # Send start event
            yield self._format_sse(StreamChunk(type="start"))

            # Get response
            if self.agent:
                # Use agent
                response = self.agent.run(message)
                content = response.content
            elif self.llm:
                # Use LLM directly - check if streaming is supported
                if isinstance(self.llm, StreamingClient):
                    # Stream tokens
                    for chunk in self.llm.stream(message):
                        yield self._format_sse(StreamChunk(type="token", content=chunk.content))
                        await asyncio.sleep(0)  # Allow event loop to process

                    # Get full content from history if available
                    content = ""  # Stream already sent content
                else:
                    # No streaming, get complete response
                    response = self.llm.complete(message)
                    content = response.content
                    # Send as single token
                    yield self._format_sse(StreamChunk(type="token", content=content))
            else:
                content = "No LLM or agent configured"
                yield self._format_sse(StreamChunk(type="token", content=content))

            # Add assistant message to history
            if content:  # Only add if we have content
                self.history.append(ChatMessage(role="assistant", content=content))

            # Send done event
            yield self._format_sse(StreamChunk(type="done"))

        except Exception as e:
            # Send error event
            yield self._format_sse(StreamChunk(type="error", error=str(e)))

    def _format_sse(self, chunk: StreamChunk) -> str:
        """Format chunk as SSE.

        Args:
            chunk: Stream chunk

        Returns:
            SSE formatted string
        """
        return f"data: {chunk.model_dump_json()}\n\n"

    def run(self, **kwargs: Any) -> None:
        """Run the server.

        Args:
            **kwargs: Arguments for uvicorn.run
        """
        import uvicorn

        uvicorn.run(
            self.app,
            host=kwargs.get("host", self.host),
            port=kwargs.get("port", self.port),
            **{k: v for k, v in kwargs.items() if k not in ["host", "port"]},
        )
