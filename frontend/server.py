from pathlib import Path
import sys

import flet_web.fastapi as flet_fastapi

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from main import main as flet_main  # noqa: E402

app = flet_fastapi.FastAPI(
    title="Habit & Routine Tracker Web",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Return service health status for Cloud Run and container checks."""
    return {"status": "ok"}


app.mount(
    "/",
    flet_fastapi.app(
        flet_main,
        app_name="Habit & Routine Tracker",
        app_short_name="Habit Tracker",
        app_description="Cross-platform Habit & Routine Tracker",
    ),
)
