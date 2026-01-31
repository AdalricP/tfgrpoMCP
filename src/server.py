"""Training-Free GRPO MCP Server.

Minimal tool set for experience collection and retrieval.
"""

import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from tfgrpo.episode import EpisodeTracker, extract_error_summary
from tfgrpo.storage import ExperienceStorage
from tfgrpo.summarizer import extract_experience

# Initialize components
app = Server("tfgrpo")
tracker = EpisodeTracker()
storage = ExperienceStorage()


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="start_episode",
            description="Start a new problem-solving episode. Returns episode_id to track progress.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Brief description of what you're trying to accomplish"
                    }
                },
                "required": ["task"]
            }
        ),
        Tool(
            name="log_attempt",
            description="Log an attempt within the current episode. Call this after trying something that failed or succeeded.",
            inputSchema={
                "type": "object",
                "properties": {
                    "episode_id": {
                        "type": "string",
                        "description": "Episode ID from start_episode"
                    },
                    "short_desc": {
                        "type": "string",
                        "description": "Brief description of what you tried (e.g., 'Added asyncio.timeout()')"
                    },
                    "error_output": {
                        "type": "string",
                        "description": "Optional error/stderr output. Will be pre-processed automatically."
                    },
                    "success": {
                        "type": "boolean",
                        "description": "True if this attempt succeeded, False if it failed",
                        "default": False
                    }
                },
                "required": ["episode_id", "short_desc"]
            }
        ),
        Tool(
            name="end_episode",
            description="End the episode. If successful, triggers summarizer (LFM 2.5 via OpenRouter) to extract experience pattern from failure/success contrast.",
            inputSchema={
                "type": "object",
                "properties": {
                    "episode_id": {
                        "type": "string",
                        "description": "Episode ID from start_episode"
                    },
                    "result": {
                        "type": "string",
                        "description": "Brief description of the final outcome"
                    },
                    "success": {
                        "type": "boolean",
                        "description": "True if the problem was solved, False otherwise"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional additional context or insights"
                    }
                },
                "required": ["episode_id", "result", "success"]
            }
        ),
        Tool(
            name="pull_experiences",
            description="Search past experiences using semantic search (embeddings). Understands meaning, not just keywords.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language query (e.g., 'How do I handle async timeout errors?')"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""

    if name == "start_episode":
        episode = tracker.start(arguments["task"])
        return [TextContent(
            type="text",
            text=f"Episode started: {episode.id}\nTask: {episode.task}\nUse this ID for log_attempt and end_episode."
        )]

    elif name == "log_attempt":
        episode = tracker.get(arguments["episode_id"])
        if not episode:
            return [TextContent(type="text", text=f"Error: Episode {arguments['episode_id']} not found")]

        # Pre-process error output if provided
        error_type, error_line = None, None
        if "error_output" in arguments and arguments["error_output"]:
            error_type, error_line = extract_error_summary(arguments["error_output"])

        episode.add_attempt(
            short_desc=arguments["short_desc"],
            error_type=error_type,
            error_line=error_line,
            success=arguments.get("success", False)
        )

        status = "✓ Success" if arguments.get("success") else f"✗ Failed ({error_type or 'unknown'})"
        return [TextContent(
            type="text",
            text=f"Logged: {arguments['short_desc']} → {status}"
        )]

    elif name == "end_episode":
        episode = tracker.end(
            arguments["episode_id"],
            result=arguments["result"],
            success=arguments["success"],
            notes=arguments.get("notes")
        )
        if not episode:
            return [TextContent(type="text", text=f"Error: Episode {arguments['episode_id']} not found")]

        # Trigger summarizer if success
        if arguments["success"]:
            # Build input for Kimi
            kimi_input = episode.to_kimi_input()

            # Run summarizer (sync for now, could be async)
            try:
                extracted = extract_experience(kimi_input)

                # Save to storage
                experience = {
                    "id": episode.id,
                    "task": episode.task,
                    "pattern": extracted.get("pattern", ""),
                    "keywords": extracted.get("keywords", []),
                    "insight": extracted.get("insight", ""),
                    "attempts_count": len(episode.attempts),
                    "result": arguments["result"],
                    "created_at": episode.created_at,
                }

                filename = storage.save(experience)

                return [TextContent(
                    type="text",
                    text=f"""Episode complete! ✓

Experience extracted and saved to {filename}:
Pattern: {extracted.get('pattern', 'N/A')}
Keywords: {', '.join(extracted.get('keywords', []))}
Insight: {extracted.get('insight', 'N/A')}"""
                )]
            except ValueError as e:
                # API key not set or similar configuration error
                return [TextContent(
                    type="text",
                    text=f"""Episode ended but extraction failed: {str(e)}

The episode was completed successfully, but experience extraction requires:
- OPENROUTER_API_KEY set in your MCP server environment

Your episode data was NOT saved. Please fix the configuration and try again."""
                )]
            except Exception as e:
                # Other extraction errors
                return [TextContent(
                    type="text",
                    text=f"""Episode ended but extraction failed: {type(e).__name__}: {str(e)}

The episode was completed successfully, but experience extraction encountered an error.
Your episode data was NOT saved. See error details above."""
                )]
        else:
            # Failed episode - don't extract
            return [TextContent(
                type="text",
                text=f"Episode ended: {arguments['result']}\n(No experience extracted - episode failed)"
            )]

    elif name == "pull_experiences":
        query = arguments["query"]
        limit = arguments.get("limit", 5)

        results = storage.search(query, limit=limit)

        if not results:
            return [TextContent(type="text", text=f"No experiences found for: {query}")]

        # Format results
        output = [f"Found {len(results)} relevant experience(s) for '{query}':\n"]
        for i, exp in enumerate(results, 1):
            output.append(f"""
{i}. {exp.get('task', 'Unknown task')}
   Pattern: {exp.get('pattern', 'N/A')}
   Keywords: {', '.join(exp.get('keywords', []))}
   Insight: {exp.get('insight', 'N/A')}
   Result: {exp.get('result', 'N/A')}
""")

        return [TextContent(type="text", text="".join(output))]

    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


def run():
    """Entry point for MCP server."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
