"""Seed Mission Control Tavern with starter quests and metrics. Run after schema apply."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DSN = "postgresql://thread:thread@127.0.0.1:55432/thread"


def _dsn() -> str:
    load_dotenv(ROOT / ".env", override=False)
    url = os.environ.get("DATABASE_URL", DEFAULT_DSN)
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def seed() -> None:
    conn = await asyncpg.connect(_dsn())
    try:
        await conn.execute("DELETE FROM tavern_quests WHERE quest_id LIKE 'quest-%'")
        await conn.execute("DELETE FROM tavern_pwin_history")

        await conn.execute(
            """
            INSERT INTO tavern_pwin_history (pwin_value, notes)
            VALUES (58.0, 'Baseline after profile creation phase')
            """
        )

        quests = [
            ("quest-001", "Query Ariadne for current packet gaps", "Coordinator", "backlog", 10, 50, 3.0),
            ("quest-002", "Translate top gaps into side quests", "Guild Master", "backlog", 15, 75, 5.0),
            ("quest-003", "Implement Party Command tab + HUD", "Healer", "in_progress", 120, 150, 8.0),
            ("quest-004", "Create Bard profile", "Guild Master", "todo", 20, 60, 2.0),
        ]
        for q in quests:
            await conn.execute(
                """
                INSERT INTO tavern_quests
                (quest_id, objective, target_hero, status, est_minutes, base_xp, est_pwin_delta)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                *q,
            )

        await conn.execute(
            """
            INSERT INTO tavern_hero_activity (hero, action_type, quest_id, description, xp_gained, pwin_impact)
            VALUES
            ('Artificer', 'delegation_test', NULL, 'Confirmed profile active via test delegation', 25, 0.5),
            ('Healer', 'quest_started', 'quest-003', 'Started Party Command + HUD implementation', 0, 0)
            """
        )

        await conn.execute(
            """
            INSERT INTO tavern_agent_logs (hero, task, model_used, status, duration_ms)
            VALUES
            ('Artificer', 'Profile confirmation test', 'grok-4.3', 'success', 38120),
            ('Healer', 'Party Command router creation', 'grok-4.3', 'success', 124000)
            """
        )

        print("Tavern seed data inserted successfully.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())