"""File reference system (@filename auto-read)."""

import re
from pathlib import Path
from typing import List, Tuple


class FileReferenceParser:
    """Parse and resolve @file references in messages."""

    def __init__(self, workspace: Path):
        """Initialize file reference parser.

        Args:
            workspace: Workspace directory
        """
        self.workspace = workspace

    def parse_references(self, text: str) -> List[str]:
        """Parse @file references from text.

        Args:
            text: Input text

        Returns:
            List of file paths found
        """
        # Match @filename or @path/to/file
        pattern = r"@([\w\-./]+\.\w+)"
        matches = re.findall(pattern, text)
        return matches

    def resolve_file(self, reference: str) -> Tuple[bool, Path, str]:
        """Resolve a file reference to actual path.

        Args:
            reference: File reference (e.g., "src/main.py")

        Returns:
            Tuple of (exists, path, content_or_error)
        """
        # Try as relative to workspace
        file_path = self.workspace / reference

        if not file_path.exists():
            # Try without leading path components
            name = Path(reference).name
            # Search in workspace
            matches = list(self.workspace.rglob(name))

            if matches:
                file_path = matches[0]  # Use first match
            else:
                return False, file_path, f"File not found: {reference}"

        # Security: ensure within workspace
        try:
            file_path = file_path.resolve()
            if not str(file_path).startswith(str(self.workspace.resolve())):
                return False, file_path, f"File outside workspace: {reference}"
        except Exception as e:
            return False, file_path, f"Error resolving path: {e}"

        # Read file
        try:
            content = file_path.read_text()
            return True, file_path, content
        except Exception as e:
            return False, file_path, f"Error reading file: {e}"

    def expand_references(self, text: str) -> str:
        """Expand @file references in text with file contents.

        Args:
            text: Input text with @references

        Returns:
            Expanded text with file contents
        """
        references = self.parse_references(text)

        if not references:
            return text

        # Build expanded text
        expanded_parts = [text]
        file_contents = []

        for ref in references:
            exists, path, content_or_error = self.resolve_file(ref)

            if exists:
                # Add file content
                rel_path = path.relative_to(self.workspace)
                file_contents.append(
                    f"\n\n--- File: {rel_path} ---\n{content_or_error}\n--- End of {rel_path} ---"
                )
            else:
                # Add error note
                file_contents.append(f"\n\n[Error: {content_or_error}]")

        # Combine
        expanded = text + "\n".join(file_contents)

        return expanded

    def get_reference_preview(self, text: str) -> str:
        """Get preview of what files would be included.

        Args:
            text: Input text

        Returns:
            Preview message
        """
        references = self.parse_references(text)

        if not references:
            return ""

        preview_parts = ["Files to include:"]

        for ref in references:
            exists, path, content_or_error = self.resolve_file(ref)

            if exists:
                size = len(content_or_error)
                lines = content_or_error.count("\n") + 1
                rel_path = path.relative_to(self.workspace)
                preview_parts.append(f"  ✓ {rel_path} ({lines} lines, {size} bytes)")
            else:
                preview_parts.append(f"  ✗ {ref} - {content_or_error}")

        return "\n".join(preview_parts)


def demo():
    """Demonstrate file reference parsing."""
    
    parser = FileReferenceParser(Path.cwd())

    # Example text
    text = "Review @src/main.py and @README.md for issues"

    # Parse
    refs = parser.parse_references(text)
    print(f"Found references: {refs}")

    # Preview
    preview = parser.get_reference_preview(text)
    print(f"\n{preview}")

    # Expand
    expanded = parser.expand_references(text)
    print(f"\nExpanded ({len(expanded)} chars)")


if __name__ == "__main__":
    demo()
