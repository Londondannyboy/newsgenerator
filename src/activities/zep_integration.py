"""
Zep Knowledge Graph Integration

Activities for querying and syncing company data with Zep Cloud.
"""

from temporalio import activity
from typing import Dict, Any
from zep_cloud.client import AsyncZep
from zep_cloud.types import GraphSearchScope

from src.config.config import config
from src.models.zep_ontology import (
    extract_company_entity_from_payload,
    COMPANY_ENTITY_TYPE,
    DEAL_ENTITY_TYPE,
    PERSON_ENTITY_TYPE,
    EDGE_TYPES
)


def get_graph_id_for_app(app: str) -> str:
    """
    Map app type to Zep graph ID.

    Args:
        app: Application type (placement, relocation, etc.)

    Returns:
        Zep graph ID
    """
    graph_mapping = {
        "placement": "finance-knowledge",
        "relocation": "relocation"
    }

    return graph_mapping.get(app, "finance-knowledge")


@activity.defn
async def query_zep_for_context(
    company_name: str,
    domain: str,
    app: str = "placement"  # Default for backward compatibility
) -> Dict[str, Any]:
    """
    Query Zep knowledge graph for existing company coverage (graceful).

    This checks if we have articles, deals, or other content
    mentioning this company already. Returns empty results if Zep is unavailable.

    Args:
        company_name: Company name
        domain: Company domain
        app: Application type (placement, relocation) for graph selection

    Returns:
        Dict with articles, deals, found_existing_coverage (safe defaults if unavailable)
    """
    graph_id = get_graph_id_for_app(app)
    activity.logger.info(f"🔍 Querying Zep graph '{graph_id}' for: {company_name}")

    if not config.ZEP_API_KEY:
        activity.logger.warning("⚠️ ZEP_API_KEY not configured - proceeding without Zep context")
        return {
            "articles": [],
            "deals": [],
            "people": [],
            "found_existing_coverage": False,
            "available": False
        }

    try:
        client = AsyncZep(api_key=config.ZEP_API_KEY)

        # Search query combining company name and domain
        search_query = f"{company_name} {domain}".strip()

        # 1. Search episodes (narrative content)
        try:
            activity.logger.info(f"  Searching episodes...")
            episode_results = await client.graph.search(
                graph_id=graph_id,
                query=search_query,
                scope="episodes",  # Search narrative episodes
                limit=20
            )
        except Exception as e:
            activity.logger.warning(f"  ⚠️ Episode search failed: {e}")
            episode_results = None

        # 2. Search nodes/entities (structured entities)
        try:
            activity.logger.info(f"  Searching entities...")
            entity_results = await client.graph.search(
                graph_id=graph_id,
                query=search_query,
                scope="nodes",  # Search structured entities
                limit=20
            )
        except Exception as e:
            activity.logger.warning(f"  ⚠️ Entity search failed: {e}")
            entity_results = None

        # Extract structured entities from episode data
        extracted_deals = []
        extracted_people = []

        # Parse episode data for extracted_entities
        if episode_results and hasattr(episode_results, 'edges'):
            try:
                for edge in episode_results.edges:
                    if hasattr(edge, 'fact') and edge.fact:
                        try:
                            import json
                            # Try to parse the fact as JSON
                            fact_data = json.loads(edge.fact) if isinstance(edge.fact, str) else edge.fact
                            if isinstance(fact_data, dict):
                                # Extract entities if present
                                entities = fact_data.get('extracted_entities', {})
                                if entities.get('deals'):
                                    extracted_deals.extend(entities['deals'][:5])
                                if entities.get('people'):
                                    extracted_people.extend(entities['people'][:5])
                        except Exception:
                            pass
            except Exception as e:
                activity.logger.warning(f"  ⚠️ Failed to parse episodes: {e}")

        # Extract from nodes
        articles = []
        node_deals = []
        if entity_results:
            try:
                articles = extract_articles_from_results(entity_results)
                node_deals = extract_deals_from_results(entity_results)
            except Exception as e:
                activity.logger.warning(f"  ⚠️ Failed to extract from entities: {e}")

        # Combine deals from episodes and nodes
        all_deals = extracted_deals + node_deals

        # Deduplicate deals by name
        seen_deals = set()
        unique_deals = []
        for deal in all_deals:
            deal_name = deal.get('name', '')
            if deal_name and deal_name not in seen_deals:
                seen_deals.add(deal_name)
                unique_deals.append(deal)

        activity.logger.info(
            f"✅ Zep context: {len(articles)} articles, {len(unique_deals)} deals, {len(extracted_people)} people"
        )

        return {
            "articles": articles[:10],
            "deals": unique_deals[:15],  # Return more deals
            "people": extracted_people[:10],
            "found_existing_coverage": len(articles) > 0 or len(unique_deals) > 0,
            "total_episodes": len(episode_results.edges) if episode_results and hasattr(episode_results, 'edges') else 0,
            "total_entities": len(entity_results.nodes) if entity_results and hasattr(entity_results, 'nodes') else 0,
            "available": True
        }

    except Exception as e:
        activity.logger.warning(f"⚠️ Zep query failed - continuing without context: {e}")
        return {
            "articles": [],
            "deals": [],
            "people": [],
            "found_existing_coverage": False,
            "available": False,
            "error": str(e)
        }


@activity.defn
async def sync_company_to_zep(
    company_id: str,
    company_name: str,
    domain: str,
    summary: str,
    payload: Dict[str, Any],
    app: str = "placement"  # Default for backward compatibility
) -> Dict[str, Any]:
    """
    Sync company profile to Zep knowledge graph with ontology support.

    Creates:
    1. Typed Company entity (using ontology)
    2. Episode with narrative summary

    Args:
        company_id: Database company ID
        company_name: Company name
        domain: Company domain
        summary: Condensed company summary (<10k chars)
        payload: V2 flexible payload for extracting structured fields
        app: Application type (placement, relocation) for graph selection

    Returns:
        Dict with graph_id, success
    """
    graph_id = get_graph_id_for_app(app)
    activity.logger.info(f"Syncing {company_name} to Zep graph '{graph_id}' with ontology")

    if not config.ZEP_API_KEY:
        return {
            "graph_id": None,
            "success": False,
            "error": "ZEP_API_KEY not configured"
        }

    try:
        client = AsyncZep(api_key=config.ZEP_API_KEY)

        # Extract structured Company entity from flexible V2 payload
        company_entity = extract_company_entity_from_payload(
            company_name, domain, payload
        )

        activity.logger.info(f"Extracted company entity: {company_entity}")

        # Add episode with narrative summary and structured entity
        graph_data = {
            "company_id": company_id,
            "company_name": company_name,
            "summary": summary,
            "app": app,
            # Include structured entity attributes for ontology extraction
            "entity": company_entity
        }

        # Add to Zep using app-specific organizational graph
        # NOTE: type must be "json", "text", or "message" (not custom values)
        # NOTE: data must be a string (use json.dumps for structured data)
        import json as json_lib
        response = await client.graph.add(
            graph_id=graph_id,
            type="json",  # Valid GraphDataType enum value
            data=json_lib.dumps(graph_data)  # Convert dict to JSON string
        )

        activity.logger.info(f"Company synced to Zep graph '{graph_id}': {company_name}")
        activity.logger.info(f"Zep response: {response}")

        # Extract episode_id from response if available
        episode_id = None
        if response and hasattr(response, 'episode_id'):
            episode_id = response.episode_id
        elif response and isinstance(response, dict):
            episode_id = response.get('episode_id')

        return {
            "graph_id": graph_id,
            "episode_id": episode_id,
            "success": True,
            "entity": company_entity
        }

    except Exception as e:
        activity.logger.error(f"Zep sync failed: {e}")
        return {
            "graph_id": None,
            "success": False,
            "error": str(e)
        }


@activity.defn
async def create_zep_summary(
    payload: Dict[str, Any],
    zep_context: Dict[str, Any]
) -> str:
    """
    Create condensed summary for Zep storage (<10k chars).

    Args:
        payload: Full CompanyPayload
        zep_context: Existing Zep context

    Returns:
        Condensed summary string
    """
    activity.logger.info("Creating Zep summary")

    # Extract comprehensive information
    name = payload.get("legal_name", "Unknown")
    tagline = payload.get("tagline", "")
    description = payload.get("short_description", "")
    long_desc = payload.get("description", "")
    hq = payload.get("headquarters", "")
    industry = payload.get("industry", "")
    services = payload.get("services", [])
    specializations = payload.get("specializations", [])
    notable_deals = payload.get("notable_deals", [])
    executives = payload.get("executives", [])
    key_clients = payload.get("key_clients", [])
    office_locations = payload.get("office_locations", [])
    hero_stats = payload.get("hero_stats", {})

    # Build comprehensive summary
    summary_parts = [
        f"Company: {name}",
        f"Tagline: {tagline}" if tagline else "",
        "",
        f"Short Description: {description}" if description else "",
        f"Full Description: {long_desc[:500]}" if long_desc else "",
        "",
        f"Headquarters: {hq}" if hq else "",
        f"Industry: {industry}" if industry else "",
        "",
    ]

    # Hero stats (key metrics)
    if hero_stats:
        stats = []
        if hero_stats.get("founded_year"):
            stats.append(f"Founded: {hero_stats['founded_year']}")
        if hero_stats.get("employees"):
            stats.append(f"Employees: {hero_stats['employees']}")
        if hero_stats.get("serviced_deals"):
            stats.append(f"Deals: {hero_stats['serviced_deals']}")
        if hero_stats.get("serviced_companies"):
            stats.append(f"Companies: {hero_stats['serviced_companies']}")
        if stats:
            summary_parts.append(f"Key Stats: {' | '.join(stats)}")
            summary_parts.append("")

    # Services and specializations
    if services:
        summary_parts.append(f"Services: {', '.join(services[:10])}")
    if specializations:
        summary_parts.append(f"Specializations: {', '.join(specializations[:10])}")
    if services or specializations:
        summary_parts.append("")

    # Key clients
    if key_clients:
        clients_text = f"Key Clients: {', '.join(key_clients[:10])}"
        summary_parts.append(clients_text)
        summary_parts.append("")

    # Office locations
    if office_locations:
        locations = [loc.get("city", "") for loc in office_locations[:5] if loc.get("city")]
        if locations:
            summary_parts.append(f"Offices: {', '.join(locations)}")
            summary_parts.append("")

    # Executives
    if executives:
        summary_parts.append("Leadership:")
        for exec in executives[:5]:
            exec_name = exec.get("name", "")
            exec_title = exec.get("title", "")
            if exec_name:
                summary_parts.append(f"- {exec_name}, {exec_title}" if exec_title else f"- {exec_name}")
        summary_parts.append("")

    # Notable deals
    if notable_deals:
        summary_parts.append("Notable Deals:")
        for deal in notable_deals[:5]:
            deal_name = deal.get("name", "")
            deal_date = deal.get("date", "")
            deal_amount = deal.get("amount", "")
            deal_line = f"- {deal_name}"
            if deal_amount:
                deal_line += f" ({deal_amount})"
            if deal_date:
                deal_line += f" - {deal_date}"
            summary_parts.append(deal_line)
        summary_parts.append("")

    # Add existing coverage context
    existing_articles = zep_context.get("articles", [])
    if existing_articles:
        summary_parts.append(
            f"Previously covered in {len(existing_articles)} articles"
        )

    summary = "\n".join(p for p in summary_parts if p)

    # Truncate to 10k chars
    if len(summary) > 10000:
        summary = summary[:9950] + "... [truncated]"

    activity.logger.info(f"Summary created: {len(summary)} chars")

    return summary


def extract_articles_from_results(results: Any) -> list[Dict[str, Any]]:
    """
    Extract article information from Zep search results.

    Args:
        results: Zep search results

    Returns:
        List of article dicts
    """
    articles = []

    if not hasattr(results, 'nodes'):
        return articles

    for node in results.nodes:
        # Check if node is an article
        node_type = getattr(node, 'type', '')
        if node_type == 'article':
            articles.append({
                "id": getattr(node, 'uuid', ''),
                "name": getattr(node, 'name', ''),
                "summary": getattr(node, 'summary', '')
            })

    return articles


def extract_deals_from_results(results: Any) -> list[Dict[str, Any]]:
    """
    Extract deal information from Zep search results.

    Args:
        results: Zep search results

    Returns:
        List of deal dicts
    """
    deals = []

    if not hasattr(results, 'nodes'):
        return deals

    for node in results.nodes:
        # Check if node is a deal
        node_type = getattr(node, 'type', '')
        if node_type == 'deal':
            deals.append({
                "id": getattr(node, 'uuid', ''),
                "name": getattr(node, 'name', ''),
                "summary": getattr(node, 'summary', '')
            })

    return deals


@activity.defn
async def sync_article_to_zep(
    article_id: str,
    title: str,
    slug: str,
    content: str,
    excerpt: str,
    article_type: str,
    mentioned_companies: list,
    app: str = "placement"
) -> Dict[str, Any]:
    """
    Sync article to Zep knowledge graph as an episode.

    Creates:
    1. Episode with condensed article content
    2. Links to mentioned companies as entities

    Args:
        article_id: Database article ID
        title: Article title
        slug: Article slug
        content: Full article content (will be condensed)
        excerpt: Article excerpt
        article_type: Type (news, guide, comparison)
        mentioned_companies: List of company mentions with relevance scores
        app: Application type for graph selection

    Returns:
        Dict with graph_id, episode_id, success
    """
    graph_id = get_graph_id_for_app(app)
    activity.logger.info(f"Syncing article '{title}' to Zep graph '{graph_id}'")

    if not config.ZEP_API_KEY:
        return {
            "graph_id": None,
            "episode_id": None,
            "success": False,
            "error": "ZEP_API_KEY not configured"
        }

    try:
        client = AsyncZep(api_key=config.ZEP_API_KEY)

        # Create structured summary for Zep (matching company pattern)
        # Keep it concise - Zep works better with structured data

        # Build companies summary
        companies_summary = ""
        if mentioned_companies:
            companies_count = len(mentioned_companies)
            companies_summary = f"\n\nMENTIONED COMPANIES ({companies_count}):\n"
            for company in mentioned_companies[:10]:  # Top 10
                company_name = company.get("name", "Unknown")
                relevance = company.get("relevance_score", 0)
                is_primary = company.get("is_primary", False)
                primary_marker = " [PRIMARY]" if is_primary else ""
                companies_summary += f"- {company_name} (relevance: {relevance:.2f}){primary_marker}\n"

        # Build content summary (first 3000 chars for Zep)
        content_summary = f"\n\nCONTENT EXCERPT:\n{content[:3000]}" if content else ""

        # Build episode data (matching company sync pattern)
        episode_data = {
            "article_id": article_id,
            "title": title,
            "slug": slug,
            "article_type": article_type,
            "app": app,
            "excerpt": excerpt,
            "entity_type": "article",
            # Structured entity data (like company sync)
            "entity": {
                "name": title,
                "type": "article",
                "article_type": article_type,
                "app": app,
                "slug": slug
            },
            # Mentioned companies as structured entities
            "mentioned_companies": [
                {
                    "name": c.get("name"),
                    "relevance_score": c.get("relevance_score", 0),
                    "is_primary": c.get("is_primary", False),
                    "mention_count": c.get("mention_count", 1)
                }
                for c in mentioned_companies[:15]
            ],
            # Structured summary (like company sync)
            "structured_summary": companies_summary + content_summary
        }

        # Add to Zep graph
        import json as json_lib
        response = await client.graph.add(
            graph_id=graph_id,
            type="json",
            data=json_lib.dumps(episode_data)
        )

        activity.logger.info(f"Article synced to Zep graph '{graph_id}': {title}")

        # Extract episode_id from response
        episode_id = None
        if response and hasattr(response, 'episode_id'):
            episode_id = response.episode_id
        elif response and isinstance(response, dict):
            episode_id = response.get('episode_id')

        return {
            "graph_id": graph_id,
            "episode_id": episode_id,
            "success": True,
            "companies_linked": len(mentioned_companies)
        }

    except Exception as e:
        activity.logger.error(f"Zep article sync failed: {e}")
        return {
            "graph_id": None,
            "episode_id": None,
            "success": False,
            "error": str(e)
        }


@activity.defn
async def sync_v2_profile_to_zep_graph(
    company_id: str,
    company_name: str,
    domain: str,
    payload: Dict[str, Any],
    extracted_entities: Dict[str, Any],
    app: str = "placement"
) -> Dict[str, Any]:
    """
    Sync V2 profile to Zep as structured graph entities.

    Creates:
    1. Company entity (typed)
    2. Deal entities (from extracted deals)
    3. Person entities (from extracted people)
    4. Edges linking them

    Args:
        company_id: Database company ID
        company_name: Company name
        domain: Company domain
        payload: V2 flexible payload
        extracted_entities: Entities extracted from narrative
        app: Application type for graph selection

    Returns:
        Dict with success, entity IDs, counts
    """
    graph_id = get_graph_id_for_app(app)
    activity.logger.info(
        f"Syncing {company_name} to Zep graph '{graph_id}' as structured entities"
    )

    if not config.ZEP_API_KEY:
        return {
            "success": False,
            "error": "ZEP_API_KEY not configured"
        }

    try:
        client = AsyncZep(api_key=config.ZEP_API_KEY)

        # Extract company properties from payload
        company_entity_data = extract_company_entity_from_payload(
            company_name, domain, payload
        )

        activity.logger.info(f"Creating Company entity: {company_name}")

        # 1. Create Company entity
        # Note: Zep entity creation API might be: client.graph.add_node() or similar
        # For now, we'll continue using episode sync as primary
        # TODO: Update once Zep Python SDK supports entity.create() method

        # Create summary with entities for episode
        deals_summary = ""
        if extracted_entities.get("deals"):
            deals_count = len(extracted_entities["deals"])
            deals_summary = f"\n\nKNOWN DEALS ({deals_count}):\n"
            for deal in extracted_entities["deals"][:10]:  # Top 10
                deals_summary += f"- {deal['name']} ({deal.get('value', 'N/A')}) - {deal.get('date', 'N/A')}\n"

        people_summary = ""
        if extracted_entities.get("people"):
            people_count = len(extracted_entities["people"])
            people_summary = f"\n\nKEY PEOPLE ({people_count}):\n"
            for person in extracted_entities["people"][:10]:  # Top 10
                people_summary += f"- {person['name']}, {person.get('role', 'N/A')}\n"

        # Build enhanced episode data
        enhanced_data = {
            "company_id": company_id,
            "company_name": company_name,
            "domain": domain,
            "app": app,
            "entity": company_entity_data,
            "extracted_entities": {
                "deals_count": len(extracted_entities.get("deals", [])),
                "people_count": len(extracted_entities.get("people", [])),
                "deals": extracted_entities.get("deals", []),
                "people": extracted_entities.get("people", [])
            },
            "structured_summary": deals_summary + people_summary
        }

        # Add enhanced episode to Zep
        import json as json_lib
        response = await client.graph.add(
            graph_id=graph_id,
            type="json",
            data=json_lib.dumps(enhanced_data)
        )

        activity.logger.info(
            f"Company synced to Zep graph '{graph_id}' with {len(extracted_entities.get('deals', []))} deals "
            f"and {len(extracted_entities.get('people', []))} people"
        )

        # Extract episode_id from response
        episode_id = None
        if response and hasattr(response, 'episode_id'):
            episode_id = response.episode_id
        elif response and isinstance(response, dict):
            episode_id = response.get('episode_id')

        return {
            "graph_id": graph_id,
            "episode_id": episode_id,
            "success": True,
            "company_entity": company_entity_data,
            "deals_count": len(extracted_entities.get("deals", [])),
            "people_count": len(extracted_entities.get("people", []))
        }

    except Exception as e:
        activity.logger.error(f"Zep graph sync failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }
