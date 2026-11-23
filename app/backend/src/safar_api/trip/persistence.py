import logging
import threading
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import Connection
from psycopg.rows import dict_row

from safar_api.config import settings

logger = logging.getLogger(__name__)

_checkpointer = None
_conn = None
_db_lock = threading.RLock()


class AsyncReadyPostgresSaver(PostgresSaver):
    """PostgresSaver with the async methods graph.astream() calls.

    The stock sync saver raises NotImplementedError from aget_tuple. These
    methods run the sync queries on the same connection. The lock keeps that
    connection on one caller at a time.
    """

    def _run(self, method, *args, **kwargs):
        with _db_lock:
            _ensure_connection_locked()
            try:
                return method(*args, **kwargs)
            except Exception as exc:
                if not _connection_closed(exc):
                    raise
                _reconnect_locked()
                return method(*args, **kwargs)

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return self._run(super().get_tuple, config)

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return self._run(super().put, config, checkpoint, metadata, new_versions)

    def put_writes(
        self,
        config: RunnableConfig,
        writes: list[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        return self._run(super().put_writes, config, writes, task_id, task_path)

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return self.get_tuple(config)

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return self.put(config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: list[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        return self.put_writes(config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        with _db_lock:
            self.delete_thread(thread_id)


def get_postgres_connection_string() -> str | None:
    """Return the configured connection string for Postgres."""
    url = (settings.checkpoint_postgres_url or settings.database_url or "").strip()
    return url if url else None


def _connection_closed(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "connection is closed" in text or "terminating connection" in text or "connection refused" in text


def _open_connection() -> Connection:
    url = get_postgres_connection_string()
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return Connection.connect(
        url,
        autocommit=True,
        prepare_threshold=0,
        row_factory=dict_row,
    )


def _reconnect_locked() -> Connection:
    """Replace a dropped Neon connection. Caller must hold _db_lock."""
    global _conn
    if _conn is not None:
        try:
            _conn.close()
        except Exception:
            pass
    logger.warning("Postgres connection dropped. Reconnecting.")
    _conn = _open_connection()
    if isinstance(_checkpointer, PostgresSaver):
        _checkpointer.conn = _conn
    return _conn


def _ensure_connection_locked() -> Connection | None:
    """Return a live connection. Caller must hold _db_lock."""
    if not get_postgres_connection_string():
        return None
    if _conn is not None and not _conn.closed:
        return _conn
    if _checkpointer is None:
        return None
    return _reconnect_locked()


def init_db(conn: Connection) -> None:
    """Create the lightweight metadata index table for saved trips."""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trips (
                    thread_id VARCHAR(255) PRIMARY KEY,
                    destination VARCHAR(255),
                    origin VARCHAR(255),
                    start_date VARCHAR(20),
                    end_date VARCHAR(20),
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
        logger.info("Initialized 'trips' index table in Postgres database")
    except Exception as e:
        logger.error("Failed to initialize database tables: %s", e)


def get_checkpointer() -> Any:
    """Get the active checkpointer (PostgresSaver if configured, else InMemorySaver)."""
    global _checkpointer, _conn
    if _checkpointer is not None:
        return _checkpointer

    conn_string = get_postgres_connection_string()
    if conn_string:
        try:
            logger.info("Connecting to Postgres checkpointer...")
            # Establish standard connection with autocommit=True for LangGraph
            _conn = _open_connection()
            # Initialize checkpointer
            saver = AsyncReadyPostgresSaver(_conn)
            saver.setup()
            _checkpointer = saver
            
            # Initialize our custom lightweight metadata tables
            init_db(_conn)
            
            logger.info("Postgres checkpointer successfully initialized and setup")
            return _checkpointer
        except Exception as e:
            logger.error("Failed to connect to Postgres database, falling back to InMemorySaver: %s", e)

    logger.warning("No Postgres connection found or connection failed. Using InMemorySaver.")
    _checkpointer = InMemorySaver()
    return _checkpointer


def _run_sql(query: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Run one statement, reconnecting once if Neon has dropped the connection."""
    with _db_lock:
        conn = _ensure_connection_locked()
        if conn is None:
            return []

        def _execute(active: Connection) -> list[dict[str, Any]]:
            with active.cursor() as cur:
                cur.execute(query, params)
                if cur.description is None:
                    return []
                return [dict(row) for row in cur.fetchall()]

        try:
            return _execute(conn)
        except Exception as exc:
            if not _connection_closed(exc):
                raise
            return _execute(_reconnect_locked())


def upsert_trip_metadata(thread_id: str, brief_dict: dict[str, Any]) -> None:
    """Sync a trip's brief properties to the persistent trips table."""
    if not get_postgres_connection_string():
        return
    destination = brief_dict.get("destination", "") or ""
    origin = brief_dict.get("origin", "") or ""
    start_date = brief_dict.get("start_date", "") or ""
    end_date = brief_dict.get("end_date", "") or ""
    _run_sql(
        """
        INSERT INTO trips (thread_id, destination, origin, start_date, end_date, updated_at)
        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (thread_id) DO UPDATE SET
            destination = EXCLUDED.destination,
            origin = EXCLUDED.origin,
            start_date = EXCLUDED.start_date,
            end_date = EXCLUDED.end_date,
            updated_at = CURRENT_TIMESTAMP;
        """,
        (thread_id, destination, origin, start_date, end_date),
    )
    logger.info("Synced trip metadata to database for thread %s", thread_id)


def list_saved_trips() -> list[dict[str, Any]]:
    """List all persisted trips from the index table, ordered by last updated."""
    if not get_postgres_connection_string():
        return []
    return _run_sql(
        """
        SELECT thread_id, destination, origin, start_date, end_date, updated_at
        FROM trips
        ORDER BY updated_at DESC;
        """
    )


def delete_saved_trip(thread_id: str) -> bool:
    """Delete a trip from the metadata index."""
    if not get_postgres_connection_string():
        return False
    with _db_lock:
        conn = _ensure_connection_locked()
        if conn is None:
            return False

        def _delete(active: Connection) -> int:
            with active.cursor() as cur:
                cur.execute("DELETE FROM trips WHERE thread_id = %s;", (thread_id,))
                return cur.rowcount

        try:
            removed = _delete(conn)
        except Exception as exc:
            if not _connection_closed(exc):
                raise
            removed = _delete(_reconnect_locked())
    if removed:
        logger.info("Deleted trip %s from index", thread_id)
    return removed > 0
