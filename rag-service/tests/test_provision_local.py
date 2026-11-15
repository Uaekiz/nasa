"""Opt-in native psql regression test using a private, disposable test cluster."""

import os
from pathlib import Path
import shutil
import socket
import subprocess
import unittest
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row


SERVICE_DIR = Path(__file__).resolve().parent.parent
BIN_DIR = os.getenv("RAG_PROVISION_TEST_BIN")


@unittest.skipUnless(BIN_DIR, "Set RAG_PROVISION_TEST_BIN for the isolated native psql provisioning regression.")
class NativeProvisioningRegression(unittest.TestCase):
    def test_mismatch_rolls_back_then_retry_and_existing_objects_are_preserved(self):
        binary = Path(BIN_DIR)
        local_root = (SERVICE_DIR / ".local" / "provision-tests").resolve()
        self.assertTrue(local_root.is_relative_to(SERVICE_DIR.resolve()))
        local_root.mkdir(parents=True, exist_ok=True)
        work = local_root / uuid4().hex
        work.mkdir()
        data = work / "data"
        log = work / "server.log"
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        environment = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
        # psql's documented MSYS branch reads test-only password input from stdin.
        environment["OSTYPE"] = "msys"
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        started = False

        def command(name, *arguments, text_input=None, timeout=60):
            # Background postgres children can inherit stdio handles. Files keep
            # pg_ctl completion independent of pipe EOF from the running server.
            stdout_path = work / (uuid4().hex + ".stdout")
            stderr_path = work / (uuid4().hex + ".stderr")
            with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                result = subprocess.run(
                    [str(binary / name), *map(str, arguments)], input=text_input,
                    stdout=stdout, stderr=stderr,
                    text=True, encoding="utf-8", errors="replace", timeout=timeout,
                    env=environment, cwd=work, creationflags=creationflags,
                )
            return subprocess.CompletedProcess(
                result.args, result.returncode,
                stdout_path.read_text(encoding="utf-8", errors="replace"),
                stderr_path.read_text(encoding="utf-8", errors="replace"),
            )

        def connect(database="postgres"):
            return psycopg.connect(
                host="127.0.0.1", port=port, user="rag_regression_admin", dbname=database,
                autocommit=True, row_factory=dict_row, connect_timeout=5,
            )

        def run_script(path, text_input=""):
            return command(
                "psql.exe", "-X", "-w", "-h", "127.0.0.1", "-p", port,
                "-U", "rag_regression_admin", "-d", "postgres",
                "-v", "AUTOCOMMIT=off", "-v", "rag_new_password_set=true",
                "-f", path, text_input=text_input,
            )

        try:
            initialized = command("initdb.exe", "-D", data, "-A", "trust", "-U", "rag_regression_admin", "--no-sync", "-E", "UTF8", "--locale=C")
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            running = command("pg_ctl.exe", "-D", data, "-l", log, "-o", f"-h 127.0.0.1 -p {port} -F", "-w", "start")
            started = (data / "postmaster.pid").is_file()
            self.assertEqual(running.returncode, 0, running.stderr)
            # Verify the private data directory before running any provisioning SQL.
            with connect() as connection:
                actual = connection.execute("SHOW data_directory").fetchone()["data_directory"]
                self.assertEqual(Path(actual).resolve(), data.resolve())

            script = SERVICE_DIR / "scripts" / "provision_local.sql"
            failed = run_script(script, "synthetic-first-entry\nsynthetic-different-entry\n")
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("New role creation was rolled back", failed.stderr)
            self.assertIn("ROLLBACK", failed.stdout)
            self.assertNotIn("there is no transaction in progress", failed.stderr)
            with connect() as connection:
                self.assertFalse(connection.execute(
                    "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='pyrosphere_rag_app') AS found"
                ).fetchone()["found"])
                self.assertFalse(connection.execute(
                    "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname='pyrosphere_rag') AS found"
                ).fetchone()["found"])

            password = "synthetic-private-regression-password"
            succeeded = run_script(script, password + "\n" + password + "\n")
            self.assertEqual(succeeded.returncode, 0, succeeded.stderr)
            self.assertNotIn("cannot run inside a transaction", succeeded.stderr)
            self.assertNotIn(password, succeeded.stdout + succeeded.stderr)
            with connect() as connection:
                role_before = connection.execute(
                    "SELECT oid, rolpassword FROM pg_authid WHERE rolname='pyrosphere_rag_app'"
                ).fetchone()
                database_before = connection.execute(
                    "SELECT oid FROM pg_database WHERE datname='pyrosphere_rag'"
                ).fetchone()["oid"]
                self.assertTrue(bool(role_before["rolpassword"]))
            with connect("pyrosphere_rag") as connection:
                schema = connection.execute(
                    "SELECT pg_get_userbyid(nspowner) AS owner FROM pg_namespace WHERE nspname='rag'"
                ).fetchone()
                self.assertEqual(schema["owner"], "pyrosphere_rag_app")
                connection.execute("CREATE TABLE rag.regression_sentinel (value integer)")
                connection.execute("INSERT INTO rag.regression_sentinel VALUES (42)")

            rerun = run_script(script)
            self.assertEqual(rerun.returncode, 0, rerun.stderr)
            self.assertIn("password and attributes will not be changed", rerun.stdout)
            with connect() as connection:
                role_after = connection.execute(
                    "SELECT oid, rolpassword FROM pg_authid WHERE rolname='pyrosphere_rag_app'"
                ).fetchone()
                self.assertTrue(role_before == role_after)
                self.assertEqual(connection.execute(
                    "SELECT oid FROM pg_database WHERE datname='pyrosphere_rag'"
                ).fetchone()["oid"], database_before)
            with connect("pyrosphere_rag") as connection:
                self.assertEqual(connection.execute("SELECT value FROM rag.regression_sentinel").fetchone()["value"], 42)
            inspected = run_script(SERVICE_DIR / "scripts" / "inspect_local.sql")
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            self.assertIn("regression_sentinel", inspected.stdout)
            self.assertNotIn(password, inspected.stdout + inspected.stderr)
        finally:
            # Stop and remove only the private directory created by this test.
            self.assertTrue(work.resolve().is_relative_to(local_root))
            if started:
                stopped = command("pg_ctl.exe", "-D", data, "-m", "fast", "-w", "stop")
                self.assertEqual(stopped.returncode, 0, stopped.stderr)
            shutil.rmtree(work)
