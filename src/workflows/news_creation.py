"""
News Creation Workflow

SCHEDULED workflow that runs daily to find and create news articles.

Pipeline:
1. Fetch news from DataForSEO (primary - ISO timestamps)
2. Fetch news from Serper (supplementary)
3. Deduplicate and merge results
4. Get recent articles (Neon) for duplicate check
5. AI assessment: relevance, priority
6. Build intelligent video prompt for each story
7. Spawn ArticleCreationWorkflow with video-first configuration
"""

from temporalio import workflow
from datetime import timedelta
from typing import Dict, Any, List

with workflow.unsafe.imports_passed_through():
    import asyncio
    from src.config.app_config import get_app_config, get_all_apps


@workflow.defn
class NewsCreationWorkflow:
    """
    Scheduled workflow that creates news articles with intelligent video prompts.

    Runs daily (or on schedule) to:
    1. Find relevant news for the app
    2. Use AI to assess if we should cover it
    3. Build intelligent, contextual video prompts
    4. Automatically create articles with video-first configuration
    """

    @workflow.run
    async def run(self, input_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute news monitoring workflow.

        Args:
            input_dict: {
                "app": "placement",
                "min_relevance_score": 0.7,
                "auto_create_articles": True,
                "max_articles_to_create": 3
            }

        Returns:
            Summary of monitoring results
        """
        app = input_dict.get("app", "placement")
        min_relevance = input_dict.get("min_relevance_score", 0.7)
        auto_create = input_dict.get("auto_create_articles", True)
        max_articles = input_dict.get("max_articles_to_create", 3)

        # Get full app configuration
        app_config = get_app_config(app)
        keywords = app_config.keywords
        exclusions = app_config.exclusions
        interests = app_config.interests
        geographic_focus = app_config.geographic_focus
        priority_sources = app_config.priority_sources
        target_audience = app_config.target_audience

        workflow.logger.info(f"News Monitor starting for app: {app}")
        workflow.logger.info(f"Keywords: {keywords[:3]}...")
        workflow.logger.info(f"Geographic focus: {geographic_focus}")

        # ===== PHASE 1A: FETCH NEWS FROM DATAFORSEO (PRIMARY) =====
        workflow.logger.info("Phase 1a: Fetching news from DataForSEO (primary)")

        # App-specific primary keywords for DataForSEO research
        dataforseo_keywords_by_app = {
            "placement": "private equity",
            "relocation": "Digital Nomad Visa"
        }
        dataforseo_keyword = dataforseo_keywords_by_app.get(app, "private equity")

        workflow.logger.info(f"DataForSEO primary keyword: {dataforseo_keyword}")

        # ===== PHASE 1A: FETCH NEWS FROM DATAFORSEO =====
        workflow.logger.info("Phase 1a: Fetching news from DataForSEO (UK)")

        dataforseo_result = await workflow.execute_activity(
            "dataforseo_news_search",
            args=[[dataforseo_keyword], ["UK"], 70],
            start_to_close_timeout=timedelta(minutes=10)
        )

        dataforseo_articles = dataforseo_result.get("articles", [])
        workflow.logger.info(f"DataForSEO news: {len(dataforseo_articles)} results")

        # ===== PHASE 1B: FETCH NEWS FROM SERPER (SUPPLEMENTARY) =====
        workflow.logger.info("Phase 1b: Fetching news from Serper (supplementary) - past 24 hours")

        serper_result = await workflow.execute_activity(
            "serper_news_search",
            args=[keywords, geographic_focus, 30, "qdr:d"],  # qdr:d = past 24 hours
            start_to_close_timeout=timedelta(minutes=2)
        )

        serper_articles = serper_result.get("articles", [])
        workflow.logger.info(f"Serper: {len(serper_articles)} results")

        # ===== PHASE 1C: DEDUPLICATE AND MERGE =====
        workflow.logger.info("Phase 1c: Deduplicating and merging results (news + organic + AI overview)")

        # Deduplicate by URL, prioritizing DataForSEO news (has timestamps)
        seen_urls = set()
        stories = []

        # Add DataForSEO news first (has ISO timestamps)
        for article in dataforseo_articles:
            url = article.get("url", "").lower().replace("www.", "").split("?")[0]
            if url and url not in seen_urls:
                seen_urls.add(url)
                stories.append(article)

        # Add Serper (supplementary)
        for article in serper_articles:
            url = article.get("url", "").lower().replace("www.", "").split("?")[0]
            if url and url not in seen_urls:
                seen_urls.add(url)
                stories.append(article)

        total_cost = dataforseo_result.get("cost", 0) + serper_result.get("cost", 0)
        workflow.logger.info(f"Total unique stories: {len(stories)} (dataforseo: {len(dataforseo_articles)}, serper: {len(serper_articles)}) (cost: ${total_cost:.3f})")

        if not stories:
            return {
                "app": app,
                "stories_found": 0,
                "stories_relevant": 0,
                "articles_created": 0,
                "message": "No news stories found for today"
            }

        # ===== PHASE 2: GET RECENT ARTICLES =====
        workflow.logger.info("Phase 2: Getting recently published from Neon")

        recent_articles = await workflow.execute_activity(
            "neon_get_recent_articles",
            args=[app, 7, 50],
            start_to_close_timeout=timedelta(seconds=30)
        )

        workflow.logger.info(f"Found {len(recent_articles)} recent articles")

        # ===== PHASE 3: AI ASSESSMENT =====
        workflow.logger.info("Phase 3: AI assessment of story relevance")

        # Build app context for AI assessment
        app_context = {
            "keywords": keywords,
            "exclusions": exclusions,
            "interests": interests,
            "target_audience": target_audience,
            "priority_sources": priority_sources
        }

        assessment_result = await workflow.execute_activity(
            "claude_assess_news",
            args=[
                stories,
                app,
                app_context,
                recent_articles,
                min_relevance
            ],
            start_to_close_timeout=timedelta(minutes=5)
        )

        relevant_stories = assessment_result.get("relevant_stories", [])

        workflow.logger.info(
            f"Assessment complete: {len(relevant_stories)} relevant stories "
            f"(high={assessment_result.get('total_high_priority', 0)}, "
            f"medium={assessment_result.get('total_medium_priority', 0)}, "
            f"low={assessment_result.get('total_low_priority', 0)})"
        )

        # ===== PHASE 4: PREPARE STORIES FOR ARTICLE CREATION =====
        # News-generator finds and assesses news - article creation happens in Quest content-worker
        stories_ready = []

        if relevant_stories:
            workflow.logger.info(f"Phase 4: Preparing top {max_articles} stories for article creation")

            # Sort by priority and relevance
            sorted_stories = sorted(
                relevant_stories,
                key=lambda x: (
                    0 if x.get("priority") == "high" else (1 if x.get("priority") == "medium" else 2),
                    -x.get("relevance_score", 0)
                )
            )

            # Prepare stories for article creation (by Quest content-worker)
            for story_assessment in sorted_stories[:max_articles]:
                story = story_assessment.get("story", {})
                priority = story_assessment.get("priority", "medium")
                story_title = story.get("title", "")

                workflow.logger.info(f"📰 Ready for article: [{priority.upper()}] {story_title[:60]}...")

                stories_ready.append({
                    "title": story.get("title"),
                    "url": story.get("url"),
                    "source": story.get("source"),
                    "description": story.get("description", story.get("snippet", "")),
                    "timestamp": story.get("timestamp", story.get("time_published", "")),
                    "priority": priority,
                    "relevance_score": story_assessment.get("relevance_score", 0),
                    "reasoning": story_assessment.get("reasoning", ""),
                    "app": app,
                    "suggested_article_type": "news",
                    "suggested_jurisdiction": geographic_focus[0] if geographic_focus else "UK"
                })

            workflow.logger.info(f"✅ {len(stories_ready)} stories ready for article creation")

        # ===== COMPLETE =====
        workflow.logger.info(
            f"News Monitor complete for {app}: "
            f"{len(stories)} found, {len(relevant_stories)} relevant, "
            f"{len(stories_ready)} ready for articles"
        )

        return {
            "app": app,
            "keywords": keywords[:3],
            "stories_found": len(stories),
            "stories_assessed": assessment_result.get("stories_assessed", 0),
            "stories_relevant": len(relevant_stories),
            "stories_ready_for_articles": len(stories_ready),
            "stories": stories_ready,  # Full story data for downstream processing
            "high_priority_count": assessment_result.get("total_high_priority", 0),
            "medium_priority_count": assessment_result.get("total_medium_priority", 0),
            "low_priority_count": assessment_result.get("total_low_priority", 0),
            "cost": total_cost,
            "dataforseo_count": len(dataforseo_articles),
            "serper_count": len(serper_articles)
        }
