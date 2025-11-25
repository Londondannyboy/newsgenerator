"""
Intelligent Video Prompt Builder

Generates contextual, creative video prompts by:
1. Analyzing article topic and content
2. Learning from recently published articles (patterns that work)
3. Using app-specific style guidelines
4. Creating specific, engaging prompts (not generic templates)

Examples:
- "Footballer kicks the ball at the private equity guy in a boardroom"
- "Golfers hitting the ball in their office overlooking the market"
- "Trading floor in 80s style with executives making deals"
"""

import os
from temporalio import activity
from typing import Dict, Any, List, Optional
import anthropic

# Import for database queries
try:
    from src.lib.neon import sql
except ImportError:
    sql = None


@activity.defn
async def build_intelligent_video_prompt(
    article_topic: str,
    article_content: str,
    app: str,
    recent_articles: Optional[List[Dict[str, Any]]] = None,
    app_config: Optional[Dict[str, Any]] = None,
    video_model: str = "seedance"
) -> Dict[str, Any]:
    """
    Build an intelligent, contextual video prompt by learning from published articles.

    Args:
        article_topic: Title/topic of the article
        article_content: Main content of the article
        app: Application name (placement, relocation, etc.)
        recent_articles: Recently published articles to learn from (optional)
        app_config: App-specific style configuration (optional)
        video_model: Video model being used (seedance, wan-2.5)

    Returns:
        Dict with:
        - prompt: The generated video prompt
        - style: The identified visual style
        - confidence: How confident the prompt matches the topic
        - learned_from: Number of articles analyzed for patterns
    """
    activity.logger.info(f"Building intelligent prompt for: {article_topic[:50]}...")

    # Get app configuration with style guidelines
    config = app_config or get_default_app_config(app)

    # Analyze the article to understand its nature
    topic_analysis = analyze_article_topic(article_topic, article_content, app)
    activity.logger.info(f"Topic analysis: {topic_analysis['category']} - {topic_analysis['tone']}")

    # Build context from recently published articles (learn patterns)
    learning_context = ""
    if recent_articles:
        learning_context = extract_style_patterns(recent_articles, app)
        activity.logger.info(f"Extracted patterns from {len(recent_articles)} published articles")

    # Use Claude to generate creative, contextual prompt
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    prompt_generation_prompt = build_prompt_generation_instruction(
        article_topic=article_topic,
        article_content=article_content,
        app=app,
        topic_analysis=topic_analysis,
        learning_context=learning_context,
        config=config,
        video_model=video_model
    )

    message = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1000,
        messages=[
            {"role": "user", "content": prompt_generation_prompt}
        ]
    )

    generated_prompt = message.content[0].text.strip()

    # Determine aspect ratio based on topic (dull topics might benefit from specific ratios)
    aspect_ratio = determine_aspect_ratio(topic_analysis, config)

    activity.logger.info(f"Generated prompt: {generated_prompt[:100]}...")
    activity.logger.info(f"Aspect ratio: {aspect_ratio}")

    return {
        "prompt": generated_prompt,
        "style": topic_analysis["category"],
        "tone": topic_analysis["tone"],
        "aspect_ratio": aspect_ratio,
        "confidence": topic_analysis["confidence"],
        "learned_from": len(recent_articles) if recent_articles else 0,
        "used_fallback": topic_analysis.get("is_dull", False)
    }


def analyze_article_topic(topic: str, content: str, app: str) -> Dict[str, Any]:
    """
    Analyze the article to determine its visual category and tone.
    """
    topic_lower = topic.lower()
    content_lower = content.lower()

    # Determine category based on keywords
    categories = {
        "sports": ["football", "soccer", "golfer", "golf", "player", "team", "sport", "match"],
        "finance": ["trading", "market", "deal", "investment", "acquisition", "fund", "finance"],
        "technology": ["tech", "software", "ai", "startup", "digital", "crypto", "blockchain"],
        "leadership": ["ceo", "executive", "management", "board", "leadership", "strategy"],
        "markets": ["stock", "market", "trading", "exchange", "price", "commodities"],
        "innovation": ["innovation", "product", "launch", "new", "creative", "breakthrough"]
    }

    category = "general"
    for cat, keywords in categories.items():
        if any(kw in topic_lower or kw in content_lower for kw in keywords):
            category = cat
            break

    # Determine tone
    tones = {
        "celebratory": ["wins", "success", "celebrates", "triumph", "accomplished", "record"],
        "analytical": ["analysis", "data", "report", "study", "research", "findings"],
        "urgent": ["crisis", "emergency", "urgent", "breaking", "alert", "warning"],
        "aspirational": ["potential", "opportunity", "growth", "future", "vision"],
        "instructional": ["how to", "guide", "tutorial", "steps", "process"]
    }

    tone = "professional"
    for t, keywords in tones.items():
        if any(kw in topic_lower or kw in content_lower for kw in keywords):
            tone = t
            break

    # Check if topic is "dull" (needs creative fallback)
    dull_keywords = ["report", "update", "announcement", "statement", "news", "meeting"]
    is_dull = any(kw in topic_lower for kw in dull_keywords) and len(content) < 500

    confidence = 0.7 if category == "general" else 0.9

    return {
        "category": category,
        "tone": tone,
        "is_dull": is_dull,
        "confidence": confidence
    }


def extract_style_patterns(articles: List[Dict[str, Any]], app: str) -> str:
    """
    Extract successful style patterns from recently published articles.

    Analyzes titles/topics to identify what types of videos work for this app.
    """
    if not articles:
        return ""

    # Extract topics from articles
    topics = [article.get("title", "").lower() for article in articles[:5]]

    pattern_summary = f"""
Recently published articles for {app}:
{chr(10).join([f"- {topic}" for topic in topics])}

These represent successful articles. Notice what topics work well for {app}.
Learn from this pattern when generating prompts.
"""

    return pattern_summary


def build_prompt_generation_instruction(
    article_topic: str,
    article_content: str,
    app: str,
    topic_analysis: Dict[str, Any],
    learning_context: str,
    config: Dict[str, Any],
    video_model: str
) -> str:
    """
    Build the instruction for Claude to generate a creative video prompt.
    """
    dull_fallback = ""
    if topic_analysis.get("is_dull"):
        dull_fallback = f"""
This appears to be a dull or generic topic. Use creative fallbacks from config:
{config.get('dull_topic_fallbacks', 'Use professional office/trading room vibes')}
Make it engaging with specific visual elements (not just generic business scenes).
"""

    instruction = f"""You are a creative video prompt engineer. Generate a cinematic, specific video prompt for this article.

ARTICLE TOPIC: {article_topic}
ARTICLE PREVIEW: {article_content[:300]}...

APP CONTEXT: {app}
CATEGORY: {topic_analysis['category']}
TONE: {topic_analysis['tone']}
VIDEO MODEL: {video_model}

{learning_context}

{dull_fallback}

STYLE GUIDELINES from config:
- {config.get('primary_style', 'Professional, cinematic')}
- {config.get('visual_elements', 'Real-world business scenarios')}
- Elements: {config.get('elements', 'offices, meetings, growth charts')}

IMPORTANT RULES:
1. Be SPECIFIC and CREATIVE - not generic templates
2. Include concrete visual elements (e.g., "Footballer kicks ball AT the PE guy IN a boardroom")
3. NO ON-SCREEN TEXT - AI struggles with text rendering. Use visual metaphors instead
4. Keep prompt under 150 words
5. Include "Quest" branding subtly (e.g., "with Quest branding in background")
6. Match the article's tone and category
7. Avoid clichés - be creative like the football example

EXAMPLES of good prompts:
- "Footballer kicks the ball at the private equity guy in a boardroom, cinematic, professional"
- "Golfers hitting the ball in an executive office overlooking the trading floor"
- "80s-style trading room with executives closing a deal, retro colors, upbeat energy"

Generate ONE specific, creative prompt for this article. Return ONLY the prompt text, no explanation."""

    return instruction


def determine_aspect_ratio(topic_analysis: Dict[str, Any], config: Dict[str, Any]) -> str:
    """
    Determine aspect ratio based on topic analysis.

    Some topics benefit from specific ratios:
    - 16:9 (default) - most business content
    - 1:2.5 (vertical) - for more intimate, focused visuals
    - 9:16 (portrait) - for mobile-first content
    """
    # Default is 16:9
    aspect_ratio = "16:9"

    # Override for specific categories
    if topic_analysis["category"] == "finance" and topic_analysis.get("is_dull"):
        # Dull finance content might work better with specific ratio
        aspect_ratio = config.get("dull_finance_ratio", "16:9")

    if topic_analysis["tone"] == "instructional":
        aspect_ratio = "9:16"  # Vertical for how-to videos

    return aspect_ratio


def get_default_app_config(app: str) -> Dict[str, Any]:
    """
    Get default app configuration with style guidelines.
    """
    app_configs = {
        "placement": {
            "primary_style": "Corporate finance, modern offices, deal-making",
            "visual_elements": "stock charts, business meetings, handshakes, success",
            "elements": "boardrooms, deal closing, growth charts, LP meetings",
            "dull_topic_fallbacks": "Trading floor vibes, financial documents, modern offices",
            "dull_finance_ratio": "16:9",
            "mood": "professional, ambitious, successful"
        },
        "relocation": {
            "primary_style": "Travel, international, lifestyle",
            "visual_elements": "cityscapes, airports, modern apartments, cultural diversity",
            "elements": "world landmarks, diverse people, modern cities, new beginnings",
            "dull_topic_fallbacks": "Journey metaphor with passports, global connectivity",
            "mood": "adventurous, hopeful, inspiring"
        },
        "pe_news": {
            "primary_style": "Investment, deal-making, finance",
            "visual_elements": "Boardroom negotiations, handshakes, growth momentum",
            "elements": "modern offices, deal closing, celebration, strategy sessions",
            "dull_topic_fallbacks": "80s trading floor, fast-paced decision making",
            "dull_finance_ratio": "16:9",
            "mood": "ambitious, strategic, triumphant"
        }
    }

    return app_configs.get(app, app_configs["placement"])
