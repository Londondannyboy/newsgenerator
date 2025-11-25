"""
Temporal Schedule Manager for News Generator

Creates and manages schedules for automated news monitoring workflows.
Runs NewsCreationWorkflow on a schedule for each configured app.
"""

import asyncio
import sys
from datetime import datetime
from temporalio.client import Client
from temporalio.api.enums.v1 import ScheduleOverlapPolicy
from temporalio.service import ScheduleService

from dotenv import load_dotenv
from src.utils.config import config
from src.workflows.news_creation import NewsCreationWorkflow

# Load environment variables
load_dotenv()


async def create_schedule(client: Client, app: str, app_display_name: str) -> None:
    """
    Create a schedule for news monitoring workflow.

    Args:
        client: Temporal client
        app: App name (e.g., "placement", "relocation")
        app_display_name: Display name for logging
    """
    schedule_id = f"news-monitor-{app}"

    try:
        # Try to get existing schedule
        schedule = await client.get_schedule(schedule_id)
        print(f"✅ Schedule '{schedule_id}' already exists for {app_display_name}")
        return
    except Exception:
        # Schedule doesn't exist, create it
        pass

    print(f"📅 Creating schedule '{schedule_id}' for {app_display_name}...")

    try:
        from temporalio.client import ScheduleDescription, ScheduleSpec, ScheduleAction, StartWorkflowAction

        # Create schedule that runs daily at 9 AM UTC
        await client.create_schedule(
            schedule_id,
            ScheduleDescription(
                schedule=ScheduleSpec(
                    cron="0 9 * * *"  # Daily at 9 AM UTC
                ),
                action=StartWorkflowAction(
                    workflow_type=NewsCreationWorkflow,
                    input=[
                        {
                            "app": app,
                            "min_relevance_score": 0.7,
                            "auto_create_articles": True,
                            "max_articles_to_create": 3
                        }
                    ],
                    task_queue=config.TEMPORAL_TASK_QUEUE,
                    workflow_id_reuse_policy=1  # Allow reuse
                )
            ),
            overlap_policy=ScheduleOverlapPolicy.SKIP
        )

        print(f"✅ Created schedule '{schedule_id}' - runs daily at 9 AM UTC")

    except Exception as e:
        print(f"❌ Failed to create schedule for {app}: {e}")
        raise


async def main():
    """Initialize all news monitoring schedules"""

    print("=" * 70)
    print("📰 News Generator - Schedule Manager")
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

    # Create schedules for each app
    print(f"\n📋 Creating schedules for configured apps:\n")

    apps = [
        ("placement", "Placement Agent Directory"),
        ("relocation", "Global Relocation Directory"),
    ]

    for app_name, app_display_name in apps:
        await create_schedule(client, app_name, app_display_name)

    print(f"\n{'='*70}")
    print(f"✅ All schedules initialized!")
    print(f"{'='*70}")
    print(f"\n📅 Next scheduled runs:")
    print(f"   - placement: Daily at 9 AM UTC")
    print(f"   - relocation: Daily at 9 AM UTC")
    print(f"\n   To view schedules: railway logs --service news-generator")

    await client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Schedule manager stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Schedule manager failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
