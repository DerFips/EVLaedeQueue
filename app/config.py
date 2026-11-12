from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "EVLädeQueue"
    app_env: str = "production"
    app_debug: bool = False
    app_secret_key: str
    app_base_url: str = "http://localhost:8000"

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 14

    database_url: str = "sqlite:///./data/ladeplatz.db"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True

    cors_allowed_origins: str = "http://localhost:3000"

    avatar_max_upload_bytes: int = 2 * 1024 * 1024
    avatar_output_size_px: int = 256

    admin_bootstrap_email: str = ""
    admin_bootstrap_password: str = ""

    # Apple Push Notification service (APNs), Token-Authentifizierung mit .p8-Schluessel.
    # Schluessel entweder als Dateipfad (APNS_AUTH_KEY_PATH) oder direkt als Text mit
    # "\n" statt Zeilenumbruechen (APNS_AUTH_KEY). Leer = Push deaktiviert.
    apns_key_id: str = ""
    apns_team_id: str = ""
    apns_bundle_id: str = ""
    apns_auth_key_path: str = ""
    apns_auth_key: str = ""
    # true fuer Entwicklungs-Builds (aus Xcode gestartet), false fuer TestFlight/App Store.
    apns_use_sandbox: bool = False

    max_request_body_bytes: int = 64 * 1024
    max_cars_per_user: int = 10

    @model_validator(mode="after")
    def _reject_weak_secrets(self):
        # Mit einem bekannten Platzhalter als JWT-Schluessel kann jeder gueltige
        # (auch Admin-)Tokens faelschen. In Produktion deshalb gar nicht erst starten.
        if self.app_env == "production":
            for name in ("app_secret_key", "jwt_secret_key"):
                value = getattr(self, name)
                if len(value) < 32 or value.upper().startswith("CHANGE_ME"):
                    raise ValueError(
                        f"{name.upper()} ist ein Platzhalter oder zu kurz (min. 32 Zeichen). "
                        "Erzeugen mit: openssl rand -hex 32"
                    )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


settings = Settings()
