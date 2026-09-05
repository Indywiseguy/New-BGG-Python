"""
Load BGG collection rows (as produced by export_collection.fetch_collection_rows)
into a table in a self-hosted Postgres database.

Connection is a plain libpq DSN — set POSTGRES_DSN in .env, e.g.:

    POSTGRES_DSN=postgresql://user:password@your-host:5432/your_db

Optionally override the table name with POSTGRES_TABLE (defaults to
"bgg_collection").
"""

import os
from typing import Optional

import psycopg

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
# (column, sql type, python coercion)
_TEXT = "text"
_INT = "integer"
_NUMERIC = "numeric"
_BOOL = "boolean"

COLUMNS: list[tuple[str, str, str]] = [
    # Identity
    ("id", _INT, "int"),
    ("collid", _INT, "int"),
    ("name", _TEXT, "text"),
    ("original_name", _TEXT, "text"),
    ("year_published", _INT, "int"),
    ("image", _TEXT, "text"),
    ("thumbnail", _TEXT, "text"),
    ("image_id", _INT, "int"),
    # Game info
    ("min_players", _INT, "int"),
    ("max_players", _INT, "int"),
    ("min_playtime", _INT, "int"),
    ("max_playtime", _INT, "int"),
    ("playing_time", _INT, "int"),
    ("min_age", _INT, "int"),
    ("avg_weight", _NUMERIC, "float"),
    ("num_owned", _INT, "int"),
    ("bgg_rec_players", _TEXT, "text"),
    ("bgg_best_players", _TEXT, "text"),
    ("bgg_rec_age_range", _TEXT, "text"),
    ("bgg_language_dependence", _TEXT, "text"),
    # Collection status flags
    ("own", _BOOL, "bool"),
    ("preordered", _BOOL, "bool"),
    ("wanttobuy", _BOOL, "bool"),
    ("wishlist", _BOOL, "bool"),
    ("wishlist_priority", _INT, "int"),
    ("wanttoplay", _BOOL, "bool"),
    ("want", _BOOL, "bool"),
    ("fortrade", _BOOL, "bool"),
    ("prevowned", _BOOL, "bool"),
    ("quantity", _INT, "int"),
    ("status_last_modified", _TEXT, "text"),
    # Play tracking
    ("num_plays", _INT, "int"),
    # Ratings
    ("rating", _NUMERIC, "float"),
    ("bgg_rating", _NUMERIC, "float"),
    ("bgg_geek_rating", _NUMERIC, "float"),
    ("num_ratings", _INT, "int"),
    ("rating_stddev", _NUMERIC, "float"),
    # BGG ranks
    ("bgg_rank", _INT, "int"),
    ("family_ranks", _TEXT, "text"),
    # Private ownership / inventory fields
    ("acquiredfrom", _TEXT, "text"),
    ("acquisition_date", _TEXT, "text"),
    ("inv_date", _TEXT, "text"),
    ("price_paid", _NUMERIC, "float"),
    ("price_paid_currency", _TEXT, "text"),
    ("curr_value", _NUMERIC, "float"),
    ("curr_value_currency", _TEXT, "text"),
    ("inv_location", _TEXT, "text"),
    ("condition", _TEXT, "text"),
    ("want_parts_list", _BOOL, "bool"),
    ("has_parts_list", _BOOL, "bool"),
    ("barcode", _TEXT, "text"),
    # Version info
    ("version_publishers", _TEXT, "text"),
    ("version_languages", _TEXT, "text"),
    ("version_year_published", _INT, "int"),
    ("version_nickname", _TEXT, "text"),
    # Comments
    ("wishlist_comment", _TEXT, "text"),
    ("comment", _TEXT, "text"),
    ("private_comment", _TEXT, "text"),
]

DEFAULT_TABLE = "bgg_collection"


# ---------------------------------------------------------------------------
# Coercion
# ---------------------------------------------------------------------------

def _to_int(v) -> Optional[int]:
    s = str(v).strip() if v is not None else ""
    if not s:
        return None
    try:
        return int(float(s))  # tolerate "1.0"-style strings
    except ValueError:
        return None


def _to_float(v) -> Optional[float]:
    s = str(v).strip() if v is not None else ""
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_bool(v) -> Optional[bool]:
    s = str(v).strip() if v is not None else ""
    if not s:
        return None
    return s == "1"


def _to_text(v) -> Optional[str]:
    s = str(v).strip() if v is not None else ""
    return s or None


_COERCE = {"int": _to_int, "float": _to_float, "bool": _to_bool, "text": _to_text}


def _coerce_row(row: dict) -> tuple:
    return tuple(_COERCE[kind](row.get(col, "")) for col, _sql_type, kind in COLUMNS)


# ---------------------------------------------------------------------------
# Postgres
# ---------------------------------------------------------------------------

def _dsn() -> str:
    dsn = os.environ.get("POSTGRES_DSN")
    if not dsn:
        raise RuntimeError(
            "POSTGRES_DSN not set in .env, e.g. "
            "postgresql://user:password@host:5432/dbname"
        )
    return dsn


def table_name() -> str:
    return os.environ.get("POSTGRES_TABLE", DEFAULT_TABLE)


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def ensure_table(conn: "psycopg.Connection", table: str) -> None:
    col_defs = ",\n    ".join(f"{_quote_ident(col)} {sql_type}" for col, sql_type, _ in COLUMNS)
    ddl = f"""
    CREATE TABLE IF NOT EXISTS {_quote_ident(table)} (
        {col_defs},
        synced_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (id)
    )
    """
    with conn.cursor() as cur:
        cur.execute(ddl)


def upsert_rows(conn: "psycopg.Connection", table: str, rows: list[dict]) -> int:
    if not rows:
        return 0

    col_names = [c for c, _, _ in COLUMNS]
    col_list = ", ".join(_quote_ident(c) for c in col_names)
    placeholders = ", ".join(["%s"] * len(col_names))
    update_clause = ", ".join(
        f"{_quote_ident(c)} = EXCLUDED.{_quote_ident(c)}" for c in col_names if c != "id"
    )

    sql = f"""
    INSERT INTO {_quote_ident(table)} ({col_list}, synced_at)
    VALUES ({placeholders}, now())
    ON CONFLICT (id) DO UPDATE SET
        {update_clause},
        synced_at = now()
    """

    values = [_coerce_row(row) for row in rows]
    with conn.cursor() as cur:
        cur.executemany(sql, values)
    return len(values)


def sync_to_postgres(rows: list[dict]) -> int:
    """Ensure the target table exists and upsert *rows* into it. Returns the
    number of rows written."""
    table = table_name()
    with psycopg.connect(_dsn()) as conn:
        ensure_table(conn, table)
        count = upsert_rows(conn, table, rows)
        conn.commit()
    return count
