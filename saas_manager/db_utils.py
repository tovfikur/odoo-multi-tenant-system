"""
Shared database utility module to consolidate psycopg2 connection patterns.
Provides centralized database connection management with consistent error handling,
connection pooling, and proper resource cleanup.
"""

import os
import psycopg2
import logging
from contextlib import contextmanager
from typing import Dict, Optional, Any, Generator
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

class DatabaseConnectionManager:
    """Centralized database connection manager for PostgreSQL."""
    
    def __init__(
        self,
        pg_host: str = "postgres",
        pg_port: int = 5432,
        pg_user: str = 'odoo_master',
        pg_password: str = None,
        min_conn: int = 1,
        max_conn: int = 10
    ):
        self.pg_host = pg_host
        self.pg_port = pg_port
        self.pg_user = pg_user
        self.pg_password = pg_password or os.getenv('POSTGRES_PASSWORD')
        
        if not self.pg_password:
            raise ValueError("PostgreSQL password must be supplied via pg_password or POSTGRES_PASSWORD env var")
        
        # Connection pools for different databases
        self._pools: Dict[str, ThreadedConnectionPool] = {}
        self.min_conn = min_conn
        self.max_conn = max_conn

    def _get_connection_params(self, dbname: str = 'postgres') -> Dict[str, Any]:
        """Get connection parameters for the specified database."""
        return {
            'dbname': dbname,
            'user': self.pg_user,
            'password': self.pg_password,
            'host': self.pg_host,
            'port': self.pg_port
        }

    def _get_pool(self, dbname: str = 'postgres') -> ThreadedConnectionPool:
        """Get or create connection pool for the specified database."""
        if dbname not in self._pools:
            try:
                self._pools[dbname] = ThreadedConnectionPool(
                    self.min_conn,
                    self.max_conn,
                    **self._get_connection_params(dbname)
                )
                logger.debug(f"Created connection pool for database: {dbname}")
            except Exception as e:
                logger.error(f"Failed to create connection pool for {dbname}: {e}")
                raise
        
        return self._pools[dbname]

    @contextmanager
    def get_connection(
        self, 
        dbname: str = 'postgres', 
        autocommit: bool = False,
        cursor_factory=None
    ) -> Generator[psycopg2.extensions.connection, None, None]:
        """
        Context manager for database connections with automatic cleanup.
        
        Args:
            dbname: Database name to connect to
            autocommit: Whether to enable autocommit
            cursor_factory: Cursor factory to use (e.g., RealDictCursor)
        
        Yields:
            psycopg2 connection object
        """
        pool = self._get_pool(dbname)
        conn = None
        
        try:
            conn = pool.getconn()
            if autocommit:
                conn.autocommit = True
            logger.debug(f"Retrieved connection for database: {dbname}")
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database operation failed for {dbname}: {e}")
            raise
        finally:
            if conn:
                pool.putconn(conn)
                logger.debug(f"Returned connection for database: {dbname}")

    @contextmanager
    def get_cursor(
        self,
        dbname: str = 'postgres',
        autocommit: bool = False,
        cursor_factory=None
    ) -> Generator[psycopg2.extensions.cursor, None, None]:
        """
        Context manager for database cursors with automatic cleanup.
        
        Args:
            dbname: Database name to connect to
            autocommit: Whether to enable autocommit
            cursor_factory: Cursor factory to use (e.g., RealDictCursor)
        
        Yields:
            psycopg2 cursor object
        """
        with self.get_connection(dbname, autocommit) as conn:
            cursor = conn.cursor(cursor_factory=cursor_factory)
            try:
                yield cursor
                if not autocommit:
                    conn.commit()
            except Exception as e:
                if not autocommit:
                    conn.rollback()
                raise
            finally:
                cursor.close()

    def execute_query(
        self,
        query: str,
        params: tuple = None,
        dbname: str = 'postgres',
        autocommit: bool = False,
        fetch_one: bool = False,
        fetch_all: bool = False,
        cursor_factory=None
    ) -> Optional[Any]:
        """
        Execute a query and optionally fetch results.
        
        Args:
            query: SQL query to execute
            params: Query parameters
            dbname: Database name to connect to
            autocommit: Whether to enable autocommit
            fetch_one: Whether to fetch one result
            fetch_all: Whether to fetch all results
            cursor_factory: Cursor factory to use
        
        Returns:
            Query results if fetch_one or fetch_all is True, None otherwise
        """
        with self.get_cursor(dbname, autocommit, cursor_factory) as cursor:
            cursor.execute(query, params)
            
            if fetch_one:
                return cursor.fetchone()
            elif fetch_all:
                return cursor.fetchall()
            return None

    def close_all_pools(self):
        """Close all connection pools."""
        for dbname, pool in self._pools.items():
            try:
                pool.closeall()
                logger.debug(f"Closed connection pool for database: {dbname}")
            except Exception as e:
                logger.error(f"Error closing pool for {dbname}: {e}")
        
        self._pools.clear()

    def __del__(self):
        """Cleanup on destruction."""
        self.close_all_pools()


# Global instance for easy access
_db_manager = None

def get_db_manager(**kwargs) -> DatabaseConnectionManager:
    """Get or create global database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseConnectionManager(**kwargs)
    return _db_manager

def init_db_manager(**kwargs) -> DatabaseConnectionManager:
    """Initialize global database manager with new parameters."""
    global _db_manager
    if _db_manager is not None:
        _db_manager.close_all_pools()
    _db_manager = DatabaseConnectionManager(**kwargs)
    return _db_manager

# Convenience functions for common operations
def execute_postgres_query(query: str, params: tuple = None, **kwargs) -> Optional[Any]:
    """Execute query on postgres database."""
    return get_db_manager().execute_query(query, params, dbname='postgres', **kwargs)

def execute_tenant_query(dbname: str, query: str, params: tuple = None, **kwargs) -> Optional[Any]:
    """Execute query on tenant database."""
    return get_db_manager().execute_query(query, params, dbname=dbname, **kwargs)

@contextmanager
def postgres_connection(**kwargs) -> Generator[psycopg2.extensions.connection, None, None]:
    """Context manager for postgres database connection."""
    with get_db_manager().get_connection('postgres', **kwargs) as conn:
        yield conn

@contextmanager
def tenant_connection(dbname: str, **kwargs) -> Generator[psycopg2.extensions.connection, None, None]:
    """Context manager for tenant database connection."""
    with get_db_manager().get_connection(dbname, **kwargs) as conn:
        yield conn

@contextmanager
def postgres_cursor(**kwargs) -> Generator[psycopg2.extensions.cursor, None, None]:
    """Context manager for postgres database cursor."""
    with get_db_manager().get_cursor('postgres', **kwargs) as cursor:
        yield cursor

@contextmanager
def tenant_cursor(dbname: str, **kwargs) -> Generator[psycopg2.extensions.cursor, None, None]:
    """Context manager for tenant database cursor."""
    with get_db_manager().get_cursor(dbname, **kwargs) as cursor:
        yield cursor
