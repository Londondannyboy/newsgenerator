# News Generator - Standalone Temporal Workflow Service

Automated news monitoring and article creation pipeline. Runs daily to find relevant news, assess relevance using AI, and trigger article creation workflows.

## Architecture

**Standalone Service** that:
1. Monitors news from DataForSEO and Serper APIs
2. Uses Claude AI to assess relevance and priority
3. Queries Neon database for recent articles (deduplication)
4. Queries Zep knowledge graph for existing coverage
5. Generates intelligent video prompts for articles
6. **Spawns ArticleCreationWorkflow** on content-worker task queue

No dependencies on content-worker codebase. Deploys independently to Railway.

## Setup

### 1. Clone and Install

```bash
git clone https://github.com/Londondannyboy/newsgenerator.git
cd newsgenerator

pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

**Required:**
- `TEMPORAL_ADDRESS`, `TEMPORAL_NAMESPACE`, `TEMPORAL_API_KEY` - Temporal Cloud
- `TEMPORAL_TASK_QUEUE=quest-content-queue` - **Must match content-worker**
- `ANTHROPIC_API_KEY` (or GOOGLE_API_KEY or OPENAI_API_KEY)
- `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD`
- `SERPER_API_KEY`
- `DATABASE_URL` - Neon PostgreSQL connection

**Optional (graceful failure):**
- `ZEP_API_KEY` - Zep Cloud for duplicate detection

### 3. Run Locally

#### Option A: Run Worker (Process Workflows)

```bash
python worker.py
```

The worker will connect to Temporal and wait for scheduled workflows.

#### Option B: Create Schedules (One-time Setup)

```bash
python scheduler.py
```

Creates daily schedules for each app (placement, relocation) at 9 AM UTC.

## Workflows

### NewsCreationWorkflow

**Trigger:** Daily schedule (9 AM UTC) or manual execution

**Pipeline:**
1. Fetch news from DataForSEO (UK primary)
2. Fetch supplementary news from Serper (24 hours)
3. Get recent articles from Neon (7 days)
4. Claude AI assessment - filter & prioritize stories
5. For each high-priority story:
   - Query Zep for existing coverage
   - Build intelligent video prompt
   - Spawn ArticleCreationWorkflow (child workflow on content-worker)

**Input:**
```python
{
    "app": "placement",              # App name
    "min_relevance_score": 0.7,      # Relevance threshold
    "auto_create_articles": True,    # Automatically create articles
    "max_articles_to_create": 3      # Max articles per run
}
```

**Output:**
```python
{
    "app": "placement",
    "stories_found": 45,             # Total stories fetched
    "stories_relevant": 8,           # After AI assessment
    "articles_created": 3,           # Actually created
    "cost": 0.15,                    # Estimated API cost
    # ... more details
}
```

## Apps Supported

- **placement** - Private equity placement agents and fund distribution
- **relocation** - Global mobility and corporate relocation services

Each app has its own keywords, exclusions, interests, and geographic focus defined in `src/config/app_config.py`.

## Cost Estimation

**Per Workflow Execution:**
- DataForSEO news search: ~$0.10
- Serper news search: ~$0.02
- Claude Haiku assessment: ~$0.01
- Claude Haiku video prompt: ~$0.02
- **Total: ~$0.15**

**Monthly (daily execution):**
- ~$4.50 per app
- ~$9 for 2 apps

## Activities

### Research
- `dataforseo_news_search` - DataForSEO News API
- `serper_news_search` - Serper Google News search

### Assessment & Context
- `assess_news_batch` - Claude AI relevance assessment
- `get_recent_articles_from_neon` - Recent articles for deduplication
- `query_zep_for_context` - Zep knowledge graph for existing coverage

### Media Generation
- `build_intelligent_video_prompt` - AI-generated contextual video prompts

## Deployment

### Railway

1. Link to Railway project:
```bash
railway link
```

2. Set environment variables in Railway:
```bash
railway variables set TEMPORAL_API_KEY=...
railway variables set ANTHROPIC_API_KEY=...
# ... all other vars from .env
```

3. Create Procfile for Railway:
```
worker: python worker.py
scheduler: python scheduler.py
```

4. Deploy:
```bash
git push origin main
# Railway auto-deploys on push
```

### Manual Execution

```bash
# Run one-off workflow
python -c "
import asyncio
from temporalio.client import Client
from src.workflows.news_creation import NewsCreationWorkflow
from src.config.config import config

async def run():
    client = await Client.connect(config.TEMPORAL_ADDRESS, namespace=config.TEMPORAL_NAMESPACE, api_key=config.TEMPORAL_API_KEY, tls=True)
    result = await client.execute_workflow(NewsCreationWorkflow.run, {
        'app': 'placement',
        'min_relevance_score': 0.7,
        'auto_create_articles': True,
        'max_articles_to_create': 3
    }, id='news-placement-manual-' + str(int(time.time())))
    print(result)

asyncio.run(run())
"
```

## Monitoring

### Check Logs

```bash
railway logs --service news-generator
```

### View Scheduled Workflows

In Temporal Cloud UI, search for workflow ID patterns:
- `news-creation-placement-scheduled-*`
- `news-creation-relocation-scheduled-*`

### Monitor Child Workflows

Child workflows (ArticleCreationWorkflow) are spawned on the content-worker task queue. Monitor in content-worker logs:

```bash
railway logs --service content-worker
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'psycopg2'"

Install dependencies:
```bash
pip install -r requirements.txt
```

### "Activity ... not registered"

Make sure worker is running:
```bash
python worker.py
```

###  "Failed to connect to Temporal"

Check:
- `TEMPORAL_ADDRESS` - correct endpoint
- `TEMPORAL_API_KEY` - valid API key
- `TEMPORAL_NAMESPACE` - correct namespace
- Network connectivity

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ News Generator Service (Standalone)                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Scheduler (Creates daily schedules)                        │
│      ↓                                                      │
│  NewsCreationWorkflow (Runs daily at 9 AM UTC)             │
│      ├→ dataforseo_news_search                             │
│      ├→ serper_news_search                                 │
│      ├→ get_recent_articles_from_neon                      │
│      ├→ assess_news_batch (Claude AI)                      │
│      ├→ query_zep_for_context                              │
│      ├→ build_intelligent_video_prompt (Claude AI)         │
│      └→ execute_child_workflow(ArticleCreationWorkflow)    │
│                                                             │
│  Database: Neon PostgreSQL (shared)                         │
│  Knowledge Graph: Zep Cloud (shared)                        │
│  Temporal: Temporal Cloud (shared)                          │
└─────────────────────────────────────────────────────────────┘
                             ↓
            (spawns child workflow on)
                             ↓
┌─────────────────────────────────────────────────────────────┐
│ Content Worker Service (Separate)                           │
├─────────────────────────────────────────────────────────────┤
│  ArticleCreationWorkflow (processes articles)               │
│  + CompanyCreationWorkflow                                  │
│  + other workflows/activities                               │
└─────────────────────────────────────────────────────────────┘
```

## Files

```
newsgenerator/
├── worker.py                    # Main worker - processes workflows
├── scheduler.py                 # Creates Temporal schedules
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment variables template
├── README.md                    # This file
├── src/
│   ├── workflows/
│   │   └── news_creation.py    # NewsCreationWorkflow
│   ├── activities/
│   │   ├── dataforseo.py       # DataForSEO news search
│   │   ├── serper.py           # Serper news search
│   │   ├── news_assessment.py  # Claude AI assessment
│   │   ├── intelligent_prompt_builder.py  # Video prompt generation
│   │   ├── neon_articles.py    # Recent articles query
│   │   └── zep_integration.py  # Zep knowledge graph query
│   ├── config/
│   │   ├── config.py           # Configuration management
│   │   └── app_config.py       # App-specific keywords/interests
│   └── models/
│       └── zep_ontology.py     # Zep data models
```

## License

Internal use only.
