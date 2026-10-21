# Run the local AquaLens backend

From the repository root (the directory containing `backend` and `frontend`), with your Python virtual environment active:

```powershell
python -m pip install -r backend/requirements.txt
python -m backend.create_user
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

The account command prompts for your own username, display name and password. There are no default credentials. Account passwords are salted and hashed; session tokens are stored hashed in a local SQLite database. Keep this server terminal running.

Open http://localhost:8000/health or http://localhost:8000/docs to verify connectivity. In a second terminal run the frontend:

```powershell
cd frontend
npm run dev
```

Open http://localhost:5173 and sign in with the account you created. Use `localhost` for both frontend and API (or `127.0.0.1` for both); mixing hostnames prevents the session cookie from working correctly. The frontend defaults to `http://localhost:8000`. To change it, set `VITE_API_BASE_URL` in `frontend/.env` and restart Vite.

The API supports real cookie login, session verification and server-side logout. Stations and sources are empty because no real registry has been integrated. Analysis endpoints explicitly report unavailable. This foundation does not implement model inference, monitoring ingestion, water scores, forecasts or recommendation services.

Default allowed browser origins are http://localhost:5173 and http://127.0.0.1:5173. Set `AQUALENS_FRONTEND_ORIGINS` to a comma-separated list if Vite uses another port. Configure `AQUALENS_SECURE_COOKIES=true` for HTTPS production deployments; this local foundation needs production deployment review, shared rate limiting, operational account management and monitoring data integration before external use.
