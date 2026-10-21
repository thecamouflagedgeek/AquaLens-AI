"""Provision a real local account: python -m backend.create_user"""
import getpass
import sqlite3
from .storage import create_user


def main():
    username = input('Email / username: ').strip()
    name = input('Display name: ').strip()
    password = getpass.getpass('Password (at least 12 characters): ')
    confirmation = getpass.getpass('Confirm password: ')
    if not username or not name or len(password) < 12 or password != confirmation:
        raise SystemExit('Account not created: provide a username, name and matching passwords of at least 12 characters.')
    try:
        create_user(username, password, name)
    except sqlite3.IntegrityError:
        raise SystemExit('That username already exists.')
    print('Account created. Sign in using this username and password.')


if __name__ == '__main__':
    main()
