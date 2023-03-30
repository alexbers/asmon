# common funcions and context variables are here
import time
import sys
from contextvars import ContextVar
from collections import defaultdict, Counter

# used by alerts and metrics
prefix_to_id_to_alert = defaultdict(dict)

# mapping from filename to tasks list, used by core and metrics
filename_to_tasks = defaultdict(list)

# prefix to checks counter, used by core and metrics
prefix_to_checks_cnt = Counter()

# prefix is a (file_name, function_name, arg)
prefix_ctx = ContextVar("prefix", default="")

# just a file_name
file_name_ctx = ContextVar("file_name", default="")

# the setable value of when alert reminders should be sent
alerts_repeat_after_ctx = ContextVar("alerts_repeat_after", default=float("inf"))


def prefix_to_str(prefix):
    if len(prefix) == 3 and not prefix[2]:
        return f"{prefix[0]}:{prefix[1]}"
    return f"{prefix[0]}:{prefix[1]}:{prefix[2]}"


def log(*args, **kwargs):
    cur_time = time.strftime("%Y-%m-%d %H:%M:%S")
    print(cur_time, *args, **kwargs, file=sys.stderr, flush=True)
