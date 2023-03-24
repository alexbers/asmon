import asyncio
import resource
import os
import time

from asmon_core import run, checker
from asmon_alerts import alert, log


def setup_files_limit():
    try:
        soft_fd_limit, hard_fd_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
        resource.setrlimit(resource.RLIMIT_NOFILE, (hard_fd_limit, hard_fd_limit))
    except (ValueError, OSError):
        log("Failed to increase the limit of opened files")


def init(timezone='Asia/Yekaterinburg'):
    setup_files_limit()
    os.environ['TZ'] = timezone
    time.tzset()


if __name__ == "__main__":
    init()
    asyncio.run(run())
