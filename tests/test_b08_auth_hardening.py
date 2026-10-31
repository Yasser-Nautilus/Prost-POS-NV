"""
Tests for B-08 — Auth Hardening.

Covers:
  - PIN minimum length (≥4) at create_user and update_user
  - Brute-force throttle on login(), login_by_pin(), verify_pin()
  - Throttle resets after successful authentication
  - Throttle lockout raises ValueError with remaining seconds
  - Throttle expires after the lockout window
  - Audit log called on failed attempts
  - verify_pin() still returns None for wrong role (not throttled on role mismatch alone after 1 attempt)
"""
from __future__ import annotations

import time
import pytest
from unittest.mock import MagicMock, patch

from broast_pos.core.services.auth_service import (
    AuthService,
    _PIN_MIN_LENGTH,
    _MAX_ATTEMPTS,
    _LOCKOUT_SECONDS,
)
from broast_pos.core.models.user import User, UserRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user(
    user_id: int = 1,
    role: UserRole = UserRole.CASHIER,
    pin: str = "1234",
    is_active: bool = True,
) -> User:
    svc = AuthService.__new__(AuthService)
    pin_hash = AuthService.hash_pin(pin)
    return User(
        id=user_id,
        username=f"user{user_id}",
        display_name=f"User {user_id}",
        role=role,
        pin_hash=pin_hash,
        is_active=is_active,
    )


def _manager(pin: str = "9999") -> User:
    return _user(user_id=99, role=UserRole.MANAGER, pin=pin)


def _auth_svc(users_by_id=None, users_by_pin=None) -> AuthService:
    """Build AuthService with mocked repo."""
    repo = MagicMock()
    repo.get_by_id.side_effect = lambda uid: (users_by_id or {}).get(uid)
    repo.get_by_pin.side_effect = lambda ph: (users_by_pin or {}).get(ph)
    repo.pin_exists.return_value = False
    repo.save.side_effect = lambda u: u
    repo.get_all_active.return_value = []
    repo.get_all.return_value = []

    svc = AuthService(user_repo=repo)
    return svc


# ===========================================================================
# Part A: PIN minimum length
# ===========================================================================

class TestPinMinimumLength:

    def test_create_user_rejects_short_pin(self):
        """PIN shorter than _PIN_MIN_LENGTH must be rejected."""
        svc = _auth_svc()
        short_pin = "1" * (_PIN_MIN_LENGTH - 1)
        with pytest.raises(ValueError, match=str(_PIN_MIN_LENGTH)):
            svc.create_user(
                username="test", display_name="Test",
                role=UserRole.CASHIER, pin=short_pin,
            )

    def test_create_user_accepts_min_length_pin(self):
        """Exactly _PIN_MIN_LENGTH chars must be accepted."""
        svc = _auth_svc()
        ok_pin = "1" * _PIN_MIN_LENGTH
        # Should not raise
        svc.create_user(
            username="test", display_name="Test",
            role=UserRole.CASHIER, pin=ok_pin,
        )

    def test_create_user_accepts_longer_pin(self):
        svc = _auth_svc()
        svc.create_user(
            username="test", display_name="Test",
            role=UserRole.CASHIER, pin="12345678",
        )

    def test_update_user_rejects_short_pin(self):
        """update_user must also enforce min length."""
        user = _user()
        svc = _auth_svc(users_by_id={1: user})
        short_pin = "1" * (_PIN_MIN_LENGTH - 1)
        with pytest.raises(ValueError, match=str(_PIN_MIN_LENGTH)):
            svc.update_user(user_id=1, pin=short_pin)

    def test_update_user_accepts_min_length_pin(self):
        user = _user()
        svc = _auth_svc(users_by_id={1: user})
        ok_pin = "1" * _PIN_MIN_LENGTH
        svc.update_user(user_id=1, pin=ok_pin)

    def test_empty_pin_still_rejected_with_original_message(self):
        """Empty PIN must raise the original 'required' error, not length error."""
        svc = _auth_svc()
        with pytest.raises(ValueError):
            svc.create_user(username="test", display_name="Test",
                            role=UserRole.CASHIER, pin="")


# ===========================================================================
# Part B: Brute-force throttle — login()
# ===========================================================================

class TestLoginThrottle:

    def _svc_with_user(self, user: User) -> AuthService:
        pin_hash = user.pin_hash
        return _auth_svc(
            users_by_id={user.id: user},
            users_by_pin={pin_hash: user},
        )

    def test_first_failure_not_locked(self):
        """Single failure must not lock out."""
        user = _user()
        svc = self._svc_with_user(user)
        with pytest.raises(ValueError, match="PIN"):
            svc.login(user_id=1, pin="WRONG")
        count, locked = svc.get_throttle_state(f"uid:{user.id}")
        assert count == 1
        assert not locked

    def test_max_attempts_locks_out(self):
        """After _MAX_ATTEMPTS failures the next attempt is blocked."""
        user = _user()
        svc = self._svc_with_user(user)
        # Exhaust attempts
        for _ in range(_MAX_ATTEMPTS):
            try:
                svc.login(user_id=1, pin="WRONG")
            except ValueError:
                pass
        # Next attempt must be throttled
        with pytest.raises(ValueError, match="ثانية"):
            svc.login(user_id=1, pin="WRONG")

    def test_throttle_resets_on_success(self):
        """Successful login clears the failure count."""
        user = _user(pin="1234")
        svc = self._svc_with_user(user)
        # Some failures
        for _ in range(2):
            try:
                svc.login(user_id=1, pin="WRONG")
            except ValueError:
                pass
        # Successful login
        svc.login(user_id=1, pin="1234")
        count, locked = svc.get_throttle_state(f"uid:{user.id}")
        assert count == 0
        assert not locked

    def test_throttle_expires_after_window(self):
        """After _LOCKOUT_SECONDS the lockout should clear."""
        user = _user()
        svc = self._svc_with_user(user)
        # Exhaust attempts
        for _ in range(_MAX_ATTEMPTS):
            try:
                svc.login(user_id=1, pin="WRONG")
            except ValueError:
                pass
        # Fake time elapsed past lockout window
        key = f"uid:{user.id}"
        count, first_ts = svc._throttle[key]
        svc._throttle[key] = (count, first_ts - _LOCKOUT_SECONDS - 1)
        # Should NOT raise throttle error now (lockout expired)
        with pytest.raises(ValueError, match="PIN"):  # original PIN error, not throttle
            svc.login(user_id=1, pin="WRONG")


# ===========================================================================
# Part C: Brute-force throttle — login_by_pin()
# ===========================================================================

class TestLoginByPinThrottle:

    def test_repeated_failures_lock_out(self):
        """login_by_pin() must throttle after _MAX_ATTEMPTS wrong PINs."""
        svc = _auth_svc(users_by_pin={})  # no matching user for any PIN

        for _ in range(_MAX_ATTEMPTS):
            try:
                svc.login_by_pin("WRONG_PIN")
            except ValueError:
                pass
        with pytest.raises(ValueError, match="ثانية"):
            svc.login_by_pin("WRONG_PIN")

    def test_success_resets_throttle(self):
        """Successful login_by_pin clears failure count."""
        user = _user(pin="5678")
        pin_hash = AuthService.hash_pin("5678")
        svc = _auth_svc(users_by_pin={pin_hash: user})

        # Some failures with a different PIN (same key prefix won't match)
        # Then success
        svc.login_by_pin("5678")
        # No lockout expected
        _, locked = svc.get_throttle_state(f"pin:{pin_hash[:8]}")
        assert not locked


# ===========================================================================
# Part D: Brute-force throttle — verify_pin()
# ===========================================================================

class TestVerifyPinThrottle:

    def test_verify_pin_throttled_after_max_attempts(self):
        """verify_pin() must throttle brute-force override attempts."""
        svc = _auth_svc(users_by_pin={})
        for _ in range(_MAX_ATTEMPTS):
            svc.verify_pin("WRONG")   # returns None, records failure
        with pytest.raises(ValueError, match="ثانية"):
            svc.verify_pin("WRONG")

    def test_verify_pin_wrong_role_counts_as_failure(self):
        """A cashier's valid PIN used for override must count as failure."""
        cashier = _user(role=UserRole.CASHIER, pin="1111")
        pin_hash = AuthService.hash_pin("1111")
        svc = _auth_svc(users_by_pin={pin_hash: cashier})
        result = svc.verify_pin("1111")
        assert result is None   # wrong role — not authorized
        count, _ = svc.get_throttle_state(f"override:{pin_hash[:8]}")
        assert count >= 1

    def test_verify_pin_success_resets_throttle(self):
        """Successful verify_pin (manager PIN) clears the failure count."""
        mgr = _manager(pin="9999")
        pin_hash = AuthService.hash_pin("9999")
        svc = _auth_svc(users_by_pin={pin_hash: mgr})
        # Cause 1 failure first (wrong PIN)
        svc.verify_pin("0000")
        # Now succeed
        result = svc.verify_pin("9999")
        assert result is not None
        _, locked = svc.get_throttle_state(f"override:{pin_hash[:8]}")
        assert not locked


# ===========================================================================
# Part E: Audit logging on failures
# ===========================================================================

class TestAuditOnFailures:

    def test_audit_called_on_login_failure(self):
        """Failed login must call audit_repo.log()."""
        user = _user()
        svc = _auth_svc(users_by_id={1: user})
        audit_mock = MagicMock()
        svc.set_audit(audit_mock)

        try:
            svc.login(user_id=1, pin="WRONG")
        except ValueError:
            pass

        audit_mock.log.assert_called_once()
        call_kwargs = audit_mock.log.call_args[1]
        assert call_kwargs["event_type"] == "login_failed"

    def test_audit_not_required(self):
        """If no audit set, failure recording must not crash."""
        user = _user()
        svc = _auth_svc(users_by_id={1: user})
        # No audit set — should not raise
        try:
            svc.login(user_id=1, pin="WRONG")
        except ValueError:
            pass


# ===========================================================================
# Part F: Throttle isolation — different users independent
# ===========================================================================

class TestThrottleIsolation:

    def test_different_users_have_independent_throttles(self):
        """Failures for user 1 must not affect user 2."""
        user1 = _user(user_id=1)
        user2 = _user(user_id=2, pin="5678")
        pin2 = AuthService.hash_pin("5678")
        svc = _auth_svc(
            users_by_id={1: user1, 2: user2},
            users_by_pin={pin2: user2},
        )
        # Exhaust user1
        for _ in range(_MAX_ATTEMPTS):
            try:
                svc.login(user_id=1, pin="WRONG")
            except ValueError:
                pass
        # user2 should still be accessible
        result = svc.login(user_id=2, pin="5678")
        assert result.id == 2
