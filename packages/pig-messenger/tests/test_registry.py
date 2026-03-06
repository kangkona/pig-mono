"""Tests for messenger adapter registry."""

from pig_messenger.base import BaseMessengerAdapter, IncomingMessage, MessengerType
from pig_messenger.registry import MessengerRegistry


class MockSlackAdapter(BaseMessengerAdapter):
    """Mock Slack adapter for testing."""

    async def send_message(
        self, channel_id: str, text: str, *, thread_id: str | None = None, **kwargs
    ) -> str:
        return "msg_1"

    async def update_message(self, channel_id: str, message_id: str, text: str, **kwargs) -> None:
        pass

    def parse_event(self, raw_event: dict) -> IncomingMessage | None:
        return None

    def verify_signature(self, request_body: bytes, signature: str, **kwargs) -> bool:
        return True


class MockTelegramAdapter(BaseMessengerAdapter):
    """Mock Telegram adapter for testing."""

    async def send_message(
        self, channel_id: str, text: str, *, thread_id: str | None = None, **kwargs
    ) -> str:
        return "msg_2"

    async def update_message(self, channel_id: str, message_id: str, text: str, **kwargs) -> None:
        pass

    def parse_event(self, raw_event: dict) -> IncomingMessage | None:
        return None

    def verify_signature(self, request_body: bytes, signature: str, **kwargs) -> bool:
        return True


def test_register_adapter():
    """Test registering an adapter."""
    MessengerRegistry.clear_all()

    @MessengerRegistry.register(MessengerType.SLACK)
    class TestAdapter(MockSlackAdapter):
        pass

    assert MessengerRegistry.is_registered(MessengerType.SLACK)
    assert MessengerRegistry.get_class(MessengerType.SLACK) == TestAdapter


def test_get_class():
    """Test getting adapter class."""
    MessengerRegistry.clear_all()
    MessengerRegistry.register(MessengerType.SLACK)(MockSlackAdapter)

    adapter_class = MessengerRegistry.get_class(MessengerType.SLACK)
    assert adapter_class == MockSlackAdapter

    # Non-existent type
    assert MessengerRegistry.get_class(MessengerType.DISCORD) is None


def test_get_instance():
    """Test getting adapter instance."""
    MessengerRegistry.clear_all()
    MessengerRegistry.register(MessengerType.TELEGRAM)(MockTelegramAdapter)

    instance = MessengerRegistry.get_instance(MessengerType.TELEGRAM)
    assert isinstance(instance, MockTelegramAdapter)

    # Non-existent type
    assert MessengerRegistry.get_instance(MessengerType.WHATSAPP) is None


def test_all_types():
    """Test getting all registered types."""
    MessengerRegistry.clear_all()
    MessengerRegistry.register(MessengerType.SLACK)(MockSlackAdapter)
    MessengerRegistry.register(MessengerType.TELEGRAM)(MockTelegramAdapter)

    types = MessengerRegistry.all_types()
    assert len(types) == 2
    assert MessengerType.SLACK in types
    assert MessengerType.TELEGRAM in types


def test_is_registered():
    """Test checking if type is registered."""
    MessengerRegistry.clear_all()
    MessengerRegistry.register(MessengerType.SLACK)(MockSlackAdapter)

    assert MessengerRegistry.is_registered(MessengerType.SLACK) is True
    assert MessengerRegistry.is_registered(MessengerType.DISCORD) is False


def test_clear_all():
    """Test clearing all registrations."""
    MessengerRegistry.clear_all()
    MessengerRegistry.register(MessengerType.SLACK)(MockSlackAdapter)
    MessengerRegistry.register(MessengerType.TELEGRAM)(MockTelegramAdapter)

    assert len(MessengerRegistry.all_types()) == 2

    MessengerRegistry.clear_all()
    assert len(MessengerRegistry.all_types()) == 0


def test_multiple_registrations():
    """Test registering multiple adapters."""
    MessengerRegistry.clear_all()

    @MessengerRegistry.register(MessengerType.SLACK)
    class Adapter1(MockSlackAdapter):
        pass

    @MessengerRegistry.register(MessengerType.TELEGRAM)
    class Adapter2(MockTelegramAdapter):
        pass

    assert MessengerRegistry.is_registered(MessengerType.SLACK)
    assert MessengerRegistry.is_registered(MessengerType.TELEGRAM)
    assert MessengerRegistry.get_class(MessengerType.SLACK) == Adapter1
    assert MessengerRegistry.get_class(MessengerType.TELEGRAM) == Adapter2
