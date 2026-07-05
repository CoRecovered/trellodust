# Submission Write-Up

## Use Case

The project implements a Trello-to-Dust project briefing sync. The goal is to let a Dust agent answer project-management questions from a Trello board, including current blockers, overdue cards, recent activity, and standup status.

## How It Works

The command-line script reads one Trello board through the Trello REST API. It fetches board metadata, lists, cards, and recent activity. It then normalizes that data into a Markdown document grouped by Trello list, with dedicated sections for blocked or waiting cards, overdue cards, and recent activity.

The script publishes the Markdown into a Dust data-source document using Dust's document upsert API. The document payload includes a title, MIME type, text content, source URL, tags, timestamp, and upload options.

## Validation

The core behavior is validated offline with a realistic Trello fixture and unit tests. The tests check that cards are grouped by list, blocked and overdue work is surfaced, recent activity is preserved, and the Dust payload matches the expected document upsert shape.

Manual validation uses a dry run before publishing:

```bash
python3 trello_dust_sync.py sync --fixture fixtures/sample_trello_export.json --dry-run
python3 -m unittest discover -s tests
```

For live validation, the sync is run against a real Trello board, the generated Markdown is compared with the board, the document is uploaded to Dust, and a Dust agent is queried against the synced Trello content.

## Assumptions, Tradeoffs, and Limitations

This implementation syncs one Trello board into one Dust document. That scope keeps the workflow easy to demo and reason about while still covering the important Trello objects: board metadata, lists, cards, labels, due dates, checklist progress, links, and recent actions.

The sync is batch-oriented rather than real-time. For many project status workflows, scheduled sync is enough. In production, useful additions would include pagination, retry/backoff for rate limits, webhook-based incremental updates, richer member-name resolution, and observability around sync failures.

## Approach Rationale

A Dust data-source document upsert is used because the primary job is knowledge ingestion: make Trello project state available to a Dust agent. This keeps the integration simple, reliable, and low-risk.

A remote MCP server would be a reasonable alternative if the agent needed live Trello actions, such as creating cards, moving cards, or posting comments. For this use case, read-only sync is the safer and more focused technical solution.
