"""
Regression tests for H21:
  - Secrets & Initial Admin Configuration Hardening
  - Canonical configuration loading (.env parsing with strict precedence)
  - Rejection of missing/placeholder/weak secrets in production
  - Enforcement of secure initial admin setup (no open default admin)
"""

from __future__ import annotations

import hashlib
import os
import secrets
import tempfile
from pathlib import Path

import pytest

from broast_pos.config import config
from broast_pos.core.services.auth_service import AuthService
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.database.seed import seed_database, validate_no_default_admin
from broast_pos.data.repositories.user_repository import UserRepository


# ---------------------------------------------------------------------------
# Helpers & Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def isolate_env():
    """Isolate os.environ across all tests in this file."""
    old_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(old_env)


@pytest.fixture()
def clean_db():
    temp_dir = tempfile.mkdtemp()
    db_file = os.path.join(temp_dir, "test_h21.db")
    DatabaseConnection.reset()
    db = DatabaseConnection.get_instance(db_file)
    initialise_database(db)
    yield db
    DatabaseConnection.reset()


# ---------------------------------------------------------------------------
# 1. Canonical Configuration / .env Loader Tests
# ---------------------------------------------------------------------------
class TestConfigurationLoading:
    def test_load_env_file_respects_process_env_precedence(self, tmp_path, monkeypatch):
        """Process environment variables take top precedence over .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# Comment line\n"
            "APP_ENV=prod\n"
            'BROAST_PIN_PEPPER="pepper-from-file-1234567890"\n'
            "NEW_VAR=hello\n"
            "QUOTED_VAR='single_quoted_val'\n",
            encoding="utf-8",
        )

        # Set an existing process env var
        monkeypatch.setenv("APP_ENV", "dev")
        monkeypatch.delenv("BROAST_PIN_PEPPER", raising=False)
        monkeypatch.delenv("NEW_VAR", raising=False)
        monkeypatch.delenv("QUOTED_VAR", raising=False)

        loaded = config.load_env_file(env_file, override=False)

        # Process env should win for APP_ENV
        assert os.environ["APP_ENV"] == "dev"
        # .env file should populate previously unset variables
        assert os.environ["BROAST_PIN_PEPPER"] == "pepper-from-file-1234567890"
        assert os.environ["NEW_VAR"] == "hello"
        assert os.environ["QUOTED_VAR"] == "single_quoted_val"
        assert loaded["APP_ENV"] == "prod"

    def test_load_env_file_with_override(self, tmp_path, monkeypatch):
        """Explicit override=True allows reloading from file."""
        env_file = tmp_path / ".env"
        env_file.write_text("CUSTOM_KEY=from_file\n", encoding="utf-8")
        monkeypatch.setenv("CUSTOM_KEY", "initial")

        config.load_env_file(env_file, override=True)
        assert os.environ["CUSTOM_KEY"] == "from_file"


# ---------------------------------------------------------------------------
# 2. Production Secret & Placeholder Rejection Tests
# ---------------------------------------------------------------------------
class TestProductionSecretsRejection:
    @pytest.mark.parametrize(
        "placeholder",
        [
            "",
            "   ",
            "broast-pos-default-pepper-change-me",
            "change-me-to-a-secure-random-secret-pepper-string",
            "broast-dev-fallback-pepper-2026-unsecret",
            "test-pepper",
            "change-me-custom-secret",
            "my_placeholder_secret_key",
            "dummy_secret_value_12345",
            "short-pepper",  # < 16 chars
        ],
    )
    def test_production_start_with_placeholder_secret_fails(self, monkeypatch, placeholder):
        """Produktivstart mit Platzhalter-Secret scheitert."""
        monkeypatch.setenv("APP_ENV", "prod")
        monkeypatch.setenv("BROAST_PIN_PEPPER", placeholder)

        # 1. validate_production_secrets fails directly
        with pytest.raises(RuntimeError, match="(?i)(insecure|placeholder|must be set|refusing)"):
            config.validate_production_secrets()

        # 2. AuthService initialization fails in production
        with pytest.raises(RuntimeError):
            AuthService()

    def test_production_with_valid_secret_passes(self, monkeypatch):
        """A strong, non-placeholder secret passes production validation."""
        valid_pepper = "f4c9a871b30e42d7a5e91234567890abcdef1234567890"
        monkeypatch.setenv("APP_ENV", "prod")
        monkeypatch.setenv("BROAST_PIN_PEPPER", valid_pepper)

        config.validate_production_secrets()
        assert config.get_pin_pepper() == valid_pepper

    def test_dev_mode_permits_dev_fallback_pepper(self, monkeypatch):
        """Development mode continues to permit the safe fallback pepper."""
        monkeypatch.setenv("APP_ENV", "dev")
        monkeypatch.delenv("BROAST_PIN_PEPPER", raising=False)

        # In dev mode, validation is a no-op
        config.validate_production_secrets()
        assert config.get_pin_pepper() == config.DEV_FALLBACK_PEPPER


# ---------------------------------------------------------------------------
# 3. Initial Admin & Default Admin Access Tests
# ---------------------------------------------------------------------------
class TestInitialAdminSecurity:
    def test_production_seeding_without_admin_pin_fails_and_leaves_no_user(
        self, clean_db, monkeypatch
    ):
        """Ohne sichere Einrichtung bleibt kein Standard-Admin-Zugang offen:

        Calling seed_database() in production without BROAST_INITIAL_ADMIN_PIN fails,
        and no user record is created in the database.
        """
        monkeypatch.setenv("APP_ENV", "prod")
        monkeypatch.setenv("BROAST_PIN_PEPPER", "a" * 32)
        monkeypatch.delenv("BROAST_INITIAL_ADMIN_PIN", raising=False)
        monkeypatch.delenv("INITIAL_ADMIN_PIN", raising=False)

        with pytest.raises(RuntimeError, match="(?i)initial admin setup required"):
            seed_database(clean_db)

        # Zero users seeded: NO default admin left open
        users = clean_db.fetch_all("SELECT * FROM users")
        assert len(users) == 0

    @pytest.mark.parametrize("trivial_pin", ["1234", "0000", "1111", "9999", "123"])
    def test_production_seeding_with_trivial_pin_rejected(
        self, clean_db, monkeypatch, trivial_pin
    ):
        """Default or trivial PINs like '1234' are rejected in production."""
        monkeypatch.setenv("APP_ENV", "prod")
        monkeypatch.setenv("BROAST_PIN_PEPPER", "a" * 32)
        monkeypatch.setenv("BROAST_INITIAL_ADMIN_PIN", trivial_pin)

        with pytest.raises(RuntimeError, match="(?i)insecure broast_initial_admin_pin"):
            seed_database(clean_db)

        users = clean_db.fetch_all("SELECT * FROM users")
        assert len(users) == 0

    def test_production_seeding_with_secure_pin_succeeds(
        self, clean_db, monkeypatch
    ):
        """A secure initial admin PIN seeds the admin user with salted PBKDF2 hash."""
        secure_pin = "874209"
        valid_pepper = "c" * 32
        monkeypatch.setenv("APP_ENV", "prod")
        monkeypatch.setenv("BROAST_PIN_PEPPER", valid_pepper)
        monkeypatch.setenv("BROAST_INITIAL_ADMIN_PIN", secure_pin)

        seed_database(clean_db)

        users = clean_db.fetch_all("SELECT * FROM users")
        assert len(users) == 1
        admin = users[0]
        assert admin["username"] == "admin"
        assert admin["role"] == "admin"
        assert admin["pin_salt"] is not None
        assert admin["pin_hash"].startswith("pbkdf2_sha256$")

        # Verify authentication
        auth = AuthService(UserRepository(clean_db))
        # Default PIN "1234" must NOT authenticate
        with pytest.raises(ValueError):
            auth.login_by_pin("1234")

        # Configured PIN must authenticate successfully
        logged_in = auth.login_by_pin(secure_pin)
        assert logged_in.username == "admin"

        # validate_no_default_admin must pass
        validate_no_default_admin(clean_db)

    def test_validate_no_default_admin_blocks_legacy_1234_hash_in_prod(
        self, clean_db, monkeypatch
    ):
        """In production, an existing user with the published default PIN '1234' is rejected."""
        monkeypatch.setenv("APP_ENV", "prod")
        monkeypatch.setenv("BROAST_PIN_PEPPER", "d" * 32)

        legacy_hash = hashlib.sha256(b"1234").hexdigest()
        clean_db.execute(
            "INSERT INTO users (username, display_name, pin_hash, role, is_active) "
            "VALUES (?, ?, ?, ?, 1)",
            ("admin", "Default Admin", legacy_hash, "admin"),
        )
        clean_db.commit()

        with pytest.raises(RuntimeError, match="(?i)default admin credentials detected"):
            validate_no_default_admin(clean_db)

    def test_validate_no_default_admin_blocks_salted_1234_in_prod(
        self, clean_db, monkeypatch
    ):
        """Even if salted PBKDF2, if the PIN is '1234', production refuses to run."""
        pepper = "e" * 32
        monkeypatch.setenv("APP_ENV", "prod")
        monkeypatch.setenv("BROAST_PIN_PEPPER", pepper)

        salt = secrets.token_hex(16)
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            (pepper + "1234").encode("utf-8"),
            salt.encode("utf-8"),
            100_000,
        )
        pbkdf2_hash = f"pbkdf2_sha256$100000${dk.hex()}"

        clean_db.execute(
            "INSERT INTO users (username, display_name, pin_hash, pin_salt, role, is_active) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            ("admin", "Default Admin", pbkdf2_hash, salt, "admin"),
        )
        clean_db.commit()

        with pytest.raises(RuntimeError, match="(?i)default admin credentials detected"):
            validate_no_default_admin(clean_db)

    def test_dev_mode_still_seeds_default_admin(self, clean_db, monkeypatch):
        """In dev mode without custom PIN, default admin with PIN 1234 is seeded for convenience."""
        monkeypatch.setenv("APP_ENV", "dev")
        monkeypatch.delenv("BROAST_INITIAL_ADMIN_PIN", raising=False)
        monkeypatch.delenv("INITIAL_ADMIN_PIN", raising=False)

        seed_database(clean_db)
        auth = AuthService(UserRepository(clean_db))
        user = auth.login_by_pin("1234")
        assert user.username == "admin"


# ---------------------------------------------------------------------------
# 4. Gitignore Secrets Protection Tests
# ---------------------------------------------------------------------------
class TestGitignoreSecrets:
    def test_gitignore_contains_secret_and_env_patterns(self):
        """Verify .gitignore includes .env, secret files, and real printer config."""
        gitignore_path = Path(__file__).resolve().parent.parent / ".gitignore"
        content = gitignore_path.read_text(encoding="utf-8")

        assert ".env" in content
        assert ".env.*" in content
        assert "!.env.example" in content
        assert "*.secret" in content
        assert "*.key" in content
        assert "*.pem" in content
        assert "broast_pos/config/printers.json" in content
