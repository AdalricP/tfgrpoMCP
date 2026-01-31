"""Storage for experiences - flat JSON files with semantic search."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from functools import lru_cache

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


class EmbeddingGenerator:
    """Generate embeddings using OpenRouter."""

    def __init__(self):
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not set in environment")
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )

    @lru_cache(maxsize=256)
    def embed(self, text: str) -> np.ndarray:
        """Generate embedding for text, cached."""
        response = self.client.embeddings.create(
            model="openai/text-embedding-3-small",  # Cheap, fast embeddings
            input=text,
        )
        return np.array(response.data[0].embedding)

    def embed_search_text(self, text: str) -> np.ndarray:
        """Generate embedding for search query (no caching)."""
        response = self.client.embeddings.create(
            model="openai/text-embedding-3-small",
            input=text,
        )
        return np.array(response.data[0].embedding)


class ExperienceStorage:
    """Flat JSON file storage with semantic search."""

    def __init__(self, storage_dir: str | None = None):
        if storage_dir is None:
            # Default: experiences/ next to this file
            storage_dir = Path(__file__).parent / "experiences"
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)

        # Initialize embedding generator (lazy load)
        self._embedding_gen: EmbeddingGenerator | None = None

    def _get_embedding_gen(self) -> EmbeddingGenerator:
        """Lazy load embedding generator."""
        if self._embedding_gen is None:
            try:
                self._embedding_gen = EmbeddingGenerator()
            except ValueError:
                # No API key - semantic search unavailable
                pass
        return self._embedding_gen

    def save(self, experience: dict[str, Any]) -> str:
        """Save experience to a new JSON file. Returns filename."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"exp_{timestamp}.json"
        filepath = self.storage_dir / filename

        # Generate and store embedding for semantic search
        embed_gen = self._get_embedding_gen()
        if embed_gen is not None:
            search_text = " ".join([
                experience.get("task", ""),
                experience.get("pattern", ""),
                experience.get("insight", ""),
                " ".join(experience.get("keywords", []))
            ])
            try:
                experience["embedding"] = embed_gen.embed(search_text).tolist()
            except Exception:
                # Skip embedding if generation fails
                experience["embedding"] = None

        with open(filepath, "w") as f:
            json.dump(experience, f, indent=2)

        return filename

    def search(self, query: str, limit: int = 5, semantic: bool = True) -> list[dict[str, Any]]:
        """
        Search across all experiences.

        Args:
            query: Search query text
            limit: Max results to return
            semantic: Use semantic search (embeddings) if available, falls back to keyword search
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())

        results = []
        has_embeddings = False

        # Try semantic search first
        if semantic:
            embed_gen = self._get_embedding_gen()
            if embed_gen is not None:
                try:
                    query_embedding = embed_gen.embed_search_text(query)
                    has_embeddings = True
                except Exception:
                    pass

        for filepath in self.storage_dir.glob("exp_*.json"):
            try:
                with open(filepath, "r") as f:
                    exp = json.load(f)

                score = 0.0

                # Semantic similarity score
                if has_embeddings and exp.get("embedding"):
                    exp_embedding = np.array(exp["embedding"])
                    sim = cosine_similarity(query_embedding, exp_embedding)
                    # Normalize to 0-10 range for keyword compatibility
                    score = max(score, sim * 10)

                # Keyword matching (boosts score when combined with semantic)
                text = (
                    exp.get("task", "") + " " +
                    exp.get("pattern", "") + " " +
                    exp.get("insight", "") + " " +
                    " ".join(exp.get("keywords", []))
                ).lower()

                for word in query_words:
                    if word in text:
                        # Add smaller boost for keyword matches when semantic is available
                        boost = 0.5 if has_embeddings else 1
                        score += boost
                        # Bonus for word boundary match
                        if f" {word} " in f" {text} ":
                            score += boost

                if score > 0:
                    results.append((score, exp))
            except (json.JSONDecodeError, IOError):
                continue

        # Sort by score descending, return top N
        results.sort(key=lambda x: x[0], reverse=True)
        return [exp for _, exp in results[:limit]]

    def get_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get most recent experiences."""
        files = sorted(
            self.storage_dir.glob("exp_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        results = []
        for filepath in files[:limit]:
            try:
                with open(filepath, "r") as f:
                    results.append(json.load(f))
            except (json.JSONDecodeError, IOError):
                continue

        return results
