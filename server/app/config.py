import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    ollama_url: str
    model: str
    auth_token: str
    db_path: Path
    bind_host: str
    bind_port: int
    system_prompt: str


def load_config() -> Config:
    return Config(
        ollama_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"),
        model=os.getenv("MODEL", "llama3.1:8b"),
        auth_token=os.getenv("AUTH_TOKEN", ""),
        db_path=Path(os.getenv("DB_PATH", "skynet.db")),
        bind_host=os.getenv("BIND_HOST", "0.0.0.0"),
        bind_port=int(os.getenv("BIND_PORT", "8080")),
        system_prompt=os.getenv(
            "SYSTEM_PROMPT",
            "You are a helpful personal assistant running on the user's own hardware. Be concise.",
        ),
    )


config = load_config()
