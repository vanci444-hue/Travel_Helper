"""应用配置：只从 backend/.env 经 ConfigManager 读取，use_env=False。"""

from __future__ import annotations

from pathlib import Path

from pycore.core import BaseSettings, ConfigManager

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BACKEND_DIR / ".env"

DEFAULT_CORS_ORIGINS = [
    "http://localhost:5199",
    "http://127.0.0.1:5199",
    "http://localhost:5175",
    "http://127.0.0.1:5175",
    "http://localhost:8099",
    "http://127.0.0.1:8099",
    "http://localhost:8003",
    "http://127.0.0.1:8003",
]


class AppSettings(BaseSettings):
    debug: bool = True
    secret_key: str
    host: str = "127.0.0.1"
    port: int = 8099
    cors_origins: list[str] = DEFAULT_CORS_ORIGINS
    database_path: str = "data/Travel_Helper.db"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"
    manager_thinking_enabled: bool = False
    itinerary_thinking_enabled: bool = True
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 1
    amap_web_key: str = ""
    amap_timeout_seconds: int = 10
    planning_timeout_seconds: int = 180
    max_tool_iterations_research: int = 8
    max_tool_iterations_itinerary: int = 12
    walk_threshold_m: int = 1200
    manager_history_limit: int = 20
    intake_max_followups: int = 2


def _ensure_env_file() -> None:
    if ENV_PATH.exists():
        return
    example = BACKEND_DIR / ".env.example"
    if example.exists():
        ENV_PATH.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        return
    ENV_PATH.write_text("secret_key=change-me\n", encoding="utf-8")


def resolve_database_file(path_value: str) -> Path:
    db_path = Path(path_value)
    if not db_path.is_absolute():
        db_path = (BACKEND_DIR / db_path).resolve()
    else:
        db_path = db_path.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def load_settings() -> AppSettings:
    _ensure_env_file()
    manager: ConfigManager[AppSettings] = ConfigManager()
    try:
        loaded = manager.settings
        if isinstance(loaded, AppSettings):
            return loaded
    except Exception:
        pass
    manager.load(AppSettings, ENV_PATH, use_env=False)
    return manager.settings


settings = load_settings()
database_file = resolve_database_file(settings.database_path)
database_url = f"sqlite+aiosqlite:///{database_file}"
