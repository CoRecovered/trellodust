# Submission write-up

## Use case

I built a Trello-to-Dust project briefing sync. The goal is to let a Dust agent answer project-management questions from a Trello board, such as what is blocked, what is overdue, what changed recently, and what should be raised in a standup.

## How it works

The CLI reads one Trello board using the Trello REST API. It fetches board metadata, lists, cards, and recent activity. It then normalizes that data into a Markdown document grouped by Trello list, with special sections for blocked/waiting cards, overdue cards, and recent activity.

The script publishes that Markdown into a Dust data-source document using Dust's document upsert API. The document includes a title, MIME type, text content, source URL, tags, timestamp, and upload options.

## Validation

I validated the core behavior offline with a realistic Trello fixture and unit tests. The tests check that cards are grouped by list, blocked and overdue work is surfaced, recent activity is preserved, and the Dust payload matches the expected document upsert shape.

I also validated the output manually with a dry run:

```bash
python3 trello_dust_sync.py sync --fixture fixtures/sample_trello_export.json --dry-run
python3 -m unittest discover -s tests
```

For live validation, I would run the same sync against a real Trello board, confirm the generated Markdown matches the board, upload it to Dust, and ask a Dust agent questions that require the synced Trello context.

## Assumptions, tradeoffs, and limitations

This implementation syncs one Trello board into one Dust document. I chose that scope because it is easy to demo, easy to reason about, and appropriate for a 3-hour assignment.

The sync is batch-oriented rather than real-time. For many project status workflows, scheduled sync is enough. In production, I would add pagination, retry/backoff for rate limits, webhook-based incremental updates, richer member-name resolution, and observability around sync failures.

## Why this approach

I chose a Dust data-source document upsert rather than a remote MCP server because the primary job is knowledge ingestion: make Trello project state available to a Dust agent. This keeps the integration simple, reliable, and low-risk.

A remote MCP server would be a reasonable alternative if the agent needed to perform live Trello actions, such as creating cards, moving cards, or posting comments. For this assignment, read-only sync is the safer and more focused technical solution.

