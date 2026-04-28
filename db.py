from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from config import DB_PATH, ensure_directories


PRODUCT_COLUMNS = (
    "id",
    "article",
    "name",
    "quantity",
    "supplier_site",
    "supplier_article",
    "product_url",
    "image_urls_raw",
    "notes",
    "created_at",
    "updated_at",
)

IMAGE_COLUMNS = (
    "id",
    "product_id",
    "source",
    "source_url",
    "local_path",
    "position",
    "mime_type",
    "file_ext",
    "width_px",
    "height_px",
    "file_size_bytes",
    "status",
    "created_at",
)


def get_connection() -> sqlite3.Connection:
    ensure_directories()
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                quantity INTEGER,
                supplier_site TEXT,
                supplier_article TEXT,
                product_url TEXT,
                image_urls_raw TEXT,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS product_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                source TEXT NOT NULL,
                source_url TEXT NOT NULL,
                local_path TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 1,
                mime_type TEXT,
                file_ext TEXT,
                width_px INTEGER,
                height_px INTEGER,
                file_size_bytes INTEGER,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );
            """
        )


def upsert_product(payload: dict[str, Any]) -> int:
    with get_connection() as connection:
        existing = connection.execute(
            "SELECT id FROM products WHERE article = ?",
            (payload["article"],),
        ).fetchone()
        if existing:
            connection.execute(
                """
                UPDATE products
                SET name = ?,
                    quantity = ?,
                    supplier_site = ?,
                    supplier_article = ?,
                    product_url = ?,
                    image_urls_raw = ?,
                    notes = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    payload["name"],
                    payload.get("quantity"),
                    payload.get("supplier_site"),
                    payload.get("supplier_article"),
                    payload.get("product_url"),
                    payload.get("image_urls_raw"),
                    payload.get("notes"),
                    existing["id"],
                ),
            )
            return int(existing["id"])

        cursor = connection.execute(
            """
            INSERT INTO products (
                article, name, quantity, supplier_site, supplier_article,
                product_url, image_urls_raw, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["article"],
                payload["name"],
                payload.get("quantity"),
                payload.get("supplier_site"),
                payload.get("supplier_article"),
                payload.get("product_url"),
                payload.get("image_urls_raw"),
                payload.get("notes"),
            ),
        )
        return int(cursor.lastrowid)


def delete_product_images(product_id: int) -> None:
    with get_connection() as connection:
        connection.execute("DELETE FROM product_images WHERE product_id = ?", (product_id,))


def add_product_image(payload: dict[str, Any]) -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO product_images (
                product_id, source, source_url, local_path, position,
                mime_type, file_ext, width_px, height_px, file_size_bytes, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["product_id"],
                payload["source"],
                payload["source_url"],
                payload["local_path"],
                payload["position"],
                payload.get("mime_type"),
                payload.get("file_ext"),
                payload.get("width_px"),
                payload.get("height_px"),
                payload.get("file_size_bytes"),
                payload.get("status", "active"),
            ),
        )
        return int(cursor.lastrowid)


def fetch_products() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                p.*,
                COUNT(i.id) AS image_count
            FROM products p
            LEFT JOIN product_images i ON i.product_id = p.id
            GROUP BY p.id
            ORDER BY p.updated_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_product_images(product_id: int) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM product_images
            WHERE product_id = ?
            ORDER BY position ASC, id ASC
            """,
            (product_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_product_by_article(article: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM products WHERE article = ?",
            (article,),
        ).fetchone()
    return dict(row) if row else None


def resolve_media_path(local_path: str) -> Path:
    return Path(local_path)
