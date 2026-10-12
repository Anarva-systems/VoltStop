import pytest
from pydantic import ValidationError

from app.core.config import Settings


def staging_settings(**overrides) -> Settings:
    values = {
        "environment": "staging",
        "supabase_url": "https://phase23-project.supabase.co",
        "supabase_anon_key": "synthetic-staging-anon-key",
        "vendor_portal_origin": "https://vendor.staging.voltstop.example",
        "database_url": "postgresql://phase23_user:synthetic-db-pass@db.staging.example:5432/voltstop_staging",
        "redis_url": "rediss://phase23_user:synthetic-redis-pass@redis.staging.example:6380/0",
        "razorpay_mode": "test",
        "razorpay_key_id": "rzp_test_phase23",
        "razorpay_key_secret": "synthetic-razorpay-test-secret",
        "razorpay_webhook_secret": "synthetic-webhook-secret-with-32-characters",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_development_keeps_local_defaults():
    settings = Settings(_env_file=None)

    assert settings.environment == "development"
    assert settings.razorpay_mode == ""


def test_development_rejects_live_razorpay_configuration():
    with pytest.raises(ValidationError, match="Live Razorpay credentials are not allowed"):
        Settings(_env_file=None, environment="development", razorpay_mode="live")


def test_staging_accepts_explicit_isolated_test_configuration():
    settings = staging_settings()

    assert settings.environment == "staging"
    assert settings.razorpay_mode == "test"


def test_staging_rejects_missing_required_configuration():
    with pytest.raises(ValidationError, match="Missing required staging/production settings"):
        Settings(_env_file=None, environment="staging")


def test_staging_rejects_live_razorpay_credentials():
    with pytest.raises(ValidationError, match="RAZORPAY_KEY_ID does not match"):
        staging_settings(razorpay_key_id="rzp_live_phase23")


def test_staging_requires_a_non_local_database():
    with pytest.raises(ValidationError, match="cannot be localhost"):
        staging_settings(database_url="postgresql://phase23_user:secret@localhost:5432/voltstop_staging")


def test_staging_requires_authenticated_redis():
    with pytest.raises(ValidationError, match="explicit Redis credential"):
        staging_settings(redis_url="redis://redis.staging.example:6379/0")


def test_staging_requires_tls_for_redis():
    with pytest.raises(ValidationError, match="must use TLS"):
        staging_settings(redis_url="redis://phase23_user:synthetic-redis-pass@redis.staging.example:6379/0")


def test_staging_cannot_disable_redis():
    with pytest.raises(ValidationError, match="Redis must be enabled"):
        staging_settings(redis_enabled=False)


def test_staging_rejects_wildcard_or_non_https_portal_origin():
    with pytest.raises(ValidationError, match="specific HTTPS origin"):
        staging_settings(vendor_portal_origin="*")
    with pytest.raises(ValidationError, match="specific HTTPS origin"):
        staging_settings(vendor_portal_origin="https://*.staging.voltstop.example")


def test_staging_rejects_weak_webhook_secret():
    with pytest.raises(ValidationError, match="at least 32 characters"):
        staging_settings(razorpay_webhook_secret="short")


def test_production_requires_live_mode_and_tls_redis():
    with pytest.raises(ValidationError, match="RAZORPAY_MODE must be live"):
        staging_settings(environment="production")

    with pytest.raises(ValidationError, match="must use TLS"):
        staging_settings(
            environment="production",
            razorpay_mode="live",
            razorpay_key_id="rzp_live_phase23",
            redis_url="redis://phase23_user:synthetic-redis-pass@redis.prod.example:6379/0",
        )


def test_production_accepts_explicit_live_configuration():
    settings = staging_settings(
        environment="production",
        razorpay_mode="live",
        razorpay_key_id="rzp_live_phase23",
    )

    assert settings.environment == "production"
    assert settings.razorpay_mode == "live"


def test_unknown_environment_fails_closed():
    with pytest.raises(ValidationError, match="ENVIRONMENT must be"):
        Settings(_env_file=None, environment="prod")


def test_configuration_validation_error_does_not_expose_secret_values():
    sentinel = "synthetic-secret-must-not-appear"

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, environment="staging", razorpay_key_secret=sentinel)

    assert sentinel not in str(error.value)
