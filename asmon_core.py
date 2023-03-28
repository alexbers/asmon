# the core of asmon
import asyncio
import time
import traceback
import random
import os
import re
import gc
import functools
import importlib.util
from collections import defaultdict, Counter
from contextvars import ContextVar

prefix_ctx = ContextVar("prefix", default="")
file_name_ctx = ContextVar("file_name", default="")
alerts_repeat_after_ctx = ContextVar("alerts_repeat_after", default=float("inf"))

filename_to_tasks = defaultdict(list)
prefix_to_checks_cnt = Counter()

from config import CHECK_PAUSE
from asmon_alerts import precheck_hook, postcheck_hook, alert_sender_loop, log, alert, alert_stats_loop
from asmon_metrics import start_metrics_srv, exceptions_cnt, prefix_to_str


SCRIPT_PATH = os.path.dirname(os.path.realpath(__file__))

next_allowed_run = defaultdict(int)

async def throttle_runs(key, pps):
    global next_allowed_run

    if pps == 0:
        return
    next_time = 1.0 / pps

    cur_time = time.time()

    wait_time = next_allowed_run[key] - cur_time
    if wait_time < 0:
        next_allowed_run[key] = cur_time + next_time
        return

    next_allowed_run[key] += next_time
    await asyncio.sleep(wait_time)



async def run_checkloop(check_func, args, pause, alert_prefix=(),
                        alerts_repeat_after=float("inf"), max_starts_per_sec=0,
                        timeout=float("inf")):
    prefix_ctx.set(alert_prefix)
    alerts_repeat_after_ctx.set(alerts_repeat_after)

    try:
        pause_min, pause_max = pause
    except TypeError:
        pause_min, pause_max = pause, pause

    await throttle_runs("start_check", 25)

    throttler_key = tuple(alert_prefix[:2])  # file and func

    while True:
        try:
            await throttle_runs(throttler_key, max_starts_per_sec)

            precheck_hook(args_str=str(args))
            await asyncio.wait_for(check_func(*args), timeout=timeout)
            postcheck_hook()
        except Exception as e:
            traceback.print_exception(e)

            e_name = type(e).__name__
            filename, funcname, parameter = alert_prefix
            if e_name == "Exception":
                if not str(e):
                    # skip alerts about Exception(), this is a special exception
                    continue
                e_name = ""

            msg = f"проверка упала с ошибкой {e_name} {str(e)}:{filename}, функция {funcname}"
            if isinstance(e, TimeoutError):
                msg = f"таймаут {filename}:{funcname}"

            if parameter is not None:
                msg += f"({parameter})"

            alert(msg, "__exception__")

            exceptions_cnt[prefix_to_str(alert_prefix)] += 1
        finally:
            prefix_to_checks_cnt[alert_prefix] += 1

            cur_pause = pause_min + random.random() * (pause_max-pause_min)
            await asyncio.sleep(cur_pause)


def reg_checker(checker, subj=None, pause=CHECK_PAUSE,
                alerts_repeat_after=float("inf"), max_starts_per_sec=0,
                timeout=float("inf")):
    if subj is None:
        args = []
    else:
        args = [subj]

    filename = file_name_ctx.get()

    alert_prefix = (filename, checker.__name__, subj)

    checkloop = run_checkloop(checker, args, pause, alert_prefix=alert_prefix,
                              alerts_repeat_after=alerts_repeat_after,
                              max_starts_per_sec=max_starts_per_sec,timeout=timeout)

    task = asyncio.create_task(checkloop)

    filename_to_tasks[filename].append(task)


def checker(f=None, *, args=[], pause=CHECK_PAUSE,
            alerts_repeat_after=float("inf"), max_starts_per_sec=0,
            timeout=float("inf")):
    if not file_name_ctx.get():
        # if script runs directly, do nothing
        return f if f else lambda f: f

    kwargs = {
        "pause": pause,
        "alerts_repeat_after": alerts_repeat_after,
        "max_starts_per_sec": max_starts_per_sec,
        "timeout": timeout
    }

    if f:
        reg_checker(f, **kwargs)
        return f

    def decorator(f):
        if not args:
            reg_checker(f, **kwargs)
        else:
            for arg in args:
                reg_checker(f, subj=arg, **kwargs)
        return f

    return decorator


def reset_checks_cnt(filename):
    for prefix, checks_cnt in prefix_to_checks_cnt.items():
        if prefix[0] == filename:
            prefix_to_checks_cnt[prefix] = 0


async def reg_checker_module(filename, full_filename):
    file_name_ctx.set(filename)
    reset_checks_cnt(filename)
    prefix_ctx.set((filename, "__loading__", None))

    try:
        spec = importlib.util.spec_from_file_location(filename, full_filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as E:
        traceback.print_exc()
        alert(f"Failed to load {filename}: {str(E)}")


def cancel_task(filename):
    for task in filename_to_tasks[filename]:
        task.cancel()

    filename_to_tasks.pop(filename, None)
    gc.collect()


async def run(directory=SCRIPT_PATH):
    file_name_ctx.set("asmon.py")
    prefix_ctx.set(("asmon.py", "core", None))

    alert_sender = asyncio.create_task(alert_sender_loop())
    stat_printer = asyncio.create_task(alert_stats_loop())
    metrics_handler = asyncio.create_task(start_metrics_srv())

    filename_to_mod_time = {}

    PAUSE_RESCANS = 5

    iter_num = 0
    while True:
        iter_num += 1
        checker_filenames = [f for f in os.listdir(directory) if re.fullmatch(r"check_\S+\.py", f)]
        for filename in checker_filenames:
            try:
                full_filename = os.path.join(directory, filename)

                mod_time = os.path.getmtime(full_filename)
                prev_mod_time = filename_to_mod_time.get(filename, -1)

                if mod_time != prev_mod_time:
                    if prev_mod_time == -1:
                        log("file", filename, "found, loading")
                    else:
                        log("file", filename, "changed, reloading")

                    cancel_task(filename)
                    filename_to_mod_time.pop(filename, None)

                    module = await asyncio.create_task(reg_checker_module(filename, full_filename))
                    filename_to_mod_time[filename] = mod_time
            except Exception:
                log(f"failed to load {filename}")
                traceback.print_exc()
                exceptions_cnt["core"] += 1

        for filename in set(filename_to_tasks) - set(checker_filenames):
            try:
                log("file", filename, "deleted, unloading")
                cancel_task(filename)
                filename_to_mod_time.pop(filename, None)
            except Exception:
                log(f"failed to unload {filename}")
                traceback.print_exc()
                exceptions_cnt["core"] += 1

        await asyncio.sleep(PAUSE_RESCANS)

