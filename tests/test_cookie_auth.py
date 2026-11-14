"""Regression tests for the frontend's cookie-based authentication contract."""
import unittest
from http.cookies import SimpleCookie

from fastapi import HTTPException, Request, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.api.auth import login, logout
from backend.app.api.deps import get_current_user
from backend.app.core.config import settings
from backend.app.core.security import hash_password
from backend.app.core.workspaces import ensure_india_account
from backend.app.schemas.schemas import UserOut
from backend.app.db.models import User
from backend.app.db.session import Base
from backend.app.schemas.schemas import UserLogin


def request_with_cookie(token=None):
    headers = [(b'cookie', f'{settings.SESSION_COOKIE}={token}'.encode())] if token else []
    return Request({'type': 'http', 'headers': headers})


class CookieAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add(User(username='researcher', email='researcher@example.test', hashed_password=hash_password('test-password'), role='viewer', is_active=True))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def sign_in(self):
        response = Response()
        data = login(UserLogin(username='researcher', password='test-password'), response, self.db)
        cookie = SimpleCookie()
        cookie.load(response.headers['set-cookie'])
        self.assertTrue(cookie[settings.SESSION_COOKIE]['httponly'])
        self.assertEqual(cookie[settings.SESSION_COOKIE]['samesite'], 'lax')
        self.assertEqual(cookie[settings.SESSION_COOKIE].value, data['access_token'])
        return data['access_token']

    def test_cookie_authenticates_profile_and_survives_new_request(self):
        token = self.sign_in()
        for _ in range(2):
            self.assertEqual(get_current_user(request_with_cookie(token), None, self.db).username, 'researcher')

    def test_missing_cookie_and_wrong_password_are_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            get_current_user(request_with_cookie(), None, self.db)
        self.assertEqual(caught.exception.status_code, 401)
        with self.assertRaises(HTTPException):
            login(UserLogin(username='researcher', password='wrong'), Response(), self.db)

    def test_india_account_login_and_existing_account_are_separate(self):
        before = self.db.query(User).filter_by(username='researcher').one().hashed_password
        india = ensure_india_account(self.db)
        original_hash = india.hashed_password
        ensure_india_account(self.db)
        self.assertEqual(self.db.query(User).filter_by(username='admin_1').count(), 1)
        self.assertEqual(india.hashed_password, original_hash)
        self.assertEqual(self.db.query(User).filter_by(username='researcher').one().hashed_password, before)
        response = Response()
        data = login(UserLogin(username='admin_1', password='India123'), response, self.db)
        authenticated = get_current_user(request_with_cookie(data['access_token']), None, self.db)
        self.assertEqual(UserOut.model_validate(authenticated).workspace, 'india')
        self.assertEqual(UserOut.model_validate(self.db.query(User).filter_by(username='researcher').one()).workspace, 'existing')
        with self.assertRaises(HTTPException):
            login(UserLogin(username='admin_1', password='AquaLens2026!'), Response(), self.db)

    def test_logout_invalidates_cookie_and_bearer_replay(self):
        token = self.sign_in()
        response = Response()
        logout(request_with_cookie(token), response, None, self.db)
        self.assertIn('Max-Age=0', response.headers['set-cookie'])
        with self.assertRaises(HTTPException):
            get_current_user(request_with_cookie(token), None, self.db)
        with self.assertRaises(HTTPException):
            get_current_user(request_with_cookie(), token, self.db)
        fresh = self.sign_in()
        self.assertNotEqual(token, fresh)
        self.assertEqual(get_current_user(request_with_cookie(fresh), None, self.db).username, 'researcher')


if __name__ == '__main__':
    unittest.main()
