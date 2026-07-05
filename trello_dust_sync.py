#!/usr/bin/env python3
"""Sync a Trello board summary into a Dust data-source document."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


TRELLO_API_BASE = "https://api.trello.com/1"
DUST_API_BASE = "https://dust.tt/api/v1"


class ConfigError(Exception):
    pass


def load_dotenv(path: Path) -> None:
    candidates = [path]
    if path.name == ".env" and path.parent.exists():
        candidates.append(path.with_name(".env.example"))

    for candidate in candidates:
        if not candidate.exists():
            continue
        for raw_line in candidate.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            parsed_value = value.strip().strip('"').strip("'")
            if not parsed_value:
                continue
            os.environ.setdefault(key.strip(), parsed_value)
        break


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> Any:
    data = None
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed with {exc.code}: {error_body}") from exc

    return json.loads(response_body) if response_body else {}


class TrelloClient:
    def __init__(self, api_key: str, token: str) -> None:
        self.api_key = api_key
        self.token = token

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = {"key": self.api_key, "token": self.token}
        if params:
            query.update(params)
        url = f"{TRELLO_API_BASE}{path}?{urllib.parse.urlencode(query)}"
        return http_json("GET", url)

    def export_board(self, board_id: str, action_limit: int = 25) -> dict[str, Any]:
        board = self.get(
            f"/boards/{board_id}",
            {
                "fields": "name,desc,url,dateLastActivity,closed",
            },
        )
        lists = self.get(
            f"/boards/{board_id}/lists",
            {
                "fields": "name,closed,pos",
                "filter": "all",
            },
        )
        cards = self.get(
            f"/boards/{board_id}/cards/all",
            {
                "fields": ",".join(
                    [
                        "name",
                        "desc",
                        "idList",
                        "closed",
                        "due",
                        "dueComplete",
                        "dateLastActivity",
                        "labels",
                        "idMembers",
                        "shortUrl",
                        "badges",
                    ]
                ),
            },
        )
        actions = self.get(
            f"/boards/{board_id}/actions",
            {
                "filter": "commentCard,updateCard,createCard",
                "limit": action_limit,
            },
        )
        return {"board": board, "lists": lists, "cards": cards, "actions": actions}


def sorted_lists(lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(lists, key=lambda item: (item.get("pos", 0), item.get("name", "")))


def is_blocked(card: dict[str, Any], list_name: str) -> bool:
    label_names = {label.get("name", "").lower() for label in card.get("labels", [])}
    text = f"{card.get('name', '')} {card.get('desc', '')} {list_name}".lower()
    return "blocked" in label_names or "blocked" in text or "waiting" in text


def is_overdue(card: dict[str, Any], reference_time: dt.datetime) -> bool:
    due = parse_iso(card.get("due"))
    return bool(due and due < reference_time and not card.get("dueComplete"))


def format_card(card: dict[str, Any], list_name: str, reference_time: dt.datetime) -> str:
    labels = ", ".join(label.get("name") or label.get("color", "") for label in card.get("labels", []))
    badges = card.get("badges") or {}
    checklist_total = badges.get("checkItems", 0)
    checklist_done = badges.get("checkItemsChecked", 0)
    members = ", ".join(card.get("idMembers", [])) or "Unassigned"
    status_bits = []
    if card.get("closed"):
        status_bits.append("archived")
    if card.get("dueComplete"):
        status_bits.append("done")
    if is_blocked(card, list_name):
        status_bits.append("blocked")
    if is_overdue(card, reference_time):
        status_bits.append("overdue")

    lines = [f"- {card.get('name', 'Untitled card')}"]
    lines.append(f"  - Status: {', '.join(status_bits) if status_bits else 'active'}")
    lines.append(f"  - Members: {members}")
    if labels:
        lines.append(f"  - Labels: {labels}")
    if card.get("due"):
        lines.append(f"  - Due: {card['due']} (complete: {bool(card.get('dueComplete'))})")
    if checklist_total:
        lines.append(f"  - Checklist: {checklist_done}/{checklist_total}")
    if badges.get("comments"):
        lines.append(f"  - Comments: {badges['comments']}")
    if card.get("desc"):
        lines.append(f"  - Notes: {single_line(card['desc'])}")
    if card.get("shortUrl"):
        lines.append(f"  - URL: {card['shortUrl']}")
    return "\n".join(lines)


def single_line(value: str, limit: int = 280) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "..."


def format_action(action: dict[str, Any]) -> str:
    data = action.get("data") or {}
    member = (action.get("memberCreator") or {}).get("fullName", "Unknown")
    card = (data.get("card") or {}).get("name", "Unknown card")
    action_type = action.get("type", "activity")
    date = action.get("date", "unknown date")

    if action_type == "commentCard":
        text = single_line(data.get("text", ""))
        return f"- {date}: {member} commented on '{card}': {text}"
    if data.get("listBefore") and data.get("listAfter"):
        before = data["listBefore"].get("name", "unknown")
        after = data["listAfter"].get("name", "unknown")
        return f"- {date}: {member} moved '{card}' from {before} to {after}"
    return f"- {date}: {member} performed {action_type} on '{card}'"


def build_markdown(export: dict[str, Any], reference_time: dt.datetime | None = None) -> str:
    reference_time = reference_time or now_utc()
    board = export["board"]
    lists = sorted_lists(export.get("lists", []))
    cards = export.get("cards", [])
    actions = export.get("actions", [])
    list_by_id = {item["id"]: item for item in lists}
    cards_by_list: dict[str, list[dict[str, Any]]] = {item["id"]: [] for item in lists}
    for card in cards:
        cards_by_list.setdefault(card.get("idList", "unknown"), []).append(card)

    blocked_cards = [
        card
        for card in cards
        if is_blocked(card, (list_by_id.get(card.get("idList")) or {}).get("name", "Unknown"))
    ]
    overdue_cards = [card for card in cards if is_overdue(card, reference_time)]
    completed_cards = [card for card in cards if card.get("dueComplete")]

    lines = [
        f"# Trello Project Brief: {board.get('name', 'Untitled board')}",
        "",
        f"Source: {board.get('url', 'Unknown')}",
        f"Last Trello activity: {board.get('dateLastActivity', 'Unknown')}",
        f"Synced at: {reference_time.isoformat()}",
        "",
    ]
    if board.get("desc"):
        lines.extend(["## Board description", "", board["desc"], ""])

    lines.extend(
        [
            "## Executive summary",
            "",
            f"- Total cards: {len(cards)}",
            f"- Open cards: {sum(1 for card in cards if not card.get('closed'))}",
            f"- Blocked cards: {len(blocked_cards)}",
            f"- Overdue cards: {len(overdue_cards)}",
            f"- Cards with completed due dates: {len(completed_cards)}",
            "",
        ]
    )

    if blocked_cards:
        lines.extend(["## Blocked or waiting", ""])
        for card in blocked_cards:
            list_name = (list_by_id.get(card.get("idList")) or {}).get("name", "Unknown")
            lines.append(f"- {card.get('name', 'Untitled card')} ({list_name})")
        lines.append("")

    if overdue_cards:
        lines.extend(["## Overdue", ""])
        for card in overdue_cards:
            list_name = (list_by_id.get(card.get("idList")) or {}).get("name", "Unknown")
            lines.append(f"- {card.get('name', 'Untitled card')} ({list_name}) due {card.get('due')}")
        lines.append("")

    lines.extend(["## Board by list", ""])
    for trello_list in lists:
        list_cards = sorted(
            cards_by_list.get(trello_list["id"], []),
            key=lambda card: card.get("dateLastActivity", ""),
            reverse=True,
        )
        lines.extend([f"### {trello_list.get('name', 'Unnamed list')}", ""])
        if not list_cards:
            lines.extend(["No cards.", ""])
            continue
        for card in list_cards:
            lines.append(format_card(card, trello_list.get("name", ""), reference_time))
        lines.append("")

    if actions:
        lines.extend(["## Recent activity", ""])
        for action in actions[:25]:
            lines.append(format_action(action))
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def build_dust_payload(export: dict[str, Any], markdown: str, reference_time: dt.datetime | None = None) -> dict[str, Any]:
    reference_time = reference_time or now_utc()
    board = export["board"]
    return {
        "title": f"Trello Project Brief - {board.get('name', 'Untitled board')}",
        "mime_type": "text/markdown",
        "text": markdown,
        "source_url": board.get("url"),
        "tags": ["trello", "project-management", f"trello-board:{board.get('id', 'unknown')}"],
        "timestamp": int(reference_time.timestamp() * 1000),
        "light_document_output": True,
        "async": False,
    }


def upsert_dust_document(payload: dict[str, Any], document_id: str) -> Any:
    workspace_id = require_env("DUST_WORKSPACE_ID")
    space_id = require_env("DUST_SPACE_ID")
    data_source_id = require_env("DUST_DATA_SOURCE_ID")
    api_key = require_env("DUST_API_KEY")
    encoded_document_id = urllib.parse.quote(document_id, safe="")
    url = (
        f"{DUST_API_BASE}/w/{workspace_id}/spaces/{space_id}"
        f"/data_sources/{data_source_id}/documents/{encoded_document_id}"
    )
    return http_json("POST", url, headers={"Authorization": f"Bearer {api_key}"}, body=payload)


def load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def command_sync(args: argparse.Namespace) -> int:
    load_dotenv(Path(".env"))
    if args.fixture:
        export = load_fixture(Path(args.fixture))
    else:
        client = TrelloClient(require_env("TRELLO_API_KEY"), require_env("TRELLO_API_TOKEN"))
        export = client.export_board(require_env("TRELLO_BOARD_ID"), action_limit=args.action_limit)

    reference_time = now_utc()
    markdown = build_markdown(export, reference_time)
    payload = build_dust_payload(export, markdown, reference_time)

    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")

    if args.dry_run:
        print(markdown)
        return 0

    document_id = os.environ.get("DUST_DOCUMENT_ID", "trello-project-brief")
    result = upsert_dust_document(payload, document_id)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def command_payload(args: argparse.Namespace) -> int:
    export = load_fixture(Path(args.fixture))
    reference_time = parse_iso(args.synced_at) if args.synced_at else now_utc()
    markdown = build_markdown(export, reference_time)
    payload = build_dust_payload(export, markdown, reference_time)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync Trello board data into Dust.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync = subparsers.add_parser("sync", help="Fetch Trello data and upsert it into Dust.")
    sync.add_argument("--dry-run", action="store_true", help="Print Markdown without uploading to Dust.")
    sync.add_argument("--fixture", help="Read Trello data from a local JSON fixture.")
    sync.add_argument("--output", help="Write generated Markdown to a file.")
    sync.add_argument("--action-limit", type=int, default=25, help="Number of recent Trello actions to fetch.")
    sync.set_defaults(func=command_sync)

    payload = subparsers.add_parser("payload", help="Build a Dust payload from a fixture.")
    payload.add_argument("--fixture", required=True)
    payload.add_argument("--synced-at", help="ISO timestamp used for deterministic output.")
    payload.set_defaults(func=command_payload)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
