from __future__ import annotations
import os
import secrets
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


def data_directory(value=None):
    path = Path(value or os.getenv("MEET_DATA_DIR", str(ROOT / ".local")))
    return (path if path.is_absolute() else ROOT / path).resolve()


DEFAULTS = dict(
    provider_url="https://api.deepseek.com",
    model="deepseek-flash",
    auto_mode=True,
    auto_spacing_s=2.0,
    auto_per_minute=12,
    live_timeout_s=20,
    report_timeout_s=90,
    output_tokens=800,
    input_chars=18000,
    retention_days=30,
    persistence_mode="local",
    semantic_enabled=False,
    sentence_limit=3,
    language="vi",
    reply_language="en",
    price_input=None,
    price_output=None,
    price_date=None,
)
E5_MODEL = "intfloat/multilingual-e5-small"
# Resolved from Hugging Face model metadata during implementation; immutable model snapshot.
E5_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"


@dataclass
class Config:
    data_dir: Path
    token: str
    origins: tuple[str, ...]
    api_key: str = ""
    provider_url: str = "https://api.deepseek.com"
    model: str = "deepseek-flash"

    @classmethod
    def load(cls):
        load_dotenv(ROOT / ".env")
        path = data_directory()
        path.mkdir(parents=True, exist_ok=True)
        token_path = path / "pairing-token"
        from .ownership import atomic_private

        token = (
            token_path.read_text("utf8").strip()
            if token_path.exists()
            else secrets.token_urlsafe(32)
        )
        if len(token) < 32 or any(c.isspace() for c in token):
            raise RuntimeError(
                "PAIRING_FILE_INVALID: use rotate-token while backend is stopped, then pair again."
            )
        # Upgrade credentials created by older versions to private, atomic storage too.
        atomic_private(token_path, token)
        extension = os.getenv("MEET_EXTENSION_ID", "")
        origins = (
            (f"chrome-extension://{extension}",)
            if extension and extension != "replace_with_unpacked_extension_id"
            else ()
        )
        if os.getenv("MEET_DEV_ORIGIN"):
            origins += (os.environ["MEET_DEV_ORIGIN"],)
        from urllib.parse import urlparse

        provider = urlparse(os.getenv("MEET_PROVIDER_URL", DEFAULTS["provider_url"]))
        if (
            provider.scheme != "https"
            or not provider.hostname
            or provider.username
            or provider.query
            or provider.fragment
        ):
            raise RuntimeError(
                "Provider base URL must use HTTPS without credentials, query or fragment."
            )
        return cls(
            path,
            token_path.read_text(encoding="utf8").strip(),
            origins,
            os.getenv("DEEPSEEK_API_KEY", ""),
            os.getenv("MEET_PROVIDER_URL", DEFAULTS["provider_url"]),
            os.getenv("MEET_PROVIDER_MODEL", DEFAULTS["model"]),
        )
