"""Script adherence checker using cosine similarity with pgvector embeddings.

Will be implemented in Phase 2 (Week 9).
Compares manager's speech against script checkpoints in real-time.
"""


async def check_checkpoint_match(
    user_text: str,
    checkpoint_id: str,
    threshold: float = 0.7,
) -> tuple[bool, float]:
    """Check if user text matches a script checkpoint. Returns (matched, similarity_score)."""
    raise NotImplementedError("Script checker not yet implemented — Phase 2, Week 9")
