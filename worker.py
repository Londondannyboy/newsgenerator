"""
News Generator Worker - Temporal Python Worker

Executes NewsCreationWorkflow with all necessary activities.
"""

import asyncio
import os
import sys

from temporalio.client import Client
from temporalio.worker import Worker
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import workflow
from src.workflows.news_creation import NewsCreationWorkflow

# Import activities
from src.activities.dataforseo import dataforseo_news_search
from src.activities.serper import serper_news_search
from src.activities.news_assessment import assess_news_batch
from src.activities.intelligent_prompt_builder import build_intelligent_video_prompt
from src.activities.neon_articles import get_recent_articles_from_neon
from src.activities.zep_integration import query_zep_for_context

from src.config.config import config


async def main():
    """Start the News Generator worker"""

    print("=" * 70)
    print("📰 News Generator Worker - Starting...")
    print("=" * 70)

    # Display configuration
    print("\n🔧 Configuration:")
    print(f"   Temporal Address: {config.TEMPORAL_ADDRESS}")
    print(f"   Namespace: {config.TEMPORAL_NAMESPACE}")
    print(f"   Task Queue: {config.TEMPORAL_TASK_QUEUE}")
    print(f"   API Key: {'✅ Set' if config.TEMPORAL_API_KEY else '❌ Not set'}")
    print(f"   Environment: {config.ENVIRONMENT}")

    # Validate required environment variables
    missing = config.validate_required()

    if missing:
        print(f"\n❌ Missing required environment variables:")
        for var in missing:
            print(f"   - {var}")
        print("\n   Please set them in .env file or environment")
        sys.exit(1)

    print("\n✅ All required environment variables present")

    # Display service status
    print("\n📊 Service Status:")
    service_config = config.as_dict()
    for key, value in service_config.items():
        if key.startswith("has_"):
            service_name = key.replace("has_", "").upper()
            status = "✅" if value else "❌"
            print(f"   {status} {service_name}")

    # Connect to Temporal
    print(f"\n🔗 Connecting to Temporal Cloud...")

    try:
        if config.TEMPORAL_API_KEY:
            # Temporal Cloud with TLS
            client = await Client.connect(
                config.TEMPORAL_ADDRESS,
                namespace=config.TEMPORAL_NAMESPACE,
                api_key=config.TEMPORAL_API_KEY,
                tls=True,
            )
        else:
            # Local Temporal (development)
            client = await Client.connect(
                config.TEMPORAL_ADDRESS,
                namespace=config.TEMPORAL_NAMESPACE,
            )

        print("✅ Connected to Temporal successfully")

    except Exception as e:
        print(f"❌ Failed to connect to Temporal: {e}")
        sys.exit(1)

    # Create worker with workflow and activities
    worker = Worker(
        client,
        task_queue=config.TEMPORAL_TASK_QUEUE,
        workflows=[NewsCreationWorkflow],
        activities=[
            # News Research
            dataforseo_news_search,
            serper_news_search,

            # Assessment & Context
            assess_news_batch,
            get_recent_articles_from_neon,
            query_zep_for_context,

            # Media Generation
            build_intelligent_video_prompt
        ],
    )

    print("\n" + "=" * 70)
    print("🚀 News Generator Worker Started Successfully!")
    print("=" * 70)
    print(f"   Task Queue: {config.TEMPORAL_TASK_QUEUE}")
    print(f"   Environment: {config.ENVIRONMENT}")
    print("=" * 70)

    print("\n📋 Registered Workflows:")
    print("   - NewsCreationWorkflow")

    print("\n📋 Registered Activities:")
    activities_list = [
        ("News Research", ["dataforseo_news_search", "serper_news_search"]),
        ("Assessment", ["assess_news_batch"]),
        ("Context", ["get_recent_articles_from_neon", "query_zep_for_context"]),
        ("Media", ["build_intelligent_video_prompt"]),
    ]

    for group_name, activities in activities_list:
        print(f"\n   {group_name}:")
        for activity in activities:
            print(f"     - {activity}")

    print("\n✅ Worker is ready to process news workflows")
    print("   Press Ctrl+C to stop\n")

    # Run worker (blocks until interrupted)
    await worker.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 News Generator Worker stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ News Generator Worker crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
