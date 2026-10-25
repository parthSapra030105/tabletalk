"""
One-time database setup. Run it once, with a Postgres superuser.

Creates:
    tabletalk_app     - owns the database; used by Django and ingest (the only role that writes)
    tabletalk_reader  - used for every query the model writes. Locked down at the role level:
                        read-only transactions, a statement timeout, no access to the app's own
                        tables in `public`, no temp tables. Dataset schemas grant it SELECT one by one.
    tabletalk         - the database

Passwords are generated and written to .env, so they never pass through code or chat.
Safe to re-run: existing roles get new passwords and the settings are re-applied.

    python scripts/setup_db.py                      # prompts for the superuser password
    python scripts/setup_db.py --admin-user postgres --host localhost --port 5432
    python scripts/setup_db.py --host <hosted> --admin-user <owner> --admin-db <db> --env-file hosted.env
"""

import argparse
import getpass
import os
import secrets

import psycopg
from psycopg import sql

DB = "tabletalk"
APP = "tabletalk_app"
READER = "tabletalk_reader"
READER_STATEMENT_TIMEOUT = "10s"
ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")


def upsert_role(cur, name, password):
    exists = cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (name,)).fetchone()
    # Only a superuser may restate SUPERUSER, even as NOSUPERUSER, so a re-run just resets the password.
    attributes = "LOGIN" if exists else "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE"
    cur.execute(sql.SQL(("ALTER" if exists else "CREATE") + " ROLE {} " + attributes + " PASSWORD {}")
                .format(sql.Identifier(name), sql.Literal(password)))


def write_env(values, path=ENV_PATH):
    """Update only our keys in .env, keeping anything else already there."""
    lines = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = [l for l in f.read().splitlines() if l.split("=", 1)[0] not in values]
    lines += [f"{k}={v}" for k, v in values.items()]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", default="5432")
    parser.add_argument("--admin-user", default="postgres")
    parser.add_argument("--admin-db", default="postgres", help="an existing database to connect to first")
    parser.add_argument("--env-file", default=ENV_PATH, help="where to write the connection URLs")
    args = parser.parse_args()

    admin_password = os.environ.get("PGPASSWORD") or getpass.getpass(f"Password for Postgres user '{args.admin_user}': ")
    admin = dict(host=args.host, port=args.port, user=args.admin_user, password=admin_password)
    app_pw, reader_pw = secrets.token_urlsafe(24), secrets.token_urlsafe(24)

    with psycopg.connect(dbname=args.admin_db, autocommit=True, **admin) as conn:
        cur = conn.cursor()
        upsert_role(cur, APP, app_pw)
        upsert_role(cur, READER, reader_pw)
        # Wall #2 lives in the role itself, so no connection made as the reader can skip it.
        for setting, value in [("default_transaction_read_only", "on"),
                               ("statement_timeout", READER_STATEMENT_TIMEOUT),
                               ("idle_in_transaction_session_timeout", "30s")]:
            cur.execute(sql.SQL("ALTER ROLE {} SET {} = {}").format(sql.Identifier(READER), sql.Identifier(setting),
                                                                    sql.Literal(value)))
        cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 20").format(sql.Identifier(READER)))
        # A hosted Postgres admin isn't a superuser: it can only hand the database to the app
        # role, and then manage it as owner, if it is a member of that role.
        if not cur.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user").fetchone()[0]:
            cur.execute(sql.SQL("GRANT {} TO CURRENT_USER").format(sql.Identifier(APP)))
        if not cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB,)).fetchone():
            cur.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(DB), sql.Identifier(APP)))

    with psycopg.connect(dbname=DB, autocommit=True, **admin) as conn:
        cur = conn.cursor()
        # Nobody gets anything by default (this also removes TEMP, so the reader can't create temp tables).
        cur.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(DB)))
        cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(DB), sql.Identifier(READER)))
        cur.execute(sql.SQL("GRANT ALL ON DATABASE {} TO {}").format(sql.Identifier(DB), sql.Identifier(APP)))
        # `public` will hold Django's tables (threads, catalog). The reader must not see them.
        cur.execute(sql.SQL("ALTER SCHEMA public OWNER TO {}").format(sql.Identifier(APP)))
        cur.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")

    base = f"{args.host}:{args.port}/{DB}"
    write_env({"DATABASE_URL": f"postgresql://{APP}:{app_pw}@{base}",
               "READONLY_DATABASE_URL": f"postgresql://{READER}:{reader_pw}@{base}"}, args.env_file)
    print(f"Database '{DB}' ready. Roles '{APP}' and '{READER}' configured; connection URLs written to {args.env_file}")


if __name__ == "__main__":
    main()
