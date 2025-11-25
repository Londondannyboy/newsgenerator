"""
DataForSEO API Activities
Primary source for news and SERP data with ISO timestamps
"""

import os
import base64
import json
import aiohttp
from typing import Any
from temporalio import activity

# DataForSEO location codes
LOCATION_CODES = {
    "UK": 2826,
    "US": 2840,
    "SG": 2702,  # Singapore
    "DE": 2276,  # Germany
    "FR": 2250,  # France
    "AU": 2036,  # Australia
    "CA": 2124,  # Canada
    "JP": 2392,  # Japan
    "HK": 2344,  # Hong Kong
}


def get_auth_header() -> str:
    """Get DataForSEO Basic Auth header"""
    login = os.getenv("DATAFORSEO_LOGIN", "")
    password = os.getenv("DATAFORSEO_PASSWORD", "")
    credentials = base64.b64encode(f"{login}:{password}".encode()).decode()
    return f"Basic {credentials}"


@activity.defn
async def dataforseo_news_search(
    keywords: list[str],
    regions: list[str] = None,
    depth: int = 70
) -> dict[str, Any]:
    """
    Search news using DataForSEO Google News API

    Args:
        keywords: List of search keywords
        regions: List of region codes (UK, US, SG, etc.)
        depth: Number of results per query (1-200, default 10, recommended 70)

    Returns:
        Dict with articles list and metadata
    """
    if regions is None:
        regions = ["UK", "US", "SG"]

    url = "https://api.dataforseo.com/v3/serp/google/news/live/advanced"
    auth = get_auth_header()

    all_results = []
    total_cost = 0

    async with aiohttp.ClientSession() as session:
        for keyword in keywords:
            for region in regions:
                location_code = LOCATION_CODES.get(region, 2826)

                payload = [{
                    "keyword": keyword,
                    "location_code": location_code,
                    "language_code": "en",
                    "depth": depth,
                    "calculate_rectangles": False
                }]

                try:
                    async with session.post(
                        url,
                        json=payload,
                        headers={
                            "Authorization": auth,
                            "Content-Type": "application/json"
                        },
                        timeout=aiohttp.ClientTimeout(total=120)
                    ) as response:
                        if response.status == 200:
                            data = await response.json()

                            if data.get("tasks") and data["tasks"][0].get("result"):
                                items = data["tasks"][0]["result"][0].get("items", [])
                                cost = data["tasks"][0].get("cost", 0)
                                total_cost += cost

                                for item in items:
                                    all_results.append({
                                        "title": item.get("title", ""),
                                        "url": item.get("url", ""),
                                        "source": item.get("domain", "").replace("www.", ""),
                                        "timestamp": item.get("timestamp", ""),
                                        "time_published": item.get("time_published", ""),
                                        "snippet": item.get("snippet", ""),
                                        "image_url": item.get("image_url", ""),
                                        "rank": item.get("rank_absolute", 0),
                                        "region": region,
                                        "keyword": keyword,
                                        "api_source": "dataforseo"
                                    })

                                activity.logger.info(
                                    f"DataForSEO news: {len(items)} results for '{keyword}' in {region}"
                                )
                        else:
                            activity.logger.error(
                                f"DataForSEO error: {response.status} for '{keyword}' in {region}"
                            )

                except Exception as e:
                    activity.logger.error(f"DataForSEO exception: {e}")
                    continue

    return {
        "articles": all_results,
        "total": len(all_results),
        "cost": total_cost,
        "regions": regions,
        "keywords": keywords
    }


@activity.defn
async def dataforseo_serp_search(
    query: str,
    region: str = "UK",
    depth: int = 70,
    include_ai_overview: bool = True,
    people_also_ask_depth: int = 4
) -> dict[str, Any]:
    """
    Search organic SERP results using DataForSEO with AI Overview and People Also Ask

    Args:
        query: Search query
        region: Region code (UK, US, SG, etc.)
        depth: Number of results (1-200, default 10, recommended 70 for 7 pages)
        include_ai_overview: Include Google AI Overview results
        people_also_ask_depth: Depth for "People also ask" results (0-4)

    Returns:
        Dict with organic results, AI overview, people also ask, and metadata
    """
    url = "https://api.dataforseo.com/v3/serp/google/organic/live/advanced"
    auth = get_auth_header()
    location_code = LOCATION_CODES.get(region, 2826)

    payload = [{
        "keyword": query,
        "location_code": location_code,
        "language_code": "en",
        "device": "desktop",
        "os": "windows",
        "depth": depth,
        "group_organic_results": True,
        "load_async_ai_overview": include_ai_overview,
        "people_also_ask_click_depth": people_also_ask_depth,
        "calculate_rectangles": False
    }]

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                url,
                json=payload,
                headers={
                    "Authorization": auth,
                    "Content-Type": "application/json"
                },
                timeout=aiohttp.ClientTimeout(total=120)
            ) as response:
                if response.status == 200:
                    data = await response.json()

                    results = []
                    cost = 0

                    if data.get("tasks") and data["tasks"][0].get("result"):
                        items = data["tasks"][0]["result"][0].get("items", [])
                        cost = data["tasks"][0].get("cost", 0)

                        for item in items:
                            if item.get("type") == "organic":
                                results.append({
                                    "title": item.get("title", ""),
                                    "url": item.get("url", ""),
                                    "source": item.get("domain", "").replace("www.", ""),
                                    "snippet": item.get("description", ""),
                                    "rank": item.get("rank_absolute", 0),
                                    "region": region,
                                    "api_source": "dataforseo"
                                })

                    activity.logger.info(
                        f"DataForSEO SERP: {len(results)} results for '{query}' in {region}"
                    )

                    return {
                        "results": results,
                        "total": len(results),
                        "cost": cost,
                        "query": query,
                        "region": region
                    }
                else:
                    activity.logger.error(f"DataForSEO SERP error: {response.status}")
                    return {"results": [], "total": 0, "cost": 0, "error": f"HTTP {response.status}"}

        except Exception as e:
            activity.logger.error(f"DataForSEO SERP exception: {e}")
            return {"results": [], "total": 0, "cost": 0, "error": str(e)}
