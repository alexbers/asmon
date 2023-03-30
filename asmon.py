import asyncio
import resource
import os
import time

from config import TIMEZONE
from asmon.core import run
from asmon.alerts import log

SCRIPT_PATH = os.path.dirname(os.path.realpath(__file__))


def setup_files_limit():
    try:
        soft_fd_limit, hard_fd_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
        resource.setrlimit(resource.RLIMIT_NOFILE, (hard_fd_limit, hard_fd_limit))
    except (ValueError, OSError):
        log("Failed to increase the limit of opened files")


def init(timezone=TIMEZONE):
    setup_files_limit()
    os.environ['TZ'] = timezone
    time.tzset()


if __name__ == "__main__":
    init()
    asyncio.run(run(directory=SCRIPT_PATH))
