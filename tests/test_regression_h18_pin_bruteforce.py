"""
Regression tests — H18: PIN-only throttling did not limit a sequence of
different guesses.

Root cause:
  login_by_pin() and verify_pin() derived their throttle key from a hash of
  the ENTERED GUESS (pin_hash[:8]). Each new wrong PIN landed in a fresh
  bucket, so an attacker rotating through different guesses never hit the
  failure count needed to trigger the lockout. The guess-derived key was
  also logged, which is unsuitable for a small PIN space (effectively a
  fingerprint of the guess).

Fix verified here:
  - A sequence of DIFFERENT wrong PINs against login_by_pin()/verify_pin()
    still accumulates failures on one shared key and triggers the lockout,
    not just repeating the same wrong PIN.
  - The throttle key logged/stored for these paths is a fixed, non-guess
    derived label ("pin-only-login" / "manager-override"), never a hash of
    the attempted PIN.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from broast_pos.core.services.auth_service import _MAX_ATTEMPTS, AuthService


def _auth_svc() -> AuthService:
    """AuthService with no matching user for any PIN — every guess fails."""
    repo = MagicMock()
    repo.get_by_pin.return_value = None
    repo.pin_exists.return_value = False
    return AuthService(user_repo=repo)


class TestH18RotatingGuessesStillLockOut:

    def test_login_by_pin_rotating_wrong_pins_triggers_lockout(self):
        svc = _auth_svc()
        # A different wrong PIN every time — the old bug gave each one its
        # own bucket, so the lockout was never reached.
        for i in range(_MAX_ATTEMPTS):
            with pytest.raises(ValueError):
                svc.login_by_pin(f"{1000 + i}")

        with pytest.raises(ValueError, match="ثانية"):
            svc.login_by_pin("9999")  # yet another new guess — still locked

    def test_verify_pin_rotating_wrong_pins_triggers_lockout(self):
        svc = _auth_svc()
        for i in range(_MAX_ATTEMPTS):
            svc.verify_pin(f"{2000 + i}")

        with pytest.raises(ValueError, match="ثانية"):
            svc.verify_pin("8888")

    def test_login_by_pin_throttle_key_is_not_guess_derived(self):
        """The stored key must be a fixed label, never tied to the guess."""
        svc = _auth_svc()
        for guess in ("1111", "2222"):  # different guesses — must hit the SAME key
            with pytest.raises(ValueError):
                svc.login_by_pin(guess)
        count, _ = svc.get_throttle_state("pin-only-login")
        assert count == 2, "Different guesses must accumulate on one shared key"

    def test_verify_pin_throttle_key_is_not_guess_derived(self):
        svc = _auth_svc()
        svc.verify_pin("1111")
        svc.verify_pin("2222")
        count, _ = svc.get_throttle_state("manager-override")
        assert count == 2, "Different guesses must accumulate on one shared key"

    def test_no_guess_derived_fingerprint_in_log(self, caplog):
        """H18: never log a guess-derived identifier for a small PIN space."""
        import logging
        svc = _auth_svc()
        with caplog.at_level(logging.WARNING):
            with pytest.raises(ValueError):
                svc.login_by_pin("424242")
        assert "424242" not in caplog.text
        pin_hash_prefix = AuthService.hash_pin("424242")[:8]
        assert pin_hash_prefix not in caplog.text
