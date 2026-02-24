"""Authentication and OAuth management."""

import json
import secrets
import webbrowser
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, parse_qs
import threading

from pydantic import BaseModel


class TokenInfo(BaseModel):
    """OAuth token information."""

    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_at: Optional[datetime] = None
    scope: Optional[str] = None


class OAuthProvider(BaseModel):
    """OAuth provider configuration."""

    name: str
    client_id: str
    client_secret: Optional[str] = None
    auth_url: str
    token_url: str
    redirect_uri: str = "http://localhost:8765/callback"
    scope: str = ""


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth callback."""

    auth_code = None

    def do_GET(self):
        """Handle GET request."""
        if self.path.startswith("/callback"):
            # Parse query params
            query = self.path.split("?", 1)[1] if "?" in self.path else ""
            params = parse_qs(query)

            if "code" in params:
                OAuthCallbackHandler.auth_code = params["code"][0]
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(
                    """
                    <html>
                    <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                        <h1 style="color: green;">&#10003; Authentication Successful!</h1>
                        <p>You can close this window and return to the terminal.</p>
                    </body>
                    </html>
                    """.encode()
                )
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Error: No authorization code")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress log messages."""
        pass


class OAuthFlow:
    """OAuth 2.0 authorization flow."""

    def __init__(self, provider: OAuthProvider):
        """Initialize OAuth flow.

        Args:
            provider: OAuth provider configuration
        """
        self.provider = provider
        self.state = secrets.token_urlsafe(32)

    def start_flow(self) -> Optional[str]:
        """Start OAuth flow and return authorization code.

        Returns:
            Authorization code or None if failed
        """
        # Build authorization URL
        params = {
            "client_id": self.provider.client_id,
            "redirect_uri": self.provider.redirect_uri,
            "response_type": "code",
            "scope": self.provider.scope,
            "state": self.state,
        }

        auth_url = f"{self.provider.auth_url}?{urlencode(params)}"

        print(f"\n🔐 Opening browser for authentication...")
        print(f"Provider: {self.provider.name}")
        print(f"Redirect: {self.provider.redirect_uri}")
        print()

        # Start local server to receive callback
        server = HTTPServer(("localhost", 8765), OAuthCallbackHandler)

        # Open browser
        webbrowser.open(auth_url)

        print("Waiting for authentication...")
        print("(If browser doesn't open, visit this URL manually:)")
        print(f"  {auth_url}")
        print()

        # Wait for callback (with timeout)
        server_thread = threading.Thread(target=server.handle_request)
        server_thread.daemon = True
        server_thread.start()
        server_thread.join(timeout=120)  # 2 minute timeout

        auth_code = OAuthCallbackHandler.auth_code
        OAuthCallbackHandler.auth_code = None  # Reset

        if not auth_code:
            print("❌ Authentication timeout or failed")
            return None

        print("✓ Authorization code received")
        return auth_code

    def exchange_code(self, code: str) -> Optional[TokenInfo]:
        """Exchange authorization code for access token.

        Args:
            code: Authorization code

        Returns:
            Token info or None if failed
        """
        import httpx

        payload = {
            "client_id": self.provider.client_id,
            "client_secret": self.provider.client_secret,
            "code": code,
            "redirect_uri": self.provider.redirect_uri,
            "grant_type": "authorization_code",
        }

        try:
            response = httpx.post(
                self.provider.token_url, data=payload, timeout=30
            )
            response.raise_for_status()

            data = response.json()

            # Calculate expiration
            expires_in = data.get("expires_in")
            expires_at = None
            if expires_in:
                expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

            return TokenInfo(
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token"),
                token_type=data.get("token_type", "Bearer"),
                expires_at=expires_at,
                scope=data.get("scope"),
            )

        except Exception as e:
            print(f"❌ Token exchange failed: {e}")
            return None


class AuthManager:
    """Manages authentication for multiple providers."""

    def __init__(self, storage_path: Optional[Path] = None):
        """Initialize auth manager.

        Args:
            storage_path: Path to store tokens (default: ~/.agents/auth.json)
        """
        if storage_path is None:
            storage_path = Path.home() / ".agents" / "auth.json"

        self.storage_path = storage_path
        self.tokens: Dict[str, TokenInfo] = {}
        self._load_tokens()

    def _load_tokens(self) -> None:
        """Load tokens from storage."""
        if not self.storage_path.exists():
            return

        try:
            data = json.loads(self.storage_path.read_text())
            for provider, token_data in data.items():
                self.tokens[provider] = TokenInfo(**token_data)
        except Exception as e:
            print(f"Warning: Failed to load tokens: {e}")

    def _save_tokens(self) -> None:
        """Save tokens to storage."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            provider: token.model_dump(mode="json")
            for provider, token in self.tokens.items()
        }

        self.storage_path.write_text(json.dumps(data, indent=2, default=str))

    def login(self, provider: OAuthProvider) -> bool:
        """Login to a provider via OAuth.

        Args:
            provider: OAuth provider config

        Returns:
            True if successful
        """
        flow = OAuthFlow(provider)

        # Get authorization code
        code = flow.start_flow()
        if not code:
            return False

        # Exchange for token
        token = flow.exchange_code(code)
        if not token:
            return False

        # Store token
        self.tokens[provider.name] = token
        self._save_tokens()

        print(f"✓ Successfully logged in to {provider.name}")
        return True

    def logout(self, provider_name: str) -> bool:
        """Logout from a provider.

        Args:
            provider_name: Provider name

        Returns:
            True if successful
        """
        if provider_name in self.tokens:
            del self.tokens[provider_name]
            self._save_tokens()
            print(f"✓ Logged out from {provider_name}")
            return True

        print(f"Not logged in to {provider_name}")
        return False

    def get_token(self, provider_name: str) -> Optional[str]:
        """Get access token for a provider.

        Args:
            provider_name: Provider name

        Returns:
            Access token or None
        """
        token_info = self.tokens.get(provider_name)
        if not token_info:
            return None

        # Check if expired
        if token_info.expires_at and token_info.expires_at < datetime.utcnow():
            # TODO: Implement token refresh
            print(f"⚠️  Token for {provider_name} expired")
            return None

        return token_info.access_token

    def is_logged_in(self, provider_name: str) -> bool:
        """Check if logged in to a provider.

        Args:
            provider_name: Provider name

        Returns:
            True if logged in and token valid
        """
        return self.get_token(provider_name) is not None

    def list_providers(self) -> list[str]:
        """List providers with active authentication.

        Returns:
            List of provider names
        """
        return list(self.tokens.keys())
