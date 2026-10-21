"""Local persistence for authorized accounts and server-side sessions."""
import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager, closing
from pathlib import Path

DB_PATH = Path(os.environ.get('AQUALENS_DATABASE', Path(__file__).parent / 'runtime' / 'aqualens.sqlite3'))

@contextmanager
def database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as connection, connection:
        connection.row_factory = sqlite3.Row
        connection.execute('CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_salt TEXT NOT NULL, password_hash TEXT NOT NULL, name TEXT NOT NULL)')
        connection.execute('CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at REAL NOT NULL)')
        yield connection


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def verify_password(password, salt, expected):
    return hmac.compare_digest(password_hash(password, salt), expected)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_user(username, password, name):
    salt = secrets.token_hex(16)
    with database() as connection:
        connection.execute('INSERT INTO users VALUES (?, ?, ?, ?, ?)', (secrets.token_hex(16), username.strip(), salt, password_hash(password, salt), name.strip()))
