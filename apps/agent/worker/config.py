from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from worker.liara_env import apply_liara_worker_env

_REPO_ROOT = Path(__file__).resolve().parents[3]
apply_liara_worker_env()
load_dotenv(_REPO_ROOT / ".env")
load_dotenv()
apply_liara_worker_env()


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
    sandbox_extend_when_remaining_seconds: int
    vercel_sandbox_max_session_seconds: int
    vercel_snapshot_retention_count: int
    vercel_snapshot_delete_evicted: bool
    run_event_max_bytes: int
    openhands_sdk_version: str
    liara_api_key: str
    liara_base_url: str
    liara_default_model: str
    liara_models: tuple[str, ...]
    vercel_token: str | None
    vercel_team_id: str | None
    vercel_project_id: str | None
    vercel_base_snapshot_id: str | None
    vercel_preview_wait_seconds: int
    max_iterations: int
    templates_dir: str
    agent_runtime: str
    agent_server_port: int
    oh_secret_key: str | None
    oh_session_api_key: str | None
    llm_proxy_public_url: str | None
    llm_proxy_admin_url: str | None
    llm_proxy_admin_key: str | None
    run_orphan_policy: str
    llm_remote_direct_liara: bool

    def uses_remote_agent(self) -> bool:
        if self.sandbox_provider != "vercel":
            return False
        mode = self.agent_runtime.lower()
        if mode == "embedded":
            return False
        if mode == "remote":
            return True
        return mode in ("auto", "default", "")

    @classmethod
    def load(cls) -> "Settings":
        models_raw = os.environ.get(
            "LIARA_MODELS",
            "deepseek/deepseek-v4.1-flash-1017",
        )
        liara_models = tuple(m.strip() for m in models_raw.split(",") if m.strip())
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
            poll_seconds=float(os.environ.get("WORKER_POLL_SECONDS", "1")),
            deploy_env=os.environ.get("DEPLOY_ENV", "dev"),
            sandbox_provider=os.environ.get("SANDBOX_PROVIDER", "local").lower(),
            sandbox_idle_seconds=int(os.environ.get("SANDBOX_IDLE_SECONDS", "600")),
            sandbox_extend_when_remaining_seconds=int(
                os.environ.get("SANDBOX_EXTEND_WHEN_REMAINING_SECONDS", "300")
            ),
            vercel_sandbox_max_session_seconds=int(
                os.environ.get("VERCEL_SANDBOX_MAX_SESSION_SECONDS", "2700")
            ),
            vercel_snapshot_retention_count=int(
                os.environ.get("VERCEL_SNAPSHOT_RETENTION_COUNT", "1")
            ),
            vercel_snapshot_delete_evicted=os.environ.get(
                "VERCEL_SNAPSHOT_DELETE_EVICTED", "1"
            )
            .lower()
            in ("1", "true", "yes"),
            run_event_max_bytes=int(os.environ.get("RUN_EVENT_MAX_BYTES", "65536")),
            openhands_sdk_version=os.environ.get("OPENHANDS_SDK_VERSION", "1.63.1"),
            liara_api_key=os.environ.get("LIARA_API_KEY", ""),
            liara_base_url=os.environ.get("LIARA_BASE_URL", ""),
            liara_default_model=liara_models[0] if liara_models else "deepseek/deepseek-v4.1-flash-1017",
            liara_models=liara_models,
            vercel_token=os.environ.get("VERCEL_TOKEN"),
            vercel_team_id=os.environ.get("VERCEL_TEAM_ID"),
            vercel_project_id=os.environ.get("VERCEL_PROJECT_ID"),
            vercel_base_snapshot_id=os.environ.get("VERCEL_BASE_SNAPSHOT_ID") or None,
            vercel_preview_wait_seconds=int(
                os.environ.get("VERCEL_PREVIEW_WAIT_SECONDS", "120")
            ),
            max_iterations=int(os.environ.get("MAX_ITERATIONS", "80")),
            templates_dir=os.environ.get(
                "TEMPLATES_DIR",
                os.path.join(os.path.dirname(__file__), "..", "..", "..", "templates"),
            ),
            agent_runtime=os.environ.get("AGENT_RUNTIME", "auto").lower(),
            agent_server_port=int(os.environ.get("AGENT_SERVER_PORT", "8000")),
            oh_secret_key=os.environ.get("OH_SECRET_KEY") or None,
            oh_session_api_key=os.environ.get("OH_SESSION_API_KEYS_0") or None,
            llm_proxy_public_url=os.environ.get("LLM_PROXY_PUBLIC_URL") or None,
            llm_proxy_admin_url=os.environ.get("LLM_PROXY_ADMIN_URL") or None,
            llm_proxy_admin_key=os.environ.get("LLM_PROXY_ADMIN_KEY") or None,
            run_orphan_policy=os.environ.get("RUN_ORPHAN_POLICY", "interrupt").lower(),
            llm_remote_direct_liara=os.environ.get("LLM_REMOTE_DIRECT_LIARA", "")
            .lower()
            in ("1", "true", "yes"),
        )