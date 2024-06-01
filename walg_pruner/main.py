import logging
import os
import subprocess
import time
import signal
import click
import psycopg2
from psycopg2.extras import DictCursor

terminate = False


def signal_handler(sig, frame):
    global terminate
    logging.info("SIGTERM received, preparing to shut down...")
    terminate = True


def read_envdir(envdir_path):
    env_vars = {}
    for filename in os.listdir(envdir_path):
        filepath = os.path.join(envdir_path, filename)
        if os.path.isfile(filepath):
            with open(filepath) as f:
                env_vars[filename] = f.read().strip()
    return env_vars


def set_env_vars(env_vars):
    for key, value in env_vars.items():
        os.environ[key] = value
        logging.debug(f"Set environment variable {key}={value}")


def is_primary_database(
    pg_host, pg_port, pg_user, pg_password, pg_database, pg_ssl_mode
):
    try:
        with psycopg2.connect(
            host=pg_host,
            port=pg_port,
            user=pg_user,
            password=pg_password,
            dbname=pg_database,
            sslmode=pg_ssl_mode,
        ) as db_connection:
            db_connection.autocommit = True
            with db_connection.cursor() as pg_cursor:
                pg_cursor.execute("SELECT NOT pg_is_in_recovery()")
                pg_is_primary = pg_cursor.fetchone()
                return pg_is_primary and pg_is_primary[0]
    except Exception as e:
        logging.error("Error checking database primary status: %s", str(e))
        return False


@click.command()
@click.option(
    "--interval",
    default=86400,
    help="Interval in seconds between prunes",
    envvar="PRUNE_INTERVAL",
)
@click.option(
    "--retain",
    required=True,
    help="Number of full backups to retain",
    default=2,
    envvar="RETAIN_COUNT",
)
@click.option(
    "--after",
    default=None,
    help="Timestamp or name after which backups should be retained",
    envvar="AFTER_TIMESTAMP",
)
@click.option(
    "--envdir",
    default="/run/etc/wal-e.d/env",
    help="Directory containing environment variable files",
    envvar="ENVDIR",
)
@click.option(
    "--log-level",
    default="INFO",
    help="Log level for the application",
    envvar="LOG_LEVEL",
)
@click.option(
    "--pg-host",
    default="localhost",
    help="PostgreSQL host",
    envvar="PGHOST",
)
@click.option(
    "--pg-port",
    default="5432",
    help="PostgreSQL port",
    envvar="PGPORT",
)
@click.option(
    "--pg-user",
    default="postgres",
    help="PostgreSQL user",
    envvar="PGUSER",
)
@click.option(
    "--pg-database",
    default="postgres",
    help="PostgreSQL database",
    envvar="PGDATABASE",
)
@click.option(
    "--pg-password",
    help="PostgreSQL password",
    envvar="PGPASSWORD",
)
@click.option(
    "--pg-sslmode",
    default="require",
    help="PostgreSQL SSL mode",
    envvar="PGSSLMODE",
)
def prune_walg_backups(
    interval,
    retain,
    after,
    envdir,
    log_level,
    pg_host,
    pg_port,
    pg_user,
    pg_database,
    pg_password,
    pg_sslmode,  # Change here to match the command-line option
):
    # Set up logging
    log_level = log_level.upper()
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=getattr(logging, log_level),
    )

    signal.signal(signal.SIGTERM, signal_handler)

    # wait for the database to be ready
    logging.info("Waiting for the database to be ready...")
    attempt = 0
    max_info_attempts = 5
    max_warn_attempts = 10

    while True:
        try:
            with psycopg2.connect(
                host=pg_host,
                port=pg_port,
                user=pg_user,
                password=pg_password,
                dbname=pg_database,
                sslmode=pg_sslmode,
            ) as db_connection:
                db_connection.autocommit = True
                with db_connection.cursor(cursor_factory=DictCursor) as pg_cursor:
                    pg_cursor.execute("SELECT 1")
                    break
        except psycopg2.OperationalError as e:
            attempt += 1
            if attempt <= max_info_attempts:
                logging.info("Database not ready: %s", str(e))
            elif attempt <= max_warn_attempts:
                logging.warning("Database not ready: %s", str(e))
            else:
                logging.error("Database not ready: %s", str(e))
            time.sleep(30)

    # Set environment variables from envdir if provided
    logging.info(f"Reading environment variables from {envdir}")
    env_vars = read_envdir(envdir)
    set_env_vars(env_vars)

    logging.debug(f"Using interval: {interval}")
    logging.debug(f"Retain count: {retain}")
    logging.debug(f"After timestamp: {after}")

    while not terminate:
        if is_primary_database(
            pg_host,
            pg_port,
            pg_user,
            pg_password,
            pg_database,
            pg_sslmode,  # Change here to match the function parameter
        ):
            try:
                # Construct the wal-g delete command
                delete_command = ["wal-g", "delete", "retain", "FULL", str(retain)]
                if after:
                    delete_command.extend(["--after", after])
                delete_command.append("--confirm")

                logging.info("Running command: %s", " ".join(delete_command))

                # Retry logic for transient errors
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        # Execute the wal-g delete command
                        logging.debug(f"Attempt {attempt + 1} of {max_retries}")
                        res = subprocess.run(
                            delete_command, capture_output=True, check=True
                        )
                        # Log the output
                        logging.info("Command output: %s", res.stdout.decode("utf-8"))
                        logging.info("Successfully pruned WAL-G backups")
                        break
                    except subprocess.CalledProcessError as e:
                        logging.warning(
                            "Error occurred while pruning WAL-G backups: %s", str(e)
                        )
                        if attempt < max_retries - 1:
                            logging.warning("Retrying in 10 seconds...")
                            time.sleep(10)
                        else:
                            logging.error("Max retries reached, skipping this cycle.")

            except Exception as e:
                logging.error("Unexpected error: %s", str(e))
        else:
            logging.info(
                "Not the primary database or in recovery mode. Skipping prune operation."
            )

        logging.info("Waiting for next prune cycle...")
        time.sleep(interval)


if __name__ == "__main__":
    prune_walg_backups()
