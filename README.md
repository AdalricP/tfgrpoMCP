# TFGRPO - Training-Free GRPO Experience Server

MCP server that implements the Training-Free GRPO paper's approach to learning from code-fixing episodes. Captures failure/success contrasts, extracts patterns via Kimi LLM, and retrieves them for future use.

## Installation

### Quick setup (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/aryan/tfgrpo/main/setup.sh | bash
```

### Manual setup

```bash
cd /path/to/tfgrpo
pip install -e .
```

## Configuration

1. Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

2. Add your OpenRouter API key to `.env`:
```
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

3. Add to Claude Code config (`~/.claude.json`):
```json
{
  "mcpServers": {
    "tfgrpo": {
      "type": "stdio",
      "command": "/Users/aryan/Desktop/tfgrpo/venv/bin/python",
      "args": ["-m", "tfgrpo.server"],
      "env": {
        "OPENROUTER_API_KEY": "sk-or-v1-your-key-here"
      }
    }
  }
}
```

Or add to a specific project's `mcpServers` section if you want it scoped to one directory.

## Usage

### Tool: start_episode
Start tracking a new problem-solving session.
```
start_episode(task="Fix async timeout bug in API client")
```

### Tool: log_attempt
Log what you tried. Automatically pre-processes errors.
```
log_attempt(
  episode_id="ep_20250131_150000",
  short_desc="Added asyncio.wait_for with 10s timeout",
  error_output="TimeoutError: asyncio timeout",  # optional
  success=false
)
```

### Tool: end_episode
Finish and extract experience pattern.
```
end_episode(
  episode_id="ep_20250131_150000",
  result="Used asyncio.timeout() context manager instead",
  success=true
)
```

### Tool: pull_experiences
Search past experiences by keyword.
```
pull_experiences(query="async timeout", limit=5)
```

## How It Works

1. **Collect** - Track attempts within an episode, pre-processing errors (extract type/line only)
2. **Contrast** - Compare failed vs successful attempts
3. **Extract** - Kimi LLM extracts the pattern that made the difference
4. **Store** - Save minimal JSON with pattern + keywords + insight
5. **Retrieve** - Keyword search finds relevant past experiences

## Token Optimization

- **Pre-processing**: Extracts only error type and line number from stderr
- **Minimal prompts**: Structured JSON prompts to Kimi, ~100 tokens
- **Storage**: Summaries only, no raw stack traces
- **Search**: Keyword matching with relevance scoring

## Architecture (based on the paper)

```
Query → pull_experiences → Policy generates action
         ↑                              ↓
         └──────── Experiences ←────┘
                      ↑
              end_episode → Summarizer → Extract pattern
                      ↓
              log_attempt (failed/success)
```
