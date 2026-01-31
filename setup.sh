#!/bin/bash
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Config - UPDATE THIS with your repo URL
REPO_URL="https://github.com/aryan/tfgrpo.git"
REPO_NAME="tfgrpo"
DEFAULT_INSTALL_DIR="$HOME/$REPO_NAME"

echo -e "${BLUE}"
cat << "EOF"
   __                  __  ___
  / /  ___  ___  _____/ / / _ \___  ___
 / _ \/ _ \/ _ \/ ___/ _ \/ // / _ \/ -_)
/_//_/\___/_//_/_/  /_//_/\___/ .__/\__/
                            /_/

EOF
echo -e "${NC}Training-Free GRPO Experience Server for MCP"
echo

# Detect if we're already in the repo
if [ -f "pyproject.toml" ] && grep -q "$REPO_NAME" pyproject.toml 2>/dev/null; then
    SCRIPT_DIR="$(pwd)"
    echo -e "${YELLOW}Already in repo directory, skipping clone...${NC}"
else
    # Not in repo - clone it
    echo -e "${GREEN}[0/5]${NC} Cloning repository..."

    # Ask for install directory
    read -p "Install directory [$DEFAULT_INSTALL_DIR]: " INSTALL_DIR
    INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"

    if [ -d "$INSTALL_DIR" ]; then
        echo -e "${YELLOW}Directory already exists. Update or skip?${NC}"
        read -p "[u/s]: " -n 1 -r
        echo
        if [[ $REPLY == "s" ]]; then
            cd "$INSTALL_DIR"
            SCRIPT_DIR="$INSTALL_DIR"
        else
            rm -rf "$INSTALL_DIR"
        fi
    fi

    if [ ! -d "$INSTALL_DIR" ]; then
        git clone "$REPO_URL" "$INSTALL_DIR"
        cd "$INSTALL_DIR"
        SCRIPT_DIR="$INSTALL_DIR"
        echo -e "${GREEN}✓ Cloned to $INSTALL_DIR${NC}"
    fi
fi

cd "$SCRIPT_DIR"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 not found${NC}"
    exit 1
fi

echo -e "${GREEN}[1/5]${NC} Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo -e "${GREEN}[2/5]${NC} Installing dependencies..."
pip install --upgrade pip > /dev/null
pip install -e . > /dev/null

echo -e "${GREEN}[3/5]${NC} Setting up environment..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo -e "${YELLOW}Enter your OpenRouter API key:${NC}"
    read -r API_KEY
    sed -i.bak "s/your_key_here/$API_KEY/" .env
    rm -f .env.bak
else
    echo -e "${YELLOW}.env already exists, skipping...${NC}"
fi

# Get absolute path of server script
SERVER_PATH="$(pwd)/venv/bin/tfgrpo"

echo -e "${GREEN}[4/5]${NC} Choose installation level:"
echo "  1) Repository-level (this repo only)"
echo "  2) User-level (all Claude Code projects)"
echo
read -p "Select [1/2]: " -n 1 -r
echo

MCP_CONFIG='{
  "mcpServers": {
    "tfgrpo": {
      "command": "'"$SERVER_PATH"'"
    }
  }
}'

if [[ $REPLY == "1" ]]; then
    # Repo-level
    mkdir -p .claude
    if [ -f .claude/settings.local.json ]; then
        # Merge with existing
        echo -e "${YELLOW}Updating .claude/settings.local.json...${NC}"
        # Simple merge using python
        python3 << PYTHON
import json
import os

settings_path = ".claude/settings.local.json"
mcp_config = $MCP_CONFIG

with open(settings_path, "r") as f:
    settings = json.load(f)

if "mcpServers" not in settings:
    settings["mcpServers"] = {}
settings["mcpServers"]["tfgrpo"] = mcp_config["mcpServers"]["tfgrpo"]

with open(settings_path, "w") as f:
    json.dump(settings, f, indent=2)
PYTHON
    else
        echo "$MCP_CONFIG" > .claude/settings.local.json
    fi
    echo -e "${GREEN}✓ Configured for repository-level${NC}"

elif [[ $REPLY == "2" ]]; then
    # User-level
    CONFIG_DIR="$HOME/.config/claude"
    CONFIG_FILE="$CONFIG_DIR/claude_desktop_config.json"
    mkdir -p "$CONFIG_DIR"

    if [ -f "$CONFIG_FILE" ]; then
        python3 << PYTHON
import json
import os

config_path = os.path.expanduser("$CONFIG_FILE")
mcp_config = $MCP_CONFIG

with open(config_path, "r") as f:
    config = json.load(f)

if "mcpServers" not in config:
    config["mcpServers"] = {}
config["mcpServers"]["tfgrpo"] = mcp_config["mcpServers"]["tfgrpo"]

with open(config_path, "w") as f:
    json.dump(config, f, indent=2)
PYTHON
    else
        echo "$MCP_CONFIG" > "$CONFIG_FILE"
    fi
    echo -e "${GREEN}✓ Configured for user-level${NC}"
else
    echo -e "${RED}Invalid choice. MCP configuration skipped.${NC}"
    echo -e "${YELLOW}Run this script again to configure.${NC}"
fi

echo
echo -e "${GREEN}[5/5]${NC} Done!"
echo
echo -e "${BLUE}Installation complete!${NC}"
echo
echo "Installed to: $SCRIPT_DIR"
echo
echo "Next steps:"
echo "  1. Restart Claude Code"
echo "  2. The tfgrpo MCP server will be available"
echo
echo "To uninstall:"
echo "  - Remove the MCP config from your settings"
echo "  - Delete this directory"
