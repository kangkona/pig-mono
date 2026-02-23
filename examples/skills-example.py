"""Skills system example."""

from pathlib import Path
from py_agent_core import SkillManager


def create_sample_skill():
    """Create a sample skill for demonstration."""
    # Create skill directory
    skill_dir = Path(".agents/skills/code-review")
    skill_dir.mkdir(parents=True, exist_ok=True)

    # Create SKILL.md
    skill_content = """# Code Review

Use this skill when the user asks for a code review or code quality analysis.

This skill helps you perform thorough code reviews focusing on best practices,
security, performance, and maintainability.

## Steps

1. Read the code files provided
2. Check for common issues:
   - Security vulnerabilities
   - Performance bottlenecks
   - Code smells
   - Lack of error handling
3. Verify code follows best practices
4. Suggest improvements with examples
5. Provide a summary rating (1-10)

## Output Format

Provide feedback in this format:
- Issues Found: List major issues
- Suggestions: Improvement recommendations
- Rating: Overall code quality (1-10)
- Next Steps: Action items

## Example

For a function with no error handling:
```python
def divide(a, b):
    return a / b
```

Suggest:
```python
def divide(a: float, b: float) -> float:
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
```
"""

    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(skill_content)

    print(f"✓ Created sample skill at: {skill_file}")
    return skill_file


def main():
    """Demonstrate skills system."""
    print("=== Skills System Example ===\n")

    # Create sample skill
    print("1. Creating sample skill...")
    skill_file = create_sample_skill()

    # Create skill manager
    print("\n2. Creating skill manager...")
    skill_manager = SkillManager()

    # Discover skills
    print("3. Discovering skills...")
    skill_manager.discover_skills([])

    # List loaded skills
    print(f"\n4. Loaded skills ({len(skill_manager)}):")
    for skill in skill_manager.list_skills():
        print(f"   - {skill.name}")
        print(f"     {skill.description}")

    # Get specific skill
    print("\n5. Getting 'code-review' skill...")
    skill = skill_manager.get_skill("code-review")
    if skill:
        print(f"   Name: {skill.name}")
        print(f"   Description: {skill.description}")
        print(f"   Steps: {len(skill.steps)}")

    # Get skill prompt
    print("\n6. Skill as prompt:")
    prompt = skill_manager.get_skill_prompt("code-review")
    if prompt:
        print(prompt)

    # Get all skills prompt
    print("\n7. All skills summary:")
    all_skills = skill_manager.get_all_skills_prompt()
    print(all_skills)

    print("\n✓ Skills system demo complete!")


if __name__ == "__main__":
    main()
