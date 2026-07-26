"""Admin CLI — create or reset a user without touching the running server.

Operates directly on the persisted user store (config.STATE_DIR/users.json),
so it works wherever that volume is reachable: a Render Shell session against
the live deployment, or locally against a dev database.

The first-run partner account is only ever created once, at the moment the
user store is empty — set ADMIN_EMAIL/ADMIN_PASSWORD before that boot, or you
get a generated password that is only visible in the deploy log. This CLI is
the escape hatch when that moment has already passed: create a new partner
account, or reset an existing one, on demand.

    python -m backend.cli create-admin --email you@firm.in --password ...
    python -m backend.cli reset-password --email you@firm.in --password ...
    python -m backend.cli list-users
"""

import argparse
import getpass
import sys

from . import config, users


def _read_password(explicit: str = "") -> str:
    if explicit:
        return explicit
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords did not match.", file=sys.stderr)
        sys.exit(1)
    return password


def cmd_create_admin(args) -> int:
    password = _read_password(args.password)
    try:
        user = users.create_user(
            args.email, password, name=args.name or "", role=args.role
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"Created {user['role']} account: {user['email']}")
    if user.get("name"):
        print(f"  Name: {user['name']}")
    return 0


def cmd_reset_password(args) -> int:
    record = users.find_by_email(args.email)
    if record is None:
        print(f"Error: no user with email {args.email!r}. "
              f"Use create-admin to create one.", file=sys.stderr)
        return 1

    password = _read_password(args.password)
    try:
        users.update_user(record["id"], password=password)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"Password reset for {args.email}.")
    return 0


def cmd_list_users(args) -> int:
    all_users = users.list_users()
    if not all_users:
        print("No users. Run create-admin to create the first partner account.")
        return 0

    width = max(len(u["email"]) for u in all_users)
    for user in all_users:
        status = "active" if user["active"] else "disabled"
        last = user["last_login"] or "never signed in"
        print(f"{user['email']:<{width}}  {user['role']:<8}  {status:<9}  {last}")
    return 0


def cmd_set_role(args) -> int:
    record = users.find_by_email(args.email)
    if record is None:
        print(f"Error: no user with email {args.email!r}.", file=sys.stderr)
        return 1
    try:
        user = users.update_user(record["id"], role=args.role)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(f"{user['email']} is now {user['role']}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m backend.cli",
        description="Create or reset users directly against the persisted store.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser(
        "create-admin", help="Create a new user (a partner account, by default)"
    )
    create.add_argument("--email", required=True)
    create.add_argument("--password", default="",
                        help="Omit to be prompted (recommended over the shell history)")
    create.add_argument("--name", default="")
    create.add_argument("--role", default="partner",
                        choices=["partner", "manager", "staff"])
    create.set_defaults(func=cmd_create_admin)

    reset = subparsers.add_parser(
        "reset-password", help="Reset an existing user's password"
    )
    reset.add_argument("--email", required=True)
    reset.add_argument("--password", default="")
    reset.set_defaults(func=cmd_reset_password)

    role = subparsers.add_parser("set-role", help="Change an existing user's role")
    role.add_argument("--email", required=True)
    role.add_argument("--role", required=True,
                      choices=["partner", "manager", "staff"])
    role.set_defaults(func=cmd_set_role)

    listing = subparsers.add_parser("list-users", help="List all users")
    listing.set_defaults(func=cmd_list_users)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    print(f"Operating on user store at: {config.STATE_DIR}")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
