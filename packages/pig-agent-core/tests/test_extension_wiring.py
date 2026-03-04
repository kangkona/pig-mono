"""Tests for extension protocol wiring and exports."""


def test_all_exports_available():
    """Test that all new subsystems are exported from __init__.py."""
    import pig_agent_core

    # Core
    assert hasattr(pig_agent_core, "Agent")
    assert hasattr(pig_agent_core, "Tool")

    # Memory
    assert hasattr(pig_agent_core, "MemoryProvider")
    assert hasattr(pig_agent_core, "InMemoryProvider")
    assert hasattr(pig_agent_core, "Message")

    # Context
    assert hasattr(pig_agent_core, "ContextLoader")
    assert hasattr(pig_agent_core, "SystemPromptBuilder")
    assert hasattr(pig_agent_core, "CompressionConfig")
    assert hasattr(pig_agent_core, "compress_messages")

    # Observability
    assert hasattr(pig_agent_core, "AgentEvent")
    assert hasattr(pig_agent_core, "AgentEventType")
    assert hasattr(pig_agent_core, "BillingHook")
    assert hasattr(pig_agent_core, "emit_profile_rotated")
    assert hasattr(pig_agent_core, "emit_context_compressed")
    assert hasattr(pig_agent_core, "emit_model_fallback")

    # Resilience
    assert hasattr(pig_agent_core, "ProfileManager")
    assert hasattr(pig_agent_core, "FailoverReason")
    assert hasattr(pig_agent_core, "classify_failure")
    assert hasattr(pig_agent_core, "resilient_call")
    assert hasattr(pig_agent_core, "resilient_streaming_call")
    assert hasattr(pig_agent_core, "ResilienceExhaustedError")

    # Token counting
    assert hasattr(pig_agent_core, "count_tokens")

    # Tool system
    assert hasattr(pig_agent_core, "EnhancedToolRegistry")
    assert hasattr(pig_agent_core, "EnhancedToolResult")
    assert hasattr(pig_agent_core, "ToolAuditLog")
    assert hasattr(pig_agent_core, "ToolMetrics")
    assert hasattr(pig_agent_core, "ToolMetricsCollector")


def test_version_matches_pyproject():
    """Test that __version__ matches pyproject.toml."""
    import pig_agent_core

    assert pig_agent_core.__version__ == "0.0.4"


def test_memory_provider_protocol():
    """Test that MemoryProvider protocol can be imported and used."""
    from pig_agent_core import InMemoryProvider

    # InMemoryProvider should implement MemoryProvider protocol
    provider = InMemoryProvider()
    assert hasattr(provider, "get_messages")
    assert hasattr(provider, "add_message")
    assert hasattr(provider, "clear_messages")


def test_billing_hook_protocol():
    """Test that BillingHook protocol can be imported."""
    from pig_agent_core import BillingHook

    # Check protocol has required methods
    assert hasattr(BillingHook, "on_llm_call")
    assert hasattr(BillingHook, "on_tool_call")
    assert hasattr(BillingHook, "get_usage_summary")


def test_context_loader_protocol():
    """Test that ContextLoader protocol can be imported."""
    from pig_agent_core import ContextLoader

    # Check protocol has required method
    assert hasattr(ContextLoader, "load_context")


def test_system_prompt_builder_protocol():
    """Test that SystemPromptBuilder protocol can be imported."""
    from pig_agent_core import SystemPromptBuilder

    # Check protocol has required method
    assert hasattr(SystemPromptBuilder, "build_prompt")


def test_agent_accepts_all_protocols():
    """Test that Agent constructor accepts all protocol parameters."""
    from unittest.mock import Mock

    from pig_agent_core import Agent

    mock_llm = Mock()
    mock_llm.config.model = "gpt-4"

    # Create agent with all protocol parameters
    agent = Agent(
        llm=mock_llm,
        profile_manager=Mock(),
        event_callback=Mock(),
        compress_fn=Mock(),
        memory_provider=Mock(),
        system_prompt_builder=Mock(),
        billing_hook=Mock(),
        max_rounds=10,
        max_rounds_with_plan=20,
    )

    assert agent.profile_manager is not None
    assert agent.event_callback is not None
    assert agent.compress_fn is not None
    assert agent.memory_provider is not None
    assert agent.system_prompt_builder is not None
    assert agent.billing_hook is not None


def test_enhanced_tool_registry_available():
    """Test that enhanced ToolRegistry is available."""
    from pig_agent_core import EnhancedToolRegistry

    registry = EnhancedToolRegistry()
    assert hasattr(registry, "register")
    assert hasattr(registry, "execute")
    assert hasattr(registry, "execute_batch")


def test_resilience_components_available():
    """Test that resilience components are available."""
    from pig_agent_core import FailoverReason, ProfileManager, classify_failure

    # Test FailoverReason enum
    assert hasattr(FailoverReason, "AUTH")
    assert hasattr(FailoverReason, "RATE_LIMIT")
    assert hasattr(FailoverReason, "BILLING")
    assert hasattr(FailoverReason, "TIMEOUT")
    assert hasattr(FailoverReason, "CONTEXT_OVERFLOW")

    # Test classify_failure function
    assert callable(classify_failure)

    # Test ProfileManager
    manager = ProfileManager()
    assert hasattr(manager, "add_profile")
    assert hasattr(manager, "get_next_profile")


def test_token_counter_available():
    """Test that token counter is available."""
    from pig_agent_core import count_tokens

    assert callable(count_tokens)

    # Test basic functionality
    tokens = count_tokens("Hello world")
    assert tokens > 0


def test_audit_and_metrics_available():
    """Test that audit and metrics are available."""
    from pig_agent_core import ToolAuditLog, ToolMetricsCollector

    # Test ToolAuditLog
    audit_log = ToolAuditLog()
    assert hasattr(audit_log, "log")
    assert hasattr(audit_log, "get_entries")
    assert hasattr(audit_log, "export_json")

    # Test ToolMetricsCollector
    collector = ToolMetricsCollector()
    assert hasattr(collector, "record")
    assert hasattr(collector, "get_metrics")
    assert hasattr(collector, "get_summary")
