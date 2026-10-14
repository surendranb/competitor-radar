#!/usr/bin/env bash
# ==============================================================================
# Competitor Radar Universal Installer
# Installs and configures Competitor Radar for Claude Desktop, Cursor, and OpenCode
# ==============================================================================
set -e

SERVER_NAME="competitor-radar"
PACKAGE_NAME="competitor-radar"
DISPLAY_NAME="Competitor Radar"

echo "⚡ Installing ${DISPLAY_NAME} (Fleet v2 Standard)..."
echo "  • Local-first competitive intelligence ledger"
echo "  • Zero host data leaves your device"
echo ""

HAS_UVX=false
HAS_NPX=false

if command -v uvx &>/dev/null; then
  HAS_UVX=true
  echo "✔ uvx detected (recommended Python runtime)"
elif command -v npx &>/dev/null; then
  HAS_NPX=true
  echo "✔ npx detected (Node runtime bridge)"
else
  echo "⚠ Neither uvx nor npx was detected in PATH."
  echo "  Install uv with: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

CHOSEN_CMD="uvx"
CHOSEN_ARGS='["competitor-radar"]'
if [ "$HAS_UVX" = false ] && [ "$HAS_NPX" = true ]; then
  CHOSEN_CMD="npx"
  CHOSEN_ARGS='["-y", "competitor-radar"]'
fi

CONFIG_TARGETS=()

# 1. Claude Desktop (macOS)
if [ -d "$HOME/Library/Application Support/Claude" ]; then
  CONFIG_TARGETS+=("$HOME/Library/Application Support/Claude/claude_desktop_config.json")
fi

# 2. Cursor
if [ -d "$HOME/.cursor" ]; then
  CONFIG_TARGETS+=("$HOME/.cursor/mcp.json")
fi

# 3. OpenCode
if [ -d "$HOME/.config/opencode" ]; then
  CONFIG_TARGETS+=("$HOME/.config/opencode/opencode.json")
fi

# Apply to configs using Python
python3 - <<PYEOF
import json, os, sys

targets = [t for t in """${CONFIG_TARGETS[*]}""".split() if t]
chosen_cmd = "${CHOSEN_CMD}"
chosen_args = json.loads('''${CHOSEN_ARGS}''')
server_name = "${SERVER_NAME}"

for target_path in targets:
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        data = {}
        if os.path.exists(target_path):
            with open(target_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    data = json.loads(content)
        
        if "mcpServers" not in data:
            data["mcpServers"] = {}
        
        data["mcpServers"][server_name] = {
            "command": chosen_cmd,
            "args": chosen_args
        }
        
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        print(f"✔ Configured: {target_path}")
    except Exception as e:
        print(f"⚠ Could not update {target_path}: {e}", file=sys.stderr)
PYEOF

echo ""
echo "🎉 Setup complete! Launch with:"
echo "  claude mcp add competitor-radar -- ${CHOSEN_CMD} ${PACKAGE_NAME}"
echo "Or start the local CLI directly:"
echo "  uvx competitor-radar --help"
