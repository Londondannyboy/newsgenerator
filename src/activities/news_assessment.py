"""
News Assessment Activity

Evaluates news stories for relevance using Claude AI.
Determines which stories should be promoted to article creation.
"""

import anthropic
from temporalio import activity
from typing import Dict, Any, List
import json

from src.config.config import config


@activity.defn(name="claude_assess_news")
async def assess_news_batch(
    stories: List[Dict[str, Any]],
    app: str,
    app_context: Dict[str, Any],
    recent_articles: List[Dict[str, Any]],
    min_relevance_score: float = 0.6
) -> Dict[str, Any]:
    """
    Assess a batch of news stories for relevance using Claude.

    Args:
        stories: List of news stories to assess
        app: Application name (placement, relocation, etc.)
        app_context: App configuration with keywords, exclusions, interests, etc.
        recent_articles: Recently published articles (for context/deduplication)
        min_relevance_score: Minimum score (0-1) to consider relevant

    Returns:
        Assessment results with relevant and skipped stories
    """
    activity.logger.info(f"Assessing {len(stories)} stories for app: {app}")

    if not config.ANTHROPIC_API_KEY:
        return {
            "stories_assessed": 0,
            "relevant_stories": [],
            "skipped_stories": [],
            "error": "ANTHROPIC_API_KEY not configured"
        }

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    # Build context for assessment
    keywords = app_context.get("keywords", [])
    exclusions = app_context.get("exclusions", [])
    interests = app_context.get("interests", [])

    stories_text = "\n\n".join([
        f"Story {i+1}: {story.get('title', '')}\n"
        f"Source: {story.get('source', 'Unknown')}\n"
        f"Date: {story.get('date', 'Unknown')}\n"
        f"Snippet: {story.get('snippet', story.get('description', ''))[:200]}"
        for i, story in enumerate(stories)
    ])

    prompt = f"""You are a news editor for {app}, a platform covering professional topics.

Assess these news stories for relevance and priority.

APP CONTEXT:
- Keywords: {', '.join(keywords)}
- Interests: {', '.join(interests)}
- Exclusions: {', '.join(exclusions)}

STORIES TO ASSESS:
{stories_text}

For each story, determine:
1. Is it relevant to {app}? (Yes/No)
2. Relevance score: 0-1 (1 = highly relevant)
3. Priority level: high/medium/low

Return JSON array where each object is:
{{
  "story_index": 0,
  "title": "Story title",
  "relevant": true,
  "relevance_score": 0.85,
  "priority": "high",
  "reasoning": "Why this is/isn't relevant"
}}

Only include stories with relevance_score >= {min_relevance_score}.
Prioritize stories matching keywords.
Return ONLY valid JSON array, no other text."""

    try:
        message = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text

        # Parse JSON
        assessments = json.loads(response_text)
        if not isinstance(assessments, list):
            assessments = [assessments]

        relevant_stories = []
        high_priority_count = 0
        medium_priority_count = 0
        low_priority_count = 0

        for assessment in assessments:
            if assessment.get("relevant") and assessment.get("relevance_score", 0) >= min_relevance_score:
                # Get original story
                story_index = assessment.get("story_index", 0)
                if story_index < len(stories):
                    original_story = stories[story_index]

                    relevant_stories.append({
                        "story": original_story,
                        "relevance_score": assessment.get("relevance_score", 0),
                        "priority": assessment.get("priority", "medium"),
                        "reasoning": assessment.get("reasoning", "")
                    })

                    # Count by priority
                    if assessment.get("priority") == "high":
                        high_priority_count += 1
                    elif assessment.get("priority") == "medium":
                        medium_priority_count += 1
                    else:
                        low_priority_count += 1

        activity.logger.info(
            f"Assessment complete: {len(relevant_stories)} relevant stories "
            f"(high={high_priority_count}, medium={medium_priority_count}, low={low_priority_count})"
        )

        return {
            "stories_assessed": len(stories),
            "relevant_stories": relevant_stories,
            "skipped_stories": len(stories) - len(relevant_stories),
            "total_high_priority": high_priority_count,
            "total_medium_priority": medium_priority_count,
            "total_low_priority": low_priority_count,
            "success": True
        }

    except json.JSONDecodeError as e:
        activity.logger.error(f"Failed to parse assessment JSON: {e}")
        # Return all stories as fallback
        return {
            "stories_assessed": len(stories),
            "relevant_stories": [
                {
                    "story": story,
                    "relevance_score": 0.5,
                    "priority": "medium",
                    "reasoning": "Fallback - assessment failed"
                }
                for story in stories
            ],
            "skipped_stories": 0,
            "total_high_priority": 0,
            "total_medium_priority": len(stories),
            "total_low_priority": 0,
            "success": False,
            "error": f"JSON parse failed: {e}"
        }

    except Exception as e:
        activity.logger.error(f"Assessment error: {e}")
        return {
            "stories_assessed": 0,
            "relevant_stories": [],
            "skipped_stories": len(stories),
            "total_high_priority": 0,
            "total_medium_priority": 0,
            "total_low_priority": 0,
            "success": False,
            "error": str(e)
        }
