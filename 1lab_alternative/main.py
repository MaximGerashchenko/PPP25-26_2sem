import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Dict, Iterable, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw_data"
DB_PATH = BASE_DIR / "etl_data.db"

USER_AGENT = "ETLStudyProject/1.0"

SOURCES = [
    {
        "name": "hacker_news",
        "type": "json",
        "url": "https://hn.algolia.com/api/v1/search_by_date?tags=story&hitsPerPage=30",
    },
    {
        "name": "habr",
        "type": "rss",
        "url": "https://habr.com/ru/rss/articles/",
    },
]


def ensure_directories() -> None:
    RAW_DIR.mkdir(exist_ok=True)


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unique_key TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                author TEXT,
                published_at TEXT,
                source TEXT NOT NULL,
                category TEXT,
                url TEXT,
                loaded_at TEXT NOT NULL
            )
            """
        )
        connection.commit()


def fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def save_raw(source_name: str, extension: str, content: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    file_path = RAW_DIR / f"{source_name}_{timestamp}.{extension}"
    file_path.write_text(content, encoding="utf-8")
    return file_path


def normalize_text(value: str) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def normalize_datetime(value: str) -> str:
    if not value:
        return ""

    try:
        if value.endswith("Z"):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        pass

    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return ""


def build_unique_key(item: Dict[str, str]) -> str:
    url = normalize_text(item.get("url", "")).lower()
    if url:
        return url

    title = normalize_text(item.get("title", "")).lower()
    published_at = normalize_text(item.get("published_at", ""))
    source = normalize_text(item.get("source", "")).lower()
    return f"{source}|{title}|{published_at}"


def transform_hacker_news(payload: Dict) -> List[Dict[str, str]]:
    items = []
    for hit in payload.get("hits", []):
        title = normalize_text(hit.get("title") or hit.get("story_title"))
        if not title:
            continue

        item = {
            "title": title,
            "author": normalize_text(hit.get("author")),
            "published_at": normalize_datetime(hit.get("created_at", "")),
            "source": "hacker_news",
            "category": normalize_text(", ".join(hit.get("_tags", []))),
            "url": normalize_text(hit.get("url") or hit.get("story_url")),
        }
        item["unique_key"] = build_unique_key(item)
        items.append(item)
    return items


def transform_habr(rss_text: str) -> List[Dict[str, str]]:
    root = ET.fromstring(rss_text)
    items = []

    for entry in root.findall("./channel/item"):
        categories = [normalize_text(category.text) for category in entry.findall("category") if category.text]
        item = {
            "title": normalize_text(entry.findtext("title")),
            "author": normalize_text(entry.findtext("author")),
            "published_at": normalize_datetime(entry.findtext("pubDate", "")),
            "source": "habr",
            "category": normalize_text(", ".join(categories)),
            "url": normalize_text(entry.findtext("link")),
        }
        if not item["title"]:
            continue
        item["unique_key"] = build_unique_key(item)
        items.append(item)

    return items


def deduplicate(items: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    unique_items = []

    for item in items:
        unique_key = item["unique_key"]
        if unique_key in seen:
            continue
        seen.add(unique_key)
        unique_items.append(item)

    return unique_items


def load_items(items: Iterable[Dict[str, str]]) -> int:
    loaded_at = datetime.now(timezone.utc).isoformat()
    inserted = 0

    with sqlite3.connect(DB_PATH) as connection:
        for item in items:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO items (
                    unique_key,
                    title,
                    author,
                    published_at,
                    source,
                    category,
                    url,
                    loaded_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["unique_key"],
                    item["title"],
                    item["author"],
                    item["published_at"],
                    item["source"],
                    item["category"],
                    item["url"],
                    loaded_at,
                ),
            )
            inserted += cursor.rowcount
        connection.commit()

    return inserted


def run_etl() -> None:
    ensure_directories()
    init_db()

    all_items: List[Dict[str, str]] = []

    for source in SOURCES:
        print(f"[EXTRACT] Loading data from {source['name']}...")
        try:
            raw_content = fetch_text(source["url"])
        except (HTTPError, URLError, TimeoutError) as error:
            print(f"[ERROR] Failed to load {source['name']}: {error}")
            continue

        extension = "json" if source["type"] == "json" else "xml"
        raw_path = save_raw(source["name"], extension, raw_content)
        print(f"[EXTRACT] Raw data saved to: {raw_path.name}")

        try:
            if source["type"] == "json":
                transformed = transform_hacker_news(json.loads(raw_content))
            else:
                transformed = transform_habr(raw_content)
        except (json.JSONDecodeError, ET.ParseError) as error:
            print(f"[ERROR] Failed to transform {source['name']}: {error}")
            continue

        print(f"[TRANSFORM] {source['name']}: {len(transformed)} records normalized")
        all_items.extend(transformed)

    unique_items = deduplicate(all_items)
    inserted = load_items(unique_items)

    print(f"[TRANSFORM] Total records after deduplication: {len(unique_items)}")
    print(f"[LOAD] Inserted into SQLite: {inserted}")
    print(f"[LOAD] Database file: {DB_PATH}")


def show_items(limit: int) -> None:
    init_db()
    with sqlite3.connect(DB_PATH) as connection:
        rows = connection.execute(
            """
            SELECT title, source, published_at, url
            FROM items
            ORDER BY published_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    if not rows:
        print("Database is empty. Run: python main.py run")
        return

    for index, row in enumerate(rows, start=1):
        title, source, published_at, url = row
        print(f"{index}. [{source}] {title}")
        print(f"   date: {published_at or 'unknown'}")
        print(f"   url:  {url or 'missing'}")


def reset_database() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    print("Database removed. It will be recreated on the next run.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ETL process: extract data from websites, transform it and load into SQLite."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("run", help="Run full ETL cycle")
    subparsers.add_parser("init", help="Create SQLite database")
    subparsers.add_parser("reset", help="Delete SQLite database")

    show_parser = subparsers.add_parser("show", help="Show records from database")
    show_parser.add_argument("--limit", type=int, default=10, help="Number of rows to display")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.command == "init":
        ensure_directories()
        init_db()
        print(f"Database created: {DB_PATH}")
        return 0

    if args.command == "run":
        run_etl()
        return 0

    if args.command == "show":
        show_items(args.limit)
        return 0

    if args.command == "reset":
        reset_database()
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
