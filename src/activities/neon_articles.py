"""
Neon Database Activities for Articles

Retrieves article data from Neon database.
"""

from temporalio import activity
from typing import Dict, Any, List
import os
import psycopg
from psycopg.rows import dict_row

from src.config.config import config


@activity.defn(name="neon_get_recent_articles")
async def get_recent_articles_from_neon(
    app: str,
    days: int = 7,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Get recently published articles from Neon database (graceful failure).

    Args:
        app: Application name (placement, relocation, etc.)
        days: Look back N days (default 7)
        limit: Maximum articles to return

    Returns:
        List of recent articles with metadata (empty list if unavailable)
    """
    activity.logger.info(f"Fetching recent articles for {app} from last {days} days (limit {limit})")

    if not config.DATABASE_URL:
        activity.logger.warning("DATABASE_URL not configured")
        return []

    conn = None
    try:
        conn = psycopg.connect(config.DATABASE_URL)
        with conn.cursor(row_factory=dict_row) as cur:
            # Query recent articles
            query = """
                SELECT
                    id, title, slug, excerpt, app, created_at, updated_at,
                    author, word_count, status, featured_image_url
                FROM articles
                WHERE app = %s
                AND created_at >= CURRENT_TIMESTAMP - INTERVAL '%s days'
                AND status IN ('published', 'draft')
                ORDER BY created_at DESC
                LIMIT %s
            """

            cur.execute(query, (app, days, limit))
            articles = cur.fetchall()

            activity.logger.info(f"✅ Found {len(articles)} recent articles for {app}")

            # Already dicts with dict_row
            return list(articles)

    except psycopg.OperationalError as e:
        activity.logger.warning(f"⚠️ Database connection failed - continuing without recent articles: {e}")
        return []
    except Exception as e:
        activity.logger.warning(f"⚠️ Failed to fetch recent articles - continuing: {e}")
        return []

    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
