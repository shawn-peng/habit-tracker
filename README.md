# Habit & Routine Tracker (Native Android, iPhone, Mac, Web)

A full-stack cross-platform **Habit & Routine Tracker** powered by:
- **Backend Server:** Python **FastAPI** + **MongoDB** (`PyMongo AsyncMongoClient`) + **Argon2 / JWT Auth** (`backend/`)
- **Native Android App:** **Kotlin + Jetpack Compose + Material 3** (`android/`) connecting directly to the FastAPI backend
- **Cross-Platform Client:** **Flet 1.0+** + async **`httpx`** targeting **iPhone (iOS)**, **Mac (macOS)**, **Android**, and **Web** (`frontend/`).
- **Habit Modes, Reminders & Alarms:** Unified per-habit modes (`free`, `strict` Mode 1: remind → mandatory start → force complete with pre-start guard & violation detection, `window` Mode 2: remind → force end, `reminder` Mode 3: multi-time alerts & ringing alarms) with **12-hour AM/PM** pickers, Notification vs. Ringing Alarm delivery, snooze intervals, custom messages, `GET /api/habits/reminders` center, Flet live due-reminder dialogs, native Android `AlarmManager` + System Clock handoff, and separate late-makeup accounting across stats, streaks, and SLI.
- **Personal SLI & Error Budget Dashboard (`SLI`):** SRE-style reliability analytics (`GET /api/stats/sli`) with configurable per-habit `target_slo`, rolling `7d/30d/90d` SLIs, error budget remaining & multi-window burn rates, rolling SLI trend chart, and weekday reliability diagnostics across both clients.

---

### Quick Restart Script (Windows PowerShell)

From the repository root, run `restart-app.ps1` to stop any running Habit Tracker processes, ensure MongoDB is up, start the FastAPI backend (`:8000`) and Flet client (`http://127.0.0.1:52131`), and verify readiness:

```powershell
# Restart MongoDB (if local), FastAPI (:8000), and Flet Web UI (http://127.0.0.1:52131)
.\restart-app.ps1

# Restart Web UI without auto-opening a browser tab
.\restart-app.ps1 -NoBrowser

# Restart with the native Flet Desktop window instead of Web
.\restart-app.ps1 -Mode desktop

# Stop all running Habit Tracker backend/frontend processes
.\restart-app.ps1 -StopOnly
```

---

## 1. Start the Server (MongoDB + FastAPI)

### Option A: MongoDB Atlas (M0 Free on Google Cloud)
1. Create an **M0 (Free)** cluster hosted on **Google Cloud** in MongoDB Atlas (e.g., `us-central1` Iowa or `us-east1` South Carolina) with a database user (`readWrite` on `habit_tracker`) and IP access rule.
2. Copy `backend/.env.example` to `backend/.env` and set `MONGODB_URI` to your Atlas `mongodb+srv://...` connection string (plus a strong random `JWT_SECRET`).

### Option B: Local MongoDB (via Docker)
```powershell
docker compose up -d mongodb
```
*(Or run both MongoDB and the FastAPI server inside Docker on your server with `docker compose --profile full up -d --build`.)*

### Run FastAPI Locally (Python 3.14)
```powershell
cd backend
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- Interactive API docs: `http://localhost:8000/docs`
- Run backend unit tests: `pytest -v`

### Deploy Backend to Google Cloud Run + MongoDB Atlas
- `backend/Dockerfile` listens on Cloud Run's injected `$PORT` (`8080` on Cloud Run, defaulting to `8000` locally).
- Configure runtime environment variables (or Secret Manager secrets) on the Cloud Run service:
  - `MONGODB_URI` (`mongodb+srv://...`, keeping `maxPoolSize=20&maxIdleTimeMS=60000` for serverless scaling within Atlas M0's 500-connection limit)
  - `MONGODB_DB_NAME=habit_tracker`
  - `JWT_SECRET` (a secure random secret, distinct from local dev)
  - `CORS_ORIGINS` (your deployed web origin or `*` for native/web token-based clients)
  - Optional SMTP email verification & password-reset variables: `SMTP_HOST`, `SMTP_PORT=587`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_USE_TLS=true`, `SMTP_USE_SSL=false`, `RESET_CODE_EXPIRE_MINUTES=15`, `AUTH_DEV_RETURN_RESET_CODE=false` (when `SMTP_HOST` is omitted locally, 6-digit registration verification and password-reset codes are logged to the FastAPI server console)
- Co-locate your Cloud Run service and Atlas M0 cluster in the **same GCP region** (e.g., `us-central1` / `CENTRAL_US` or `us-east1` / `EASTERN_US`) for single-digit ms database latency.
- **Atlas M0 Network Access with Cloud Run:** VPC Peering and Private Service Connect require Atlas Dedicated `M10+`. For `M0`, either route Cloud Run egress through Cloud NAT with a static IP allowlisted in Atlas, or allow `0.0.0.0/0` in Atlas Network Access combined with strong SCRAM credentials and TLS (enforced automatically by `mongodb+srv://`).

### Deploy Frontend Server to Google Cloud Run (Continuous Deployment)
- **Live Service (`habit-tracker-web`, `us-central1`):** `https://habit-tracker-web-142205380680.us-central1.run.app` (alias: `https://habit-tracker-web-mcj2rjpeiq-uc.a.run.app`), served by `frontend/server.py` + `frontend/Dockerfile` (`uvicorn` + `flet_web` ASGI on `0.0.0.0:${PORT:-8080}` with `GET /health` health checks, `--max-instances=1`, `--session-affinity`, and `--timeout=3600` for Flet WebSockets).
- **Automated CD Pipeline (`.github/workflows/deploy-frontend.yml`):** Every push to `main` touching `frontend/**` or `.github/workflows/deploy-frontend.yml` runs ASGI smoke tests (`verify-frontend`), authenticates via **keyless Google Cloud Workload Identity Federation (OIDC)** (no static service-account JSON keys stored in GitHub), pushes the container image to Artifact Registry (`us-central1-docker.pkg.dev/shawn-habit-tracker-2026/cloud-run-source-deploy/habit-tracker-web`), deploys to Cloud Run, and verifies `GET /health` and `GET /`.
- **Manual Dispatch:** Under GitHub **Actions → Deploy Frontend Server to Cloud Run**, click **Run workflow** (optionally passing `habit_api_url` to override the backend API endpoint).
- **Local Container Stack (MongoDB + Backend + Frontend Web):** Run `docker compose --profile full up -d --build` to serve the containerized frontend at `http://localhost:8080` pointing to `http://backend:8000`.

---

## 2. Native Android App (`android/`, Kotlin + Jetpack Compose)

See [`android/README.md`](android/README.md) for full details.

- **Cloud APK Build (No local Android SDK needed):** Every push or pull request on `main` (as well as `workflow_dispatch`) triggers the **`build-android-native`** job in GitHub Actions to run `./gradlew testDebugUnitTest assembleDebug` and upload **`android-native-apk`** (`HabitTracker-Android-debug.apk`).
- **Local Development:** Open `android/` directly in **Android Studio** (JDK 17+). When running the backend on your PC (`uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`), use `http://10.0.2.2:8000` in the Android Emulator or your PC's LAN IP (e.g., `http://192.168.1.50:8000`) on a physical phone.

---

## 3. Run the Flet Client Locally (Desktop & Web)

```powershell
cd frontend
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Launch Desktop window preview
flet run src/main.py

# Or launch in your Web Browser
flet run --web src/main.py
```

When signing in from an iPhone or Android device on the same Wi-Fi network, set **Server API URL** on the login screen to your server's LAN IP or HTTPS domain (e.g., `http://192.168.1.50:8000` or `https://habits.yourdomain.com`).

---

## 4. Build Flet Clients for Web, Android, Mac, and iPhone

### Local Builds (from `frontend/`)
- **Web static bundle:** `flet build web`
- **Android `.apk`:** `flet build apk`
- **macOS `.app` (on a Mac):** `flet build macos`
- **iPhone `.ipa` (on a Mac):** `flet build ipa`

### Cloud Builds for iPhone & Mac (from Windows)
Every `push` or `pull_request` on `main` (as well as manual `workflow_dispatch` runs under the GitHub **Actions** tab) automatically runs **`build-macos-and-ios`** with **`ipa-unsigned`** as the default target to compile `HabitTracker-iOS-Unsigned.ipa` and upload the **`ios-ipa`** artifact.

When dispatching the **Build Cross-Platform Clients & Test Backend** workflow manually (`workflow_dispatch`):
- **`ios_target`:**
  - **`ipa-unsigned`** *(default)* — Compiles an unsigned iOS archive and packages `Payload/<App>.app` into a sideload-ready `HabitTracker-iOS-Unsigned.ipa`, uploaded as **`ios-ipa`** (no paid Apple Developer account or certificates required).
  - **`ios-simulator`** — Builds an unsigned `.app` bundle for the macOS iOS Simulator.
  - **`ipa-signed`** — Builds a signed `.ipa` using your `IOS_TEAM_ID` GitHub repository secret (and configured signing credentials).
- **Optional extra targets** (unchecked by default for fast iOS IPA builds): **`include_macos`**, **`include_web_and_flet_apk`**, and **`include_native_android`**.

#### Personal iPhone Sideloading from Windows (Free Apple ID)
To install `HabitTracker-iOS-Unsigned.ipa` onto your own iPhone without publishing to the App Store (free Apple ID certificates remain valid for **7 days** and allow up to **3** sideloaded apps per device):
1. Download the **`ios-ipa`** artifact from the completed GitHub Actions run and unzip it to obtain `HabitTracker-iOS-Unsigned.ipa`.
2. Install using any personal sideloading tool with your Apple ID:
   - **SideStore (recommended):** Complete the one-time setup from Windows (install SideStore + pair with your PC), then import `HabitTracker-iOS-Unsigned.ipa` on your iPhone. With SideStore's local VPN (`LocalDevVPN` / WireGuard) enabled, SideStore refreshes the 7-day signature directly on your iPhone without needing your PC.
   - **AltStore:** Run **AltServer** on Windows, install AltStore on your iPhone, and open `HabitTracker-iOS-Unsigned.ipa` in AltStore (AltServer refreshes it over USB or same-network Wi-Fi sync).
   - **Sideloadly:** Connect your iPhone to Windows via USB, drag `HabitTracker-iOS-Unsigned.ipa` into Sideloadly, sign in with your Apple ID, and click **Start**.
3. On your iPhone before launching the app for the first time:
   - Enable **Developer Mode** under **Settings → Privacy & Security → Developer Mode** (requires a reboot).
   - Trust your Apple ID developer certificate under **Settings → General → VPN & Device Management**.
