"""Theme configuration for TUI components."""

from dataclasses import dataclass


@dataclass
class Theme:
    """Theme colors and styles for TUI."""

    user_color: str = "cyan"
    assistant_color: str = "green"
    system_color: str = "yellow"
    error_color: str = "red"
    timestamp_color: str = "dim"
    border_color: str = "blue"
    
    @classmethod
    def dark(cls) -> "Theme":
        """Get dark theme."""
        return cls()
    
    @classmethod
    def light(cls) -> "Theme":
        """Get light theme."""
        return cls(
            user_color="blue",
            assistant_color="green",
            system_color="orange",
            error_color="red",
        )
