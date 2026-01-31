# TFGRPO - Training-Free GRPO Experience Server

MCP server that implements Tencent's Training-Free GRPO paper approach for RL for frozen models. Captures failure/success contrasts, extracts patterns via an openrouter LLM, and retrieves them for future use.

[Link to paper](https://arxiv.org/pdf/2510.08191)

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

## MCP Flow (Training-Free GRPO)

This server follows the paper’s Training-Free GRPO idea: keep the base model frozen and shift behavior by updating an external experience library that becomes a token prior for future calls.

- **Rollouts → Attempts**: An episode collects multiple attempts (success/failure), analogous to a group of rollouts for a single query.
- **Semantic Advantage**: Instead of numerical advantages, the summarizer extracts a natural-language “why it worked” pattern by contrasting winners vs losers.
- **Experience Update**: The library is updated with add/modify/delete decisions, mirroring the paper’s experience refinement step.
- **Conditioned Policy**: `pull_experiences` retrieves relevant patterns and injects them into the context, shifting outputs without any parameter updates.

Result: you get GRPO-like optimization effects through context and experience, not fine-tuning.

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
