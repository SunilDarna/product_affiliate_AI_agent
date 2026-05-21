"""
db_tracker.py — Persistent SQLite Database Tracker

Tracks successfully selected products and downloaded YouTube video clips across
multiple pipeline execution cycles to prevent conflicts, duplicate video generation,
and duplicate uploads.
"""
import sqlite3
import os
import urllib.parse
import re
from app.config import WORKSPACE_DIR

DB_PATH = os.path.join(WORKSPACE_DIR, "pipeline.db")


def clean_amazon_url(url: str) -> str:
    """Extracts the ASIN and returns a clean, canonical Amazon URL to prevent duplicate tracking bypass."""
    try:
        decoded_url = urllib.parse.unquote(url)
        asin_match = re.search(r'/(?:dp|gp/product|d)/(B[0-9A-Z]{9}|\d{9}[0-9X])', decoded_url, re.IGNORECASE)
        if asin_match:
            asin = asin_match.group(1)
            return f"https://www.amazon.in/dp/{asin}"
            
        query_params = urllib.parse.parse_qs(urllib.parse.urlparse(decoded_url).query)
        for key, values in query_params.items():
            if key.lower() in ['asin', 'dp']:
                return f"https://www.amazon.in/dp/{values[0]}"
    except Exception as e:
        print(f"DB Tracker: URL cleaning error: {e}")
    return url


def init_db():
    """Initializes the database schema if tables do not exist."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # 1. Products table to avoid duplicate product selections
        cur.execute("""
            CREATE TABLE IF NOT EXISTS Products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                platform TEXT,
                price REAL,
                commission REAL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 2. Clips table to track downloaded YouTube search results
        cur.execute("""
            CREATE TABLE IF NOT EXISTS Clips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                youtube_id TEXT UNIQUE NOT NULL,
                title TEXT,
                duration INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        conn.commit()
        
        # Clean up any existing messy URLs in the database to match the new clean format
        cur.execute("SELECT id, url FROM Products")
        rows = cur.fetchall()
        for row_id, raw_url in rows:
            clean_url = clean_amazon_url(raw_url)
            if clean_url != raw_url:
                try:
                    cur.execute("UPDATE Products SET url = ? WHERE id = ?", (clean_url, row_id))
                except sqlite3.IntegrityError:
                    # If clean_url already exists, delete this duplicate row to keep uniqueness
                    cur.execute("DELETE FROM Products WHERE id = ?", (row_id,))
        
        conn.commit()
        conn.close()
        print(f"DB Tracker: Initialized SQLite database successfully at: {DB_PATH}")
    except Exception as e:
        print(f"DB Tracker Error during initialization: {e}")


def is_product_used(url: str) -> bool:
    """Checks if a product URL has been previously processed."""
    if not os.path.exists(DB_PATH):
        return False
    
    clean_url = clean_amazon_url(url)
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM Products WHERE url = ?", (clean_url,))
        row = cur.fetchone()
        conn.close()
        return row is not None
    except Exception as e:
        print(f"DB Tracker: Error checking product URL: {e}")
        return False


def is_clip_used(youtube_id: str) -> bool:
    """Checks if a YouTube video ID has already been utilized."""
    if not os.path.exists(DB_PATH):
        return False
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM Clips WHERE youtube_id = ?", (youtube_id,))
        row = cur.fetchone()
        conn.close()
        return row is not None
    except Exception as e:
        print(f"DB Tracker: Error checking clip ID: {e}")
        return False


def record_product(title: str, url: str, platform: str, price: float, commission: float):
    """Records a processed product to the Products database."""
    try:
        # Guarantee DB is initialized
        init_db()
        clean_url = clean_amazon_url(url)
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT OR IGNORE INTO Products (title, url, platform, price, commission)
            VALUES (?, ?, ?, ?, ?)
        """, (title, clean_url, platform, price, commission))
        conn.commit()
        conn.close()
        print(f"DB Tracker: Recorded product '{title}' to database (URL: {clean_url}).")
    except Exception as e:
        print(f"DB Tracker: Error recording product: {e}")


def record_clip(youtube_id: str, title: str, duration: int):
    """Records a downloaded YouTube video clip to the Clips database."""
    try:
        # Guarantee DB is initialized
        init_db()
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT OR IGNORE INTO Clips (youtube_id, title, duration)
            VALUES (?, ?, ?)
        """, (youtube_id, title, duration))
        conn.commit()
        conn.close()
        print(f"DB Tracker: Tracked clip ID '{youtube_id}' ('{title}') to database.")
    except Exception as e:
        print(f"DB Tracker: Error recording clip: {e}")


# Auto-initialize and migrate database schema on module load
init_db()


if __name__ == "__main__":
    print("Testing Tracker DB...")
    print("Product used 'http://test':", is_product_used("http://test"))
    record_product("Test Product", "http://test", "Amazon", 199.99, 10.0)
    print("Product used 'http://test' post-save:", is_product_used("http://test"))
