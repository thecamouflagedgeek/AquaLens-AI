"""AquaLens API foundation. Monitoring/model services are not implemented yet."""
import os
import secrets
import time
from collections import defaultdict, deque

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from .storage import database, token_hash, verify_password

app = FastAPI(title='AquaLens AI', version='0.1.0')
ORIGINS = [origin.strip() for origin in os.environ.get('AQUALENS_FRONTEND_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',') if origin.strip()]
COOKIE = 'aqualens_session'
SESSION_SECONDS = 8 * 60 * 60
SECURE_COOKIE = os.environ.get('AQUALENS_SECURE_COOKIES', 'false').lower() == 'true'
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_credentials=True, allow_methods=['GET', 'POST', 'PATCH'], allow_headers=['Content-Type'])
login_attempts = defaultdict(deque)


@app.middleware('http')
async def guard_origin(request: Request, call_next):
    # Reject cross-origin writes before they can mutate a cookie-authenticated session.
    origin = request.headers.get('origin')
    if request.method in {'POST', 'PATCH', 'PUT', 'DELETE'} and origin and origin not in ORIGINS:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content={'detail': 'Untrusted request origin.'})
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    return response


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


def current_user(request: Request):
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, 'Authentication required. Sign in with an authorized account.')
    with database() as connection:
        row = connection.execute('SELECT users.id, users.username, users.name FROM sessions JOIN users ON sessions.user_id = users.id WHERE sessions.token_hash = ? AND sessions.expires_at > ?', (token_hash(token), time.time())).fetchone()
    if not row:
        raise HTTPException(401, 'Your session has expired. Please sign in again.')
    return dict(row)


@app.get('/health')
def health():
    return {'status': 'ok', 'monitoring_available': False, 'detail': 'Authentication is available; station ingestion and model services are not connected.'}


@app.post('/auth/login')
def login(credentials: Credentials, request: Request, response: Response):
    now = time.time()
    key = request.client.host if request.client else 'unknown'
    attempts = login_attempts[key]
    while attempts and attempts[0] < now - 300:
        attempts.popleft()
    if len(attempts) >= 10:
        raise HTTPException(429, 'Too many login attempts. Retry in five minutes.')
    attempts.append(now)
    with database() as connection:
        user = connection.execute('SELECT * FROM users WHERE username = ?', (credentials.username.strip(),)).fetchone()
        salt = user['password_salt'] if user else '0' * 32
        expected = user['password_hash'] if user else '0' * 128
        valid = verify_password(credentials.password, salt, expected)
        if not user or not valid:
            raise HTTPException(401, 'Invalid username or password.')
        old_token = request.cookies.get(COOKIE)
        if old_token:
            connection.execute('DELETE FROM sessions WHERE token_hash = ?', (token_hash(old_token),))
        connection.execute('DELETE FROM sessions WHERE expires_at <= ?', (now,))
        token = secrets.token_urlsafe(32)
        connection.execute('INSERT INTO sessions VALUES (?, ?, ?)', (token_hash(token), user['id'], now + SESSION_SECONDS))
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True, secure=SECURE_COOKIE, samesite='lax', path='/')
    return {'authenticated': True}


@app.get('/auth/me')
def me(user=Depends(current_user)):
    return user


@app.post('/auth/logout')
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        with database() as connection:
            connection.execute('DELETE FROM sessions WHERE token_hash = ?', (token_hash(token),))
    response.delete_cookie(COOKIE, path='/', httponly=True, secure=SECURE_COOKIE, samesite='lax')
    return {'authenticated': False}


@app.get('/sources')
@app.get('/stations')
def registered_records(user=Depends(current_user)):
    # Empty until a real monitoring registry is integrated. Never manufacture stations.
    return {'items': []}


@app.get('/stations/{station_id}')
@app.get('/stations/{station_id}/{resource}')
def station_capability(station_id: str, resource: str = '', user=Depends(current_user)):
    raise HTTPException(404, 'Station unavailable: the monitoring registry has not been connected.')


@app.get('/observations/{observation_id}/{resource}')
def observation_capability(observation_id: str, resource: str, user=Depends(current_user)):
    raise HTTPException(503, 'Observation analysis unavailable: model and observation services have not been connected.')
