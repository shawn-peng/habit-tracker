# Habit & Routine Tracker (iPhone, Mac, Android, Web)

A 100% Python full-stack cross-platform **Habit & Routine Tracker** powered by:
- **Backend Server:** Python **FastAPI** + **MongoDB** (`PyMongo AsyncMongoClient`) + **Argon2 / JWT Auth**
- **Cross-Platform Client:** **Flet 1.0+** + async **`httpx`** targeting **iPhone (iOS)**, **Mac (macOS)**, **Android**, and **Web** from a single codebase.

---

## 1. Start the Server (MongoDB + FastAPI)

### Start MongoDB (via Docker)
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

---

## 2. Run the Flet Client Locally (Desktop & Web)

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

## 3. Build for Web, Android, Mac, and iPhone

### Local Builds (from `frontend/`)
- **Web static bundle:** `flet build web`
- **Android `.apk`:** `flet build apk`
- **macOS `.app` (on a Mac):** `flet build macos`
- **iPhone `.ipa` (on a Mac):** `flet build ipa`

### Cloud Builds for Mac & iPhone (from Windows)
Push to `https://github.com/shawn-peng/habit-tracker` and trigger the **Build Cross-Platform Clients & Test Backend** workflow under the GitHub **Actions** tab (`workflow_dispatch`) to compile macOS, iOS, Android, and Web artifacts on GitHub-hosted `macos-latest` and `ubuntu-latest` runners.

When dispatching the workflow manually, choose an `ios_target` option:
- **`ios-simulator`** *(default)* — Builds an unsigned `.app` bundle for the macOS iOS Simulator (no Apple Developer certificates required).
- **`ipa-unsigned`** — Compiles an unsigned iOS `.xcarchive` (`--flutter-build-args=--no-codesign`) for manual/external signing.
- **`ipa-signed`** — Builds a signed `.ipa` using your `IOS_TEAM_ID` GitHub repository secret (and configured signing credentials).
