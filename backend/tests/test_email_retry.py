"""
Email delivery resilience tests (password-reset OTP).

Rules honored here:
  * No real network/SMTP is used — smtplib.SMTP inside email_service is replaced
    with a fake so tests are deterministic and offline.
  * No credentials are read from or written to the environment; dummy values are
    set for the duration of each test and restored afterwards.
  * Expectations are hand-computed from the fake's recorded behaviour, not from
    the code under test.
"""
import os
import smtplib
import sys
import unittest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import email_service
from config import settings
from email_service import EmailDeliveryError, send_otp_email


class _NoSleepTime:
    """Stand-in for the time module so retry backoff doesn't slow the suite."""
    def sleep(self, seconds):
        self.slept.append(seconds)

    def __init__(self):
        self.slept = []


class _FakeSMTP:
    """Records constructions; can be told to fail transiently or on auth."""
    transient_failures = 0     # constructions that raise a transient error
    auth_failures = 0          # logins that raise an auth error
    constructions = 0
    sent_to = []

    def __init__(self, host, port, timeout=None):
        type(self).constructions += 1
        if type(self).transient_failures > 0:
            type(self).transient_failures -= 1
            raise smtplib.SMTPException("421 4.7.0 Try again later (transient)")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        pass

    def starttls(self):
        pass

    def login(self, user, password):
        if type(self).auth_failures > 0:
            raise smtplib.SMTPAuthenticationError(535, b"535-5.7.8 Username and Password not accepted")

    def sendmail(self, sender, recipients, msg):
        type(self).sent_to.extend(recipients)


class EmailRetryTests(unittest.TestCase):
    def setUp(self):
        self._real_smtp = email_service.smtplib.SMTP
        self._real_time = email_service.time
        self._real_user = settings.MAIL_USERNAME
        self._real_pass = settings.MAIL_PASSWORD
        email_service.smtplib.SMTP = _FakeSMTP
        email_service.time = _NoSleepTime()
        settings.MAIL_USERNAME = "test@example.com"
        settings.MAIL_PASSWORD = "dummy-app-password"
        _FakeSMTP.transient_failures = 0
        _FakeSMTP.auth_failures = 0
        _FakeSMTP.constructions = 0
        _FakeSMTP.sent_to = []

    def tearDown(self):
        email_service.smtplib.SMTP = self._real_smtp
        email_service.time = self._real_time
        settings.MAIL_USERNAME = self._real_user
        settings.MAIL_PASSWORD = self._real_pass

    def test_transient_failure_is_retried_until_success(self):
        # Two transient blips then success => exactly 3 connections, email sent once.
        _FakeSMTP.transient_failures = 2
        send_otp_email("student@college.edu", "alice", "123456")
        self.assertEqual(_FakeSMTP.constructions, 3)
        self.assertEqual(_FakeSMTP.sent_to, ["student@college.edu"])

    def test_permanent_failure_raises_after_all_retries(self):
        # Every attempt transiently fails => retries exhausted, error raised,
        # and nothing was ever delivered.
        _FakeSMTP.transient_failures = 99
        with self.assertRaises(EmailDeliveryError):
            send_otp_email("student@college.edu", "alice", "123456")
        self.assertEqual(_FakeSMTP.constructions, email_service._SMTP_MAX_ATTEMPTS)
        self.assertEqual(_FakeSMTP.sent_to, [])

    def test_auth_failure_is_not_retried(self):
        # Bad credentials are permanent: one connection only, clear error.
        _FakeSMTP.auth_failures = 99
        with self.assertRaises(EmailDeliveryError) as ctx:
            send_otp_email("student@college.edu", "alice", "123456")
        self.assertEqual(_FakeSMTP.constructions, 1)
        self.assertIn("authentication", str(ctx.exception).lower())
        self.assertEqual(_FakeSMTP.sent_to, [])

    def test_dev_mode_without_credentials_never_touches_smtp(self):
        settings.MAIL_USERNAME = "   "
        settings.MAIL_PASSWORD = ""
        send_otp_email("student@college.edu", "alice", "123456")
        self.assertEqual(_FakeSMTP.constructions, 0)
        self.assertEqual(_FakeSMTP.sent_to, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
