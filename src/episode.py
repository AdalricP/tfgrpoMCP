"""Episode tracking with stderr extraction and pre-processing."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass
class Attempt:
    """A single attempt within an episode (pre-processed summary)."""
    short_desc: str  # What was tried
    error_type: str | None = None  # e.g., "TimeoutError", "ValueError"
    error_line: str | None = None  # e.g., "main.py:42"
    success: bool = False


@dataclass
class Episode:
    """A GRPO episode - one problem-solving session."""
    id: str
    task: str
    created_at: str
    attempts: list[Attempt] = field(default_factory=list)
    final_result: str | None = None
    final_success: bool | None = None
    notes: str | None = None

    def add_attempt(self, short_desc: str, error_type: str | None = None,
                    error_line: str | None = None, success: bool = False) -> None:
        """Add a pre-processed attempt to this episode."""
        self.attempts.append(Attempt(
            short_desc=short_desc,
            error_type=error_type,
            error_line=error_line,
            success=success
        ))

    def get_failures(self, limit: int = 5) -> list[Attempt]:
        """Get recent failed attempts for contrast."""
        failed = [a for a in self.attempts if not a.success]
        return failed[-limit:]  # Last N failures

    def get_success(self) -> Attempt | None:
        """Get the successful attempt."""
        for a in reversed(self.attempts):
            if a.success:
                return a
        return None

    def to_kimi_input(self) -> dict:
        """Convert to minimal structured format for Kimi."""
        failures = self.get_failures()
        success = self.get_success()

        return {
            "task": self.task,
            "failures": [
                {"desc": f.short_desc, "error": f.error_type or "unknown"}
                for f in failures
            ],
            "success": {
                "desc": success.short_desc,
                "result": self.final_result or "completed"
            } if success else None,
        }


class EpisodeTracker:
    """Tracks active episodes in-memory."""

    def __init__(self):
        self._episodes: dict[str, Episode] = {}

    def start(self, task: str) -> Episode:
        """Start a new episode."""
        episode_id = f"ep_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        episode = Episode(
            id=episode_id,
            task=task,
            created_at=datetime.now().isoformat()
        )
        self._episodes[episode_id] = episode
        return episode

    def get(self, episode_id: str) -> Episode | None:
        """Get an existing episode."""
        return self._episodes.get(episode_id)

    def end(self, episode_id: str, result: str, success: bool,
            notes: str | None = None) -> Episode | None:
        """End an episode and remove from tracking."""
        episode = self._episodes.get(episode_id)
        if episode:
            episode.final_result = result
            episode.final_success = success
            episode.notes = notes
            # Keep briefly for summarizer, then clean up
            del self._episodes[episode_id]
        return episode


def extract_error_summary(stderr: str) -> tuple[str | None, str | None]:
    """
    Extract error type and location from stderr.

    Returns: (error_type, error_line) or (None, None)

    Examples:
        "TimeoutError: async operation timed out" -> ("TimeoutError", None)
        "  File 'main.py', line 42, in <module>" -> (None, "main.py:42")
    """
    if not stderr:
        return None, None

    lines = stderr.strip().split("\n")

    # Extract error type (last line usually has the error)
    error_type = None
    error_pattern = re.compile(r"^(\w+Error|^\w+Exception):")
    for line in reversed(lines[-10:]):  # Check last 10 lines
        match = error_pattern.match(line.strip())
        if match:
            error_type = match.group(1)
            break

    # Extract file:line from common traceback patterns
    error_line = None
    line_pattern = re.compile(r'File "([^"]+)", line (\d+)')
    for line in lines:
        match = line_pattern.search(line)
        if match:
            error_line = f"{Path(match.group(1)).name}:{match.group(2)}"
            break

    return error_type, error_line
