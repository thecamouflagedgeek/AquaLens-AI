# AquaLens Field · Android

Run the existing FastAPI backend from the repository root:

```powershell
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Provision an active account with role `officer` through the authenticated admin registration endpoint. Register at least one station in AquaLens India before collecting samples. The station list currently contains all registered India stations; per-officer assignments are not configured.

```powershell
cd mobile
flutter pub get
flutter run --dart-define=AQUALENS_API_URL=http://10.0.2.2:8000
```

The URL above is for the Android emulator. On a physical device use a reachable backend URL. Release builds require HTTPS; cleartext is enabled only for Android debug builds.

Sign in and sync the station list once before going offline. Capture a photo with a current GPS fix, confirm the suggested station, and save it. The queue retains the file and capture metadata across restarts. Sync runs every 15 seconds while the app is open and can be triggered from the toolbar. Each upload currently contains one image. Server history reads the same database records as India Admin → Ground. An admin must review the station match before fingerprint comparison is exposed.

To verify: make a capture with internet disconnected (leave device location on); restart the app and check Pending; reconnect and sync; inspect the original image and extracted features in both History and the Admin Ground feed. Retry the same capture ID and verify the server returns the existing observation. Try a second officer account and verify it cannot read the first officer’s observation or image.
