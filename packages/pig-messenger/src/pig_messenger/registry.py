"""Decorator-based adapter registry for platform adapters."""

from typing import Any

from .base import BaseMessengerAdapter, MessengerType


class MessengerRegistry:
    """Registry for messenger platform adapters."""

    _adapters: dict[MessengerType, type[BaseMessengerAdapter]] = {}

    @classmethod
    def register(cls, messenger_type: MessengerType):
        """Decorator to register an adapter class.

        Args:
            messenger_type: Platform type

        Returns:
            Decorator function

        Example:
            @MessengerRegistry.register(MessengerType.SLACK)
            class SlackAdapter(BaseMessengerAdapter):
                pass
        """

        def decorator(adapter_class: type[BaseMessengerAdapter]):
            cls._adapters[messenger_type] = adapter_class
            return adapter_class

        return decorator

    @classmethod
    def get_class(cls, messenger_type: MessengerType) -> type[BaseMessengerAdapter] | None:
        """Get adapter class by type.

        Args:
            messenger_type: Platform type

        Returns:
            Adapter class or None if not registered
        """
        return cls._adapters.get(messenger_type)

    @classmethod
    def get_instance(
        cls, messenger_type: MessengerType, *args: Any, **kwargs: Any
    ) -> BaseMessengerAdapter | None:
        """Get adapter instance by type.

        Args:
            messenger_type: Platform type
            *args: Positional arguments for adapter constructor
            **kwargs: Keyword arguments for adapter constructor

        Returns:
            Adapter instance or None if not registered
        """
        adapter_class = cls.get_class(messenger_type)
        if adapter_class:
            return adapter_class(*args, **kwargs)
        return None

    @classmethod
    def all_types(cls) -> list[MessengerType]:
        """Get all registered platform types.

        Returns:
            List of registered platform types
        """
        return list(cls._adapters.keys())

    @classmethod
    def is_registered(cls, messenger_type: MessengerType) -> bool:
        """Check if a platform type is registered.

        Args:
            messenger_type: Platform type

        Returns:
            True if registered
        """
        return messenger_type in cls._adapters

    @classmethod
    def clear_all(cls) -> None:
        """Clear all registered adapters.

        Useful for testing.
        """
        cls._adapters.clear()
