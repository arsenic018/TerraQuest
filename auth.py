# auth.py
# Accounts and sessions. Kept in their own tables, off the chain: password hashes
# don't belong in an append-only public ledger.

import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from typing import Optional

PBKDF2_ITERATIONS = 200_000
SESSION_TTL_SECONDS = 30 * 24 * 3600
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,24}$")


class AuthError(ValueError):
    pass


def _hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS).hex()


class UserStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=10)

    def init_db(self) -> None:
        con = self._connect()
        try:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    username      TEXT PRIMARY KEY COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    salt          TEXT NOT NULL,
                    created_at    INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token      TEXT PRIMARY KEY,
                    username   TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                """
            )
            con.commit()
        finally:
            con.close()

    def register(self, username: str, password: str) -> str:
        username = username.strip()
        if not USERNAME_RE.match(username):
            raise AuthError("username must be 3-24 letters, numbers or underscores")
        if len(password) < 8:
            raise AuthError("password must be at least 8 characters")

        salt = secrets.token_bytes(16)
        con = self._connect()
        try:
            con.execute(
                "INSERT INTO users(username, password_hash, salt, created_at) VALUES (?, ?, ?, ?)",
                (username, _hash_password(password, salt), salt.hex(), int(time.time())),
            )
            con.commit()
        except sqlite3.IntegrityError:
            raise AuthError("that username is taken")
        finally:
            con.close()
        return username

    def authenticate(self, username: str, password: str) -> str:
        """Returns the canonical username, or raises AuthError."""
        con = self._connect()
        try:
            row = con.execute(
                "SELECT username, password_hash, salt FROM users WHERE username = ?", (username.strip(),)
            ).fetchone()
        finally:
            con.close()
        if not row or not hmac.compare_digest(_hash_password(password, bytes.fromhex(row[2])), row[1]):
            raise AuthError("invalid username or password")
        return row[0]

    def create_session(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        con = self._connect()
        try:
            con.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
            con.execute(
                "INSERT INTO sessions(token, username, expires_at) VALUES (?, ?, ?)",
                (token, username, now + SESSION_TTL_SECONDS),
            )
            con.commit()
        finally:
            con.close()
        return token

    def user_for_token(self, token: str) -> Optional[str]:
        con = self._connect()
        try:
            row = con.execute(
                "SELECT username FROM sessions WHERE token = ? AND expires_at >= ?", (token, int(time.time()))
            ).fetchone()
        finally:
            con.close()
        return row[0] if row else None

    def delete_session(self, token: str) -> None:
        con = self._connect()
        try:
            con.execute("DELETE FROM sessions WHERE token = ?", (token,))
            con.commit()
        finally:
            con.close()

    def user_exists(self, username: str) -> bool:
        con = self._connect()
        try:
            return con.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone() is not None
        finally:
            con.close()
