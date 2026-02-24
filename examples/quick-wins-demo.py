"""Demo of Quick Wins features: Context, File Tools, Prompts."""

from pathlib import Path


def setup_demo_environment():
    """Setup complete demo environment."""
    
    workspace = Path("demo-full")
    workspace.mkdir(exist_ok=True)
    
    # 1. Setup Context Files
    print("1. Setting up context files...")
    
    (workspace / "AGENTS.md").write_text("""# My Project

This is a FastAPI web application.

## Conventions
- Use async/await for all routes
- Type hints required
- Pydantic models for validation

## Common Commands
- pytest for testing
- ruff for linting
""")
    
    (workspace / "SYSTEM.md").write_text("""You are a FastAPI expert.

Always:
- Use async def for routes
- Include error handling
- Add type hints
- Write docstrings
""")
    
    print("   ✓ AGENTS.md created")
    print("   ✓ SYSTEM.md created")
    
    # 2. Setup Prompt Templates
    print("\n2. Setting up prompt templates...")
    
    prompts_dir = workspace / ".agents" / "prompts"
    prompts_dir.mkdir(parents=True)
    
    (prompts_dir / "api-route.md").write_text("""# Create API Route

Create a FastAPI route for {{endpoint}}.

Requirements:
- HTTP method: {{method}}
- Response model: Pydantic
- Error handling: HTTPException
- Type hints: Complete

Include: route, model, error cases.
""")
    
    (prompts_dir / "test.md").write_text("""# Write Tests

Write pytest tests for {{target}}.

Coverage:
- Happy path
- Error cases  
- Edge cases
- {{extra}}

Use pytest fixtures and async tests where needed.
""")
    
    print("   ✓ api-route template")
    print("   ✓ test template")
    
    # 3. Create sample code for grep/find demo
    print("\n3. Creating sample code...")
    
    src_dir = workspace / "src"
    src_dir.mkdir()
    
    (src_dir / "main.py").write_text("""from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello World"}

@app.get("/users")
def list_users():
    # TODO: Implement user listing
    return []
""")
    
    (src_dir / "models.py").write_text("""from pydantic import BaseModel

class User(BaseModel):
    id: int
    name: str
    email: str
""")
    
    (src_dir / "database.py").write_text("""# Database connection
# TODO: Implement database logic

def get_connection():
    pass
""")
    
    print("   ✓ src/main.py")
    print("   ✓ src/models.py")
    print("   ✓ src/database.py")
    
    print(f"\n✓ Demo environment ready at: {workspace}")
    print("\nTry these commands:")
    print("\n  Context Files:")
    print("    > What are the project conventions?")
    print("    [Agent uses AGENTS.md for context]")
    print()
    print("  Prompt Templates:")
    print("    > /prompts")
    print("    > /api-route endpoint=users method=POST")
    print()
    print("  Advanced File Tools:")
    print("    > Search for 'TODO' in all files")
    print("    [Uses grep_files tool]")
    print("    > Find all Python files")
    print("    [Uses find_files tool]")
    print("    > Show detailed file list")
    print("    [Uses ls_detailed tool]")
    
    return workspace


def main():
    """Run demo setup."""
    print("=" * 60)
    print("Quick Wins Features Demo Setup")
    print("=" * 60)
    print()
    
    workspace = setup_demo_environment()
    
    print()
    print("=" * 60)
    print("To use:")
    print(f"  cd {workspace}")
    print("  export OPENAI_API_KEY=your-key")
    print("  pig-code")
    print("=" * 60)


if __name__ == "__main__":
    main()
