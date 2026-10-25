import unittest

from monitoring_api.control_db import ControlDatabase
from monitoring_api.repositories.auth import AuthRepository


class AuthRepositoryTests(unittest.TestCase):
    def test_lookup_uses_parameter_and_does_not_return_password_in_repr(self):
        calls = []

        class Cursor:
            def execute(self, sql, parameters):
                calls.append((sql, parameters))

            def fetchone(self):
                return ("id", "admin", "$argon2id$secret", "admin", True)

            def close(self):
                calls.append("cursor_closed")

        class Connection:
            def cursor(self):
                return Cursor()

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                pass

        db = ControlDatabase("Server=control", connector=lambda *a, **kw: Connection())
        user = AuthRepository(db).find_user(" ADMIN'-- ")
        self.assertNotIn("ADMIN", calls[0][0])
        self.assertEqual(calls[0][1], ("admin'--",))
        self.assertEqual(calls[1], "cursor_closed")
        self.assertEqual(user.password_hash, "$argon2id$secret")
        self.assertNotIn("secret", repr(user))
