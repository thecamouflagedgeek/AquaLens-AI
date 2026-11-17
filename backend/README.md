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

## Field photo validation

With the backend environment activated, download the pinned CLIP checkpoint once before field uploads. The backend automatically loads the checkpoint from backend/models/water-clip. Set AQUALENS_WATER_MODEL_DIR to use a different local copy of the same checkpoint.

```powershell
$env:HF_HOME = Join-Path $PWD 'backend/models/hf-cache'
$env:HF_HUB_DISABLE_XET = '1'
python -c "from huggingface_hub import snapshot_download; from backend.app.water_validation import MODEL, REVISION; snapshot_download(MODEL, revision=REVISION, local_dir='backend/models/water-clip', allow_patterns=['*.json', 'merges.txt', 'pytorch_model.bin'])"
python -c "from backend.app.water_validation import detector; detector(); print('Water detector ready')"
```

The detector runs locally. Version 2 accepts at least 0.67 summed water support, or a clear-container prompt winning by at least 10% over the strongest competing prompt with at least 0.45 summed water support. Both require an exposure factor of at least 0.45. Non-water and uncertain captures have no visibility score. For accepted photos, the central 60% of the frame is scored using normalized percentile contrast (40%), Laplacian detail (35%), and unclipped exposure (25%), moderated by model evidence of muddy or algae-affected water. Thresholds of 0.20, 0.40, 0.60, and 0.80 map the result to grades 1 through 5. The image-based grade is a heuristic and requires field calibration.

When the model is unavailable, uploads are retained for review. In Ground Monitoring → Samples or Findings, select the photo and use **Run water validation** after the model is ready. This also works for older field captures. A held photo stays visible for audit while its classification, stability and baseline eligibility are withheld.

Open http://localhost:5173 and sign in with the account you created. Use `localhost` for both frontend and API (or `127.0.0.1` for both); mixing hostnames prevents the session cookie from working correctly. The frontend defaults to `http://localhost:8000`. To change it, set `VITE_API_BASE_URL` in `frontend/.env` and restart Vite.

The API supports real cookie login, session verification and server-side logout. Stations and sources are empty because no real registry has been integrated. Analysis endpoints explicitly report unavailable. This foundation does not implement model inference, monitoring ingestion, water scores, forecasts or recommendation services.

Default allowed browser origins are http://localhost:5173 and http://127.0.0.1:5173. Set `AQUALENS_FRONTEND_ORIGINS` to a comma-separated list if Vite uses another port. Configure `AQUALENS_SECURE_COOKIES=true` for HTTPS production deployments; this local foundation needs production deployment review, shared rate limiting, operational account management and monitoring data integration before external use.
