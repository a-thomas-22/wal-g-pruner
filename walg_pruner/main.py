import logging
import os
import subprocess
import time
import signal
import click


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


@click.command()
@click.option(
    "--interval",
    default=3600,
    help="Interval in seconds between prunes",
    envvar="PRUNE_INTERVAL",
)
@click.option(
    "--retain",
    required=True,
    help="Number of full backups to retain",
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
def prune_walg_backups(interval, retain, after, envdir, log_level):
    # Set up logging
    log_level = log_level.upper()
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=getattr(logging, log_level),
    )

    signal.signal(signal.SIGTERM, signal_handler)

    # Set environment variables from envdir if provided
    logging.info(f"Reading environment variables from {envdir}")
    env_vars = read_envdir(envdir)
    set_env_vars(env_vars)

    logging.debug(f"Using interval: {interval}")
    logging.debug(f"Retain count: {retain}")
    logging.debug(f"After timestamp: {after}")

    while not terminate:
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
                    logging.warn(
                        "Error occurred while pruning WAL-G backups: %s", str(e)
                    )
                    if attempt < max_retries - 1:
                        logging.warning("Retrying in 10 seconds...")
                        time.sleep(10)
                    else:
                        logging.error("Max retries reached, skipping this cycle.")

        except Exception as e:
            logging.error("Unexpected error: %s", str(e))

        logging.info("Waiting for next prune cycle...")
        time.sleep(interval)


if __name__ == "__main__":
    prune_walg_backups()
