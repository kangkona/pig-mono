"""Tests for authentication system."""

import pytest
from pathlib import Path
from datetime import datetime, timedelta
from pig_agent_core.auth import AuthManager, OAuthProvider, TokenInfo, OAuthFlow


@pytest.fixture
def temp_auth_storage(tmp_path):
    """Create temporary auth storage."""
    return tmp_path / "auth.json"


def test_token_info_creation():
    """Test creating token info."""
    token = TokenInfo(
        access_token="test-token",
        token_type="Bearer",
    )
    
    assert token.access_token == "test-token"
    assert token.token_type == "Bearer"


def test_token_info_with_expiry():
    """Test token info with expiration."""
    expires_at = datetime.utcnow() + timedelta(hours=1)
    
    token = TokenInfo(
        access_token="test-token",
        expires_at=expires_at,
    )
    
    assert token.expires_at == expires_at


def test_oauth_provider_creation():
    """Test creating OAuth provider."""
    provider = OAuthProvider(
        name="test",
        client_id="test-id",
        auth_url="https://auth.example.com",
        token_url="https://token.example.com",
    )
    
    assert provider.name == "test"
    assert provider.client_id == "test-id"


def test_auth_manager_creation(temp_auth_storage):
    """Test creating auth manager."""
    auth_mgr = AuthManager(temp_auth_storage)
    
    assert auth_mgr.storage_path == temp_auth_storage
    assert len(auth_mgr.tokens) == 0


def test_auth_manager_save_load(temp_auth_storage):
    """Test saving and loading tokens."""
    auth_mgr = AuthManager(temp_auth_storage)
    
    # Add token
    token = TokenInfo(access_token="test-token")
    auth_mgr.tokens["test-provider"] = token
    auth_mgr._save_tokens()
    
    # Load in new instance
    auth_mgr2 = AuthManager(temp_auth_storage)
    
    assert "test-provider" in auth_mgr2.tokens
    assert auth_mgr2.tokens["test-provider"].access_token == "test-token"


def test_auth_manager_get_token(temp_auth_storage):
    """Test getting token."""
    auth_mgr = AuthManager(temp_auth_storage)
    
    token = TokenInfo(access_token="test-token")
    auth_mgr.tokens["test"] = token
    
    retrieved = auth_mgr.get_token("test")
    assert retrieved == "test-token"


def test_auth_manager_get_missing_token(temp_auth_storage):
    """Test getting non-existent token."""
    auth_mgr = AuthManager(temp_auth_storage)
    
    retrieved = auth_mgr.get_token("missing")
    assert retrieved is None


def test_auth_manager_expired_token(temp_auth_storage):
    """Test expired token."""
    auth_mgr = AuthManager(temp_auth_storage)
    
    # Create expired token
    expires_at = datetime.utcnow() - timedelta(hours=1)
    token = TokenInfo(access_token="expired", expires_at=expires_at)
    auth_mgr.tokens["test"] = token
    
    retrieved = auth_mgr.get_token("test")
    assert retrieved is None  # Should return None for expired


def test_auth_manager_logout(temp_auth_storage):
    """Test logout."""
    auth_mgr = AuthManager(temp_auth_storage)
    
    token = TokenInfo(access_token="test")
    auth_mgr.tokens["test"] = token
    
    assert "test" in auth_mgr.tokens
    
    result = auth_mgr.logout("test")
    
    assert result is True
    assert "test" not in auth_mgr.tokens


def test_auth_manager_is_logged_in(temp_auth_storage):
    """Test checking login status."""
    auth_mgr = AuthManager(temp_auth_storage)
    
    assert not auth_mgr.is_logged_in("test")
    
    token = TokenInfo(access_token="test")
    auth_mgr.tokens["test"] = token
    
    assert auth_mgr.is_logged_in("test")


def test_auth_manager_list_providers(temp_auth_storage):
    """Test listing providers."""
    auth_mgr = AuthManager(temp_auth_storage)
    
    auth_mgr.tokens["provider1"] = TokenInfo(access_token="token1")
    auth_mgr.tokens["provider2"] = TokenInfo(access_token="token2")
    
    providers = auth_mgr.list_providers()
    
    assert len(providers) == 2
    assert "provider1" in providers
    assert "provider2" in providers


def test_oauth_flow_creation():
    """Test creating OAuth flow."""
    provider = OAuthProvider(
        name="test",
        client_id="id",
        auth_url="https://auth.test",
        token_url="https://token.test",
    )
    
    flow = OAuthFlow(provider)
    
    assert flow.provider == provider
    assert flow.state  # Should generate random state
