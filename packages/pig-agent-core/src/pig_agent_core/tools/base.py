"""Core types and helpers for the agent tool system."""

import ipaddress
import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


@dataclass
class ToolResult:
    """Standardized tool result envelope with error handling.

    Attributes:
        ok: Whether the tool execution succeeded
        data: The result data (any type)
        error: Error message if execution failed
        meta: Additional metadata about the execution
    """

    ok: bool
    data: Any = None
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def serialize(self, max_chars: int = 4000) -> str:
        """Serialize result to JSON string with structure-aware truncation.

        Args:
            max_chars: Maximum character limit for the serialized output

        Returns:
            JSON string representation of the result
        """
        d: dict[str, Any] = {"ok": self.ok}
        if self.ok:
            d["data"] = self.data
        else:
            d["error"] = self.error

        payload = json.dumps(d, ensure_ascii=False, default=str)
        if len(payload) <= max_chars:
            return payload

        # Content-aware shrinking (preserves structure)
        if self.ok and self.data is not None:
            shrunk = _try_shrink(self.data, max_chars)
            if shrunk is not None:
                candidate = json.dumps(
                    {"ok": True, "data": shrunk}, ensure_ascii=False, default=str
                )
                if len(candidate) <= max_chars:
                    return candidate

        # Hard fallback (loses structure)
        if self.ok:
            wrapper = json.dumps(
                {"ok": True, "truncated": True, "data_preview": ""}, ensure_ascii=False
            )
            avail = max(0, max_chars - len(wrapper))
            fallback: dict[str, Any] = {
                "ok": True,
                "truncated": True,
                "data_preview": str(self.data)[:avail],
            }
        else:
            wrapper = json.dumps({"ok": False, "truncated": True, "error": ""}, ensure_ascii=False)
            avail = max(0, max_chars - len(wrapper))
            fallback = {"ok": False, "truncated": True, "error": str(self.error or "")[:avail]}

        return json.dumps(fallback, ensure_ascii=False, default=str)


class CancelledError(Exception):
    """Raised when the agent's cancel event fires during tool execution."""

    pass


# ---------------------------------------------------------------------------
# Structure-aware data shrinking
# ---------------------------------------------------------------------------


def _json_size(obj: Any) -> int:
    """Calculate JSON serialized size of an object."""
    return len(json.dumps(obj, ensure_ascii=False, default=str))


_TEXT_FIELD_NAMES = frozenset({"body", "content", "text", "selftext", "snippet", "methodology"})
_TEXT_FIELD_CAP = 200  # Default character limit for text field truncation
_COMPACT_RECURSION_MAX_DEPTH = 5  # Maximum recursion depth for nested list compaction


def _compact_items_text(items: list, cap: int = _TEXT_FIELD_CAP, depth: int = 0) -> list:
    """Truncate known text fields inside list-of-dict items to *cap* chars.

    Args:
        items: List of items to compact
        cap: Character limit for text fields
        depth: Current recursion depth (internal use)

    Returns:
        Compacted list with truncated text fields
    """
    if depth >= _COMPACT_RECURSION_MAX_DEPTH:
        return items

    out = []
    for item in items:
        if isinstance(item, dict):
            new_item = dict(item)
            for field_name in _TEXT_FIELD_NAMES:
                val = new_item.get(field_name)
                if isinstance(val, str) and len(val) > cap:
                    new_item[field_name] = val[:cap] + "…"
            # Recurse into nested lists (e.g. comment replies)
            for k, v in new_item.items():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    new_item[k] = _compact_items_text(v, cap, depth + 1)
            out.append(new_item)
        else:
            out.append(item)
    return out


def _try_shrink(data: Any, budget: int) -> Any | None:
    """Reduce *data* size while preserving as much structure as possible.

    Strategies applied in order:
      S0. List/dict items with text fields → truncate those fields first
          (preserves item count, reduces per-item size).
      S1. List → keep first N items that fit.
      S2. Dict with nested list → shrink that list.
      S3. Dict with long strings → truncate the longest values.

    Args:
        data: Data to shrink
        budget: Maximum character budget

    Returns:
        Smaller copy of data, or None when no strategy applies
    """
    target = budget - 30  # reserve room for {"ok":true,"data":}

    # S0: compact known text fields in list items before dropping items
    if isinstance(data, list) and data and isinstance(data[0], dict):
        compacted = _compact_items_text(data)
        if _json_size(compacted) <= target:
            return compacted
        data = compacted  # continue with compacted items for subsequent strategies
    elif isinstance(data, dict):
        # Check nested lists inside a dict wrapper
        modified = False
        result = dict(data)
        for key, val in data.items():
            if isinstance(val, list) and val and isinstance(val[0], dict):
                compacted_list = _compact_items_text(val)
                result[key] = compacted_list
                modified = True

        if modified:
            if _json_size(result) <= target:
                return result
            data = result  # continue with compacted data for subsequent strategies

    # S1: top-level list — drop tail items
    if isinstance(data, list):
        if len(data) <= 1:
            return None
        for n in range(len(data) - 1, 0, -1):
            if _json_size(data[:n]) <= target:
                return data[:n]
        return data[:1]

    if not isinstance(data, dict):
        return None

    result = dict(data)

    # S2: shrink the first nested list that's too large
    for key in list(result):
        val = result[key]
        if isinstance(val, list) and len(val) > 1:
            for n in range(len(val) - 1, 0, -1):
                temp = dict(result)
                temp[key] = val[:n]
                if _json_size(temp) <= target:
                    return temp
            temp = dict(result)
            temp[key] = val[:1]
            if _json_size(temp) <= target:
                return temp
            break

    if _json_size(result) <= target:
        return result

    # S3: trim long string values, longest first
    for key in sorted(result, key=lambda k: len(str(result[k])), reverse=True):
        val = result[key]
        if not isinstance(val, str) or len(val) <= 200:
            continue
        excess = _json_size(result) - target
        if excess <= 0:
            break
        new_len = max(200, len(val) - excess - 30)
        result[key] = val[:new_len] + "…[truncated]"

    return result if _json_size(result) <= target else None


# ---------------------------------------------------------------------------
# URL Validation (SSRF Protection)
# ---------------------------------------------------------------------------

# Blocked IP ranges for SSRF protection
_BLOCKED_IP_RANGES = [
    ipaddress.ip_network("0.0.0.0/8"),  # Current network
    ipaddress.ip_network("10.0.0.0/8"),  # Private
    ipaddress.ip_network("127.0.0.0/8"),  # Loopback
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local
    ipaddress.ip_network("172.16.0.0/12"),  # Private
    ipaddress.ip_network("192.168.0.0/16"),  # Private
    ipaddress.ip_network("224.0.0.0/4"),  # Multicast
    ipaddress.ip_network("240.0.0.0/4"),  # Reserved
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
    ipaddress.ip_network("fc00::/7"),  # IPv6 private
]

# Cloud metadata endpoints
_METADATA_ENDPOINTS = {
    "169.254.169.254",  # AWS, Azure, GCP
    "metadata.google.internal",
    "169.254.169.253",  # Azure (alternative)
}


class URLValidationError(Exception):
    """Raised when URL validation fails."""

    pass


def validate_url(url: str, allow_private: bool = False) -> str:
    """Validate URL to prevent SSRF attacks.

    Blocks:
    - Private IP addresses (10.x, 192.168.x, 127.x, etc.)
    - Cloud metadata endpoints (169.254.169.254, etc.)
    - Non-HTTP/HTTPS schemes
    - Localhost and link-local addresses

    Args:
        url: URL to validate
        allow_private: If True, allow private IPs (for testing)

    Returns:
        The validated URL

    Raises:
        URLValidationError: If URL is blocked

    Examples:
        >>> validate_url("https://example.com")
        'https://example.com'
        >>> validate_url("http://localhost")  # doctest: +SKIP
        URLValidationError: Blocked hostname: localhost
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise URLValidationError(f"Invalid URL format: {e}") from e

    # Check scheme
    if parsed.scheme not in ("http", "https"):
        raise URLValidationError(f"Blocked scheme: {parsed.scheme}. Only http/https allowed.")

    hostname = parsed.hostname
    if not hostname:
        raise URLValidationError("URL must have a hostname")

    # Check for localhost
    if hostname.lower() in ("localhost", "0.0.0.0"):
        if not allow_private:
            raise URLValidationError(f"Blocked hostname: {hostname}")
        return url

    # Check for metadata endpoints
    if hostname in _METADATA_ENDPOINTS:
        raise URLValidationError(f"Blocked metadata endpoint: {hostname}")

    # Try to resolve hostname to IP
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        # Not a direct IP, could be a domain name
        # In production, you'd want to resolve DNS and check the IP
        # For now, we'll allow domain names and rely on post-redirect validation
        return url

    # Check if IP is in blocked ranges
    if not allow_private:
        for blocked_range in _BLOCKED_IP_RANGES:
            if ip in blocked_range:
                raise URLValidationError(f"Blocked IP address: {ip} (in {blocked_range})")

    return url


def validate_redirect_url(original_url: str, redirect_url: str, allow_private: bool = False) -> str:
    """Validate redirect URL to prevent SSRF via redirects.

    This should be called after following a redirect to ensure
    the redirect target is also safe.

    Args:
        original_url: Original URL that was requested
        redirect_url: URL that the server redirected to
        allow_private: If True, allow private IPs (for testing)

    Returns:
        The validated redirect URL

    Raises:
        URLValidationError: If redirect URL is blocked

    Examples:
        >>> validate_redirect_url("https://example.com", "https://other.com")
        'https://other.com'
    """
    # Validate the redirect URL with same rules
    return validate_url(redirect_url, allow_private=allow_private)
