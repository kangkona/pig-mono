"""Tool schemas for web tools."""

from typing import Any


def _fn(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    """Helper to build OpenAI function calling schema.

    Args:
        name: Function name
        description: Function description
        parameters: Parameters schema

    Returns:
        OpenAI function calling schema
    """
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
            "strict": True,
        },
    }


# Search web tool schema
SEARCH_WEB_SCHEMA = _fn(
    name="search_web",
    description=(
        "Search the web for information using Tavily API. "
        "Returns a list of search results with titles, URLs, and snippets."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default: 5)",
                "default": 5,
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
)

# Read webpage tool schema
READ_WEBPAGE_SCHEMA = _fn(
    name="read_webpage",
    description=(
        "Read and extract text content from a webpage. Returns the main text content of the page."
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL of the webpage to read",
            },
        },
        "required": ["url"],
        "additionalProperties": False,
    },
)

# All web tool schemas
TOOL_SCHEMAS = [
    SEARCH_WEB_SCHEMA,
    READ_WEBPAGE_SCHEMA,
]
