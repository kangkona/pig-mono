#!/bin/bash
# Install all packages in development mode
#
# Creates isolated venvs per CLI package using uv, then symlinks
# the CLI entry points to ~/.local/bin/. This avoids pipx's inability
# to resolve local monorepo dependencies.

set -e

echo "Installing pig-mono packages in development mode..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
VENVS_DIR="$HOME/.local/pig-mono-venvs"
BIN_DIR="$HOME/.local/bin"

cd "$REPO_ROOT"

mkdir -p "$VENVS_DIR" "$BIN_DIR"

# All local library packages (installed as editable into every venv)
LOCAL_PKGS="-e packages/pig-llm -e packages/pig-tui -e packages/pig-agent-core"

install_pkg() {
    local name="$1"
    local pkg_path="$2"
    shift 2
    # remaining args are "cli_name" entries from [project.scripts]
    local venv_dir="$VENVS_DIR/$name"

    echo "Installing $name..."

    # Create venv
    uv venv "$venv_dir" --quiet

    # Install the package + all local deps
    uv pip install --python "$venv_dir/bin/python" \
        -e "$pkg_path" $LOCAL_PKGS --quiet

    # Symlink CLI entry points
    for cli_name in "$@"; do
        ln -sf "$venv_dir/bin/$cli_name" "$BIN_DIR/$cli_name"
        echo "  ✓ $cli_name -> $BIN_DIR/$cli_name"
    done
    echo
}

# Uninstall old pipx versions if they exist
for pkg in pig-web-ui pig-coding-agent pig-messenger; do
    pipx uninstall "$pkg" 2>/dev/null || true
done

install_pkg pig-web-ui      packages/pig-web-ui      pig-webui
install_pkg pig-coding-agent packages/pig-coding-agent pig-code
install_pkg pig-messenger    packages/pig-messenger    pig-messenger

echo "✓ All packages installed successfully!"
echo "Make sure $BIN_DIR is in your PATH."
