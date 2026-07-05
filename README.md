# Trello to Dust Project Brief Sync

This project implements a focused Dust assignment use case: keep a Dust agent's knowledge up to date with the current state of a Trello project board.

## Use case

Project managers often want to ask an AI agent questions like:

- What is blocked right now?
- What changed recently?
- Which cards are overdue or missing owners?
- What should I raise in the next standup?

The script reads Trello board, list, card, label, due-date, checklist, and recent activity data, then publishes a concise Markdown document into a Dust data source. A Dust agent can use that document as searchable project context.

## Why this approach

I chose Dust data-source document upsert instead of a remote MCP server for the first version because it is faster to build, easier to demo, and fits an asynchronous project-management sync pattern. Trello boards are not usually queried second-by-second; a scheduled sync every few minutes or hours is enough for most status-reporting workflows.

An MCP server would be a strong follow-up if users needed live Trello actions from inside Dust, such as moving a card or creating a comment. For this assignment, the data-source approach keeps the blast radius small while still connecting Trello data to Dust in a production-shaped way.

## Files

- `trello_dust_sync.py`: CLI sync tool.
- `fixtures/sample_trello_export.json`: offline sample board used for validation and demos.
- `tests/test_trello_dust_sync.py`: unit tests for transformation and Dust payload creation.
- `.env.example`: environment variables needed for a real sync.

## Setup

This project uses only the Python standard library.

```bash
cd dust-trello-assignment
python3 -m unittest discover -s tests
```

For a real Trello and Dust sync:

```bash
cp .env.example .env
```

Fill in:

- `TRELLO_API_KEY`
- `TRELLO_API_TOKEN`
- `TRELLO_BOARD_ID`
- `DUST_API_KEY`
- `DUST_WORKSPACE_ID`
- `DUST_SPACE_ID`
- `DUST_DATA_SOURCE_ID`

Then run:

```bash
python3 trello_dust_sync.py sync --dry-run
python3 trello_dust_sync.py sync
```

The dry run prints the generated Markdown and does not call Dust.

## Demo flow

1. Create a Trello board called `Dust Launch Plan`.
2. Add lists such as `Backlog`, `In Progress`, `Blocked`, and `Done`.
3. Add cards with labels, due dates, members, comments, and checklist items.
4. Run `python3 trello_dust_sync.py sync --dry-run` to show the normalized document.
5. Run `python3 trello_dust_sync.py sync` to publish to Dust.
6. In Dust, create an agent with access to the data source.
7. Ask:
   - "Summarize the current Trello board."
   - "Which work is blocked?"
   - "What changed recently?"
   - "What should I mention in standup?"

## Validation

I validated the transformation offline using a realistic Trello fixture and unit tests. The tests verify that:

- Cards are grouped under their Trello lists.
- Blocked, overdue, and completed cards are highlighted.
- Recent activity is included.
- The Dust upsert payload contains the expected title, MIME type, text, tags, source URL, timestamp, and async/lightweight flags.

For live validation, run the sync with `--dry-run` first, compare the output to the Trello board, then run without `--dry-run` and ask a Dust agent questions that require the synced content.

## Assumptions and limitations

- The script syncs one Trello board into one Dust document.
- It is designed for periodic batch sync, not real-time webhook updates.
- It reads open and closed cards so status history is visible.
- It does not mutate Trello data.
- It stores Trello member IDs rather than resolving all user display names, keeping the API surface small for the assignment.
- Larger production boards may need pagination, rate-limit backoff, and incremental sync state.

## References

- Trello boards API documents board cards, lists, members, and actions endpoints.
- Dust document API supports upserting a document into a workspace data source with `title`, `mime_type`, `text`, `source_url`, `tags`, and `timestamp`.
