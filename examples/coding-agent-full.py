"""Complete py-coding-agent example with all features."""

import os
from pathlib import Path

def setup_demo_environment():
    """Setup demo environment with extensions and skills."""
    
    # Create workspace
    workspace = Path("demo-workspace")
    workspace.mkdir(exist_ok=True)
    
    # Create sample extension
    ext_dir = workspace / ".agents" / "extensions"
    ext_dir.mkdir(parents=True, exist_ok=True)
    
    (ext_dir / "demo_extension.py").write_text("""
def extension(api):
    '''Demo extension with custom tools.'''
    
    @api.tool(description="Reverse a string")
    def reverse_string(text: str) -> str:
        return text[::-1]
    
    @api.command("greet", "Say hello")
    def greet_command():
        return "Hello from extension!"
    
    @api.on("tool_call_start")
    def log_tool(event, ctx):
        print(f"🔧 Calling tool: {event.get('tool_name')}")
    
    print("✓ Demo extension loaded")
""")
    
    # Create sample skill
    skill_dir = workspace / ".agents" / "skills" / "python-best-practices"
    skill_dir.mkdir(parents=True, exist_ok=True)
    
    (skill_dir / "SKILL.md").write_text("""# Python Best Practices

Use this skill when reviewing Python code or suggesting improvements.

## Steps

1. Check code structure and organization
2. Verify type hints are used
3. Check for docstrings
4. Look for error handling
5. Suggest Pythonic improvements

## Example

For code without type hints:
```python
def add(a, b):
    return a + b
```

Suggest:
```python
def add(a: int, b: int) -> int:
    '''Add two integers.'''
    return a + b
```
""")
    
    print(f"✓ Demo environment created at: {workspace}")
    return workspace


def main():
    """Run complete demo."""
    print("=" * 60)
    print("py-coding-agent Complete Feature Demo")
    print("=" * 60)
    print()
    
    # Setup demo environment
    print("Setting up demo environment...")
    workspace = setup_demo_environment()
    print()
    
    # Show what's available
    print("Demo includes:")
    print("  ✓ Extension with 1 custom tool + 2 commands")
    print("  ✓ Skill: Python Best Practices")
    print("  ✓ Session management enabled")
    print()
    
    # Show command examples
    print("Try these commands:")
    print()
    print("  Session Management:")
    print("    /session    - Show session info")
    print("    /tree       - View conversation tree")
    print("    /fork demo  - Fork to new session")
    print("    /compact    - Compact old messages")
    print()
    print("  Skills:")
    print("    /skills                       - List skills")
    print("    /skill:python-best-practices  - Invoke skill")
    print()
    print("  Extensions:")
    print("    /extensions  - List loaded extensions")
    print("    /greet       - Custom command from extension")
    print()
    print("  Ask agent:")
    print("    'Reverse the string hello'     - Uses custom tool")
    print("    'Review this Python function'  - Uses skill")
    print()
    print("-" * 60)
    print()
    
    # Check for API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("⚠️  Set OPENAI_API_KEY to run the agent")
        print()
        print("Demo environment is ready at:", workspace)
        print()
        print("To start:")
        print(f"  cd {workspace}")
        print("  export OPENAI_API_KEY=your-key")
        print("  pig-code")
        return

    # Start agent
    print("Starting agent...")
    print("(Set OPENAI_API_KEY first to actually run)")
    print()
    print(f"Command: cd {workspace} && pig-code")


if __name__ == "__main__":
    main()
