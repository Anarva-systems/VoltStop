from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_name: str = "VoltStop API"
    # A cloud deployment must opt into development explicitly; otherwise missing
    # production configuration should fail closed during process startup.
    environment: str = "production"
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_publishable_key: str = ""
    bootstrap_admin_email: str = ""
    vendor_portal_origin: str = "http://localhost:3000"
    vendor_portal_preview_origins: str = ""
    vendor_portal_dev_origins: str = ""
    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = True
    booking_lock_ttl_seconds: int = 300
    razorpay_mode: str = ""
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    osrm_router_url: str = "https://router.project-osrm.org/route/v1/driving"
    google_maps_api_key: str = ""
    google_routes_url: str = "https://routes.googleapis.com/directions/v2:computeRoutes"
    database_pool_min_size: int = 1
    database_pool_max_size: int = 10

    @staticmethod
    def _canonical_origin(value: str) -> str:
        parsed = urlsplit(value.strip())
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or "*" in parsed.hostname
        ):
            raise ValueError("CORS origins must be explicit HTTP(S) origins without paths or wildcards")
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("CORS origin contains an invalid port") from exc
        hostname = parsed.hostname.lower()
        host = f"[{hostname}]" if ":" in hostname else hostname
        return f"{parsed.scheme.lower()}://{host}{f':{port}' if port is not None else ''}"

    @property
    def vendor_portal_allowed_origins(self) -> list[str]:
        origins = [self._canonical_origin(self.vendor_portal_origin)]
        for raw_origin in self.vendor_portal_preview_origins.split(","):
            origin = raw_origin.strip()
            if origin:
                origins.append(self._canonical_origin(origin))
        if self.environment.strip().lower() == "development":
            for raw_origin in self.vendor_portal_dev_origins.split(","):
                origin = raw_origin.strip()
                if origin:
                    origins.append(self._canonical_origin(origin))
        return list(dict.fromkeys(origins))

    @property
    def supabase_api_key(self) -> str:
        """Return the public Supabase key used for user-scoped Auth requests."""
        return self.supabase_publishable_key or self.supabase_anon_key

    @model_validator(mode="after")
    def validate_deployed_environment(self) -> "Settings":
        environment = self.environment.strip().lower()
        if environment not in {"development", "staging", "production"}:
            raise ValueError("ENVIRONMENT must be development, staging, or production")

        preview_origins = [
            origin.strip()
            for origin in self.vendor_portal_preview_origins.split(",")
            if origin.strip()
        ]
        for origin in preview_origins:
            canonical = self._canonical_origin(origin)
            if not canonical.startswith("https://"):
                raise ValueError("VENDOR_PORTAL_PREVIEW_ORIGINS must contain HTTPS origins only")
        if environment != "development" and self.vendor_portal_dev_origins.strip():
            raise ValueError("VENDOR_PORTAL_DEV_ORIGINS is allowed only in development")
        for origin in self.vendor_portal_dev_origins.split(","):
            if origin.strip():
                self._canonical_origin(origin)

        if environment == "development":
            mode = self.razorpay_mode.strip().lower()
            if mode == "live" or self.razorpay_key_id.startswith("rzp_live_"):
                raise ValueError("Live Razorpay credentials are not allowed in development")
            if mode and mode != "test":
                raise ValueError("RAZORPAY_MODE must be test in development")
            if (
                mode == "test"
                and self.razorpay_key_id
                and not self.razorpay_key_id.startswith("rzp_test_")
            ):
                raise ValueError("RAZORPAY_KEY_ID does not match the configured environment mode")
            return self

        expected_mode = "test" if environment == "staging" else "live"
        required = {
            "SUPABASE_URL": self.supabase_url,
            "SUPABASE_ANON_KEY or SUPABASE_PUBLISHABLE_KEY": self.supabase_api_key,
            "DATABASE_URL": self.database_url,
            "REDIS_URL": self.redis_url,
            "RAZORPAY_KEY_ID": self.razorpay_key_id,
            "RAZORPAY_KEY_SECRET": self.razorpay_key_secret,
            "RAZORPAY_MODE": self.razorpay_mode,
        }
        if environment == "production":
            required["RAZORPAY_WEBHOOK_SECRET"] = self.razorpay_webhook_secret
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError("Missing required staging/production settings: " + ", ".join(missing))

        supabase = urlsplit(self.supabase_url)
        database = urlsplit(self.database_url)
        redis = urlsplit(self.redis_url)
        portal = urlsplit(self.vendor_portal_origin)
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if supabase.scheme != "https" or not supabase.hostname:
            raise ValueError("SUPABASE_URL must use HTTPS and include a host")
        if supabase.hostname.lower() in local_hosts:
            raise ValueError("SUPABASE_URL cannot target localhost in staging/production")
        if database.scheme not in {"postgres", "postgresql"} or not database.hostname:
            raise ValueError("DATABASE_URL must identify a PostgreSQL host")
        if not database.username or not database.password:
            raise ValueError("DATABASE_URL must use an explicit database identity")
        if redis.scheme not in {"redis", "rediss"} or not redis.hostname:
            raise ValueError("REDIS_URL must identify a Redis host")
        if not redis.password:
            raise ValueError("REDIS_URL must use an explicit Redis credential")
        if not self.redis_enabled:
            raise ValueError("Redis must be enabled in staging/production")

        if database.hostname.lower() in local_hosts or redis.hostname.lower() in local_hosts:
            raise ValueError("Staging/production database and Redis hosts cannot be localhost")

        if (
            portal.scheme != "https"
            or not portal.hostname
            or portal.hostname.lower() in local_hosts
            or "*" in portal.hostname
        ):
            raise ValueError("VENDOR_PORTAL_ORIGIN must be a specific HTTPS origin")
        if portal.username or portal.password or portal.path not in {"", "/"} or portal.query or portal.fragment:
            raise ValueError("VENDOR_PORTAL_ORIGIN must contain only an origin")

        if self.razorpay_mode.strip().lower() != expected_mode:
            raise ValueError(f"RAZORPAY_MODE must be {expected_mode} for {environment}")
        expected_key_prefix = "rzp_test_" if expected_mode == "test" else "rzp_live_"
        if not self.razorpay_key_id.startswith(expected_key_prefix):
            raise ValueError("RAZORPAY_KEY_ID does not match the configured environment mode")
        if self.razorpay_webhook_secret and len(self.razorpay_webhook_secret) < 32:
            raise ValueError("RAZORPAY_WEBHOOK_SECRET must contain at least 32 characters")
        if environment == "production" and len(self.razorpay_webhook_secret) < 32:
            raise ValueError("RAZORPAY_WEBHOOK_SECRET must contain at least 32 characters")

        if redis.scheme != "rediss":
            raise ValueError("Staging/production REDIS_URL must use TLS (rediss)")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
