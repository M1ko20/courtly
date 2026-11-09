import os
from pathlib import Path

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://reservations:reservations@localhost:5432/reservations"
)
DEFAULT_SECRET_KEY = "dev-only-insecure-secret-change-me"
DEFAULT_UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
# A VAPID keypair identifies this server to browser push services (FCM,
# Mozilla's push service, ...) — it doesn't protect user data, it just lets
# a push service tell "our server" apart from anyone else. Same deliberate
# dev-only-fallback pattern as DEFAULT_SECRET_KEY (ADR-003): fine for local
# dev out of the box, must be overridden by env vars for anything beyond
# that. Generated once with py_vapid.Vapid02().generate_keys(), not secret
# in the sense a real credential is.
DEFAULT_VAPID_PUBLIC_KEY = "BIBfr7saQ_QdBF9zqTj6Q0si2h91lTokpAtaPzf8phZXQ1_SXkBuMzJlpRdZHzMI54HQcJyGVxIdenGhNPaqtl4"
DEFAULT_VAPID_PRIVATE_KEY = "I8WX6J2BxWWkXk-ItfLFUQADSJJIUJdmEvxrCu7Pguc"


def _normalize_database_url(url: str) -> str:
    """Hosting providers (Render, Heroku, ...) hand out plain postgres:// or
    postgresql:// URLs; SQLAlchemy would then pick psycopg2, which isn't
    installed — point it at psycopg (v3) instead."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class Settings:
    def __init__(self) -> None:
        self.database_url = _normalize_database_url(
            os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
        )
        self.secret_key = os.environ.get("SECRET_KEY", DEFAULT_SECRET_KEY)
        self.access_token_expire_minutes = int(
            os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
        )
        self.frontend_origin = os.environ.get(
            "FRONTEND_ORIGIN", "http://localhost:5173"
        )
        self.upload_dir = Path(os.environ.get("UPLOAD_DIR", str(DEFAULT_UPLOAD_DIR)))
        self.vapid_public_key = os.environ.get(
            "VAPID_PUBLIC_KEY", DEFAULT_VAPID_PUBLIC_KEY
        )
        self.vapid_private_key = os.environ.get(
            "VAPID_PRIVATE_KEY", DEFAULT_VAPID_PRIVATE_KEY
        )
        self.vapid_contact_email = os.environ.get(
            "VAPID_CONTACT_EMAIL", "admin@courtly.example"
        )
        # "text" (key=value lines, readable in a terminal) or "json" (one
        # object per line, for shipping logs somewhere) — see observability.py.
        self.log_format = os.environ.get("LOG_FORMAT", "text")
        self.log_level = os.environ.get("LOG_LEVEL", "INFO")


settings = Settings()
