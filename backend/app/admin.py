import sys

from app.accounts import Accounts
from app.config import Settings
from app.db import Database
from app.mailer import Mailer


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] != "disable-2fa":
        print("Usage: python -m app.admin disable-2fa EMAIL")
        return 2
    settings = Settings()
    db = Database(settings.sessions_root() / "app.db")
    accounts = Accounts(db, settings, Mailer(settings))
    row = db.one("SELECT id FROM users WHERE email = ?", (argv[2].strip().lower(),))
    if row is None:
        print("No account found for that email.")
        return 1
    accounts.clear_two_factor(row["id"])
    db.run("DELETE FROM auth_tokens WHERE user_id = ?", (row["id"],))
    print("Two-factor sign-in was turned off and all sessions were signed out.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
