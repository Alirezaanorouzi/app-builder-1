from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_REPO_ROOT / ".env")
load_dotenv()


def _repo_abs(path_str: str) -> str:
    p = Path(path_str)
    if not p.is_absolute():
        p = (_REPO_ROOT / p).resolve()
    return str(p)


@dataclass(frozen=True)
class Settings:
    database_url: str
    conversation_dir: str
    workspace_staging_dir: str
    archive_local_dir: str
    worker_concurrency: int
    poll_seconds: float
    deploy_env: str
    sandbox_provider: str
    sandbox_idle_seconds: int
    run_event_max_bytes: int
    openhands_sdk_version: str
    liara_api_key: str
    liara_base_url: str
    liara_default_model: str
    vercel_token: str | None
    vercel_team_id: str | None
    vercel_project_id: str | None
    max_iterations: int
    templates_dir: str

    @classmethod
    def load(cls) -> "Settings":
        models = os.environ.get(
            "LIARA_MODELS",
            "deepseek/deepseek-v4.1-flash",
        ).split(",")
        conversation_dir = _repo_abs(
            os.environ.get("CONVERSATION_DIR", "./data/conversations")
        )
        archive_local_dir = _repo_abs(
            os.environ.get("ARCHIVE_LOCAL_DIR", "./data/archives")
        )
        workspace_staging_dir = _repo_abs(
            os.environ.get(
                "WORKSPACE_STAGING_DIR",
                str(Path(conversation_dir).parent / "workspace-staging"),
            )
        )
        return cls(
            database_url=os.environ["DATABASE_URL"],
            conversation_dir=conversation_dir,
            workspace_staging_dir=workspace_staging_dir,
            archive_local_dir=archive_local_dir,
            worker_concurrency=int(os.environ.get("WORKER_CONCURRENCY", "2")),
            poll_seconds=float(os.environ.get("WORKER_POLL_SECONDS", "3")),
            deploy_env=os.environ.get("DEPLOY_ENV", "dev"),
            sandbox_provider=os.environ.get("SANDBOX_PROVIDER", "local").lower(),
            sandbox_idle_seconds=int(os.environ.get("SANDBOX_IDLE_SECONDS", "300")),
            run_event_max_bytes=int(os.environ.get("RUN_EVENT_MAX_BYTES", "65536")),
            openhands_sdk_version=os.environ.get("OPENHANDS_SDK_VERSION", "1.63.1"),
            liara_api_key=os.environ.get("LIARA_API_KEY", ""),
            liara_base_url=os.environ.get("LIARA_BASE_URL", ""),
            liara_default_model=models[0].strip() or "deepseek/deepseek-v4.1-flash",
            vercel_token=os.environ.get("VERCEL_TOKEN"),
            vercel_team_id=os.environ.get("VERCEL_TEAM_ID"),
            vercel_project_id=os.environ.get("VERCEL_PROJECT_ID"),
            max_iterations=int(os.environ.get("MAX_ITERATIONS", "80")),
            templates_dir=os.environ.get(
                "TEMPLATES_DIR",
                os.path.join(os.path.dirname(__file__), "..", "..", "..", "templates"),
            ),
        )