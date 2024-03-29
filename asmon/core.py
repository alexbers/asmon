# the core of asmon
import asyncio
import time
import traceback
import os
import re
import gc
import importlib.util
from collections import defaultdict
from contextvars import ContextVar

from .commons import (log, prefix_to_str, prefix_ctx, file_name_ctx,
                      renotify_ctx, if_in_a_row_ctx, filename_to_tasks,
                      prefix_to_checks_cnt)
from .alerts import (alert, alerts_precheck_hook, alerts_postcheck_hook, load_alerts,
                     alert_sender_loop, alert_stats_loop, alert_save_loop, recover_alerts,
                     try_reload_send_alerts, send_alert_reloader_loop)
from .metrics import (metrics_precheck_hook, metrics_postcheck_hook, exceptions_cnt,
                      start_metrics_srv)

next_allowed_run = defaultdict(int)

reload_survivers = {}

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



async def run_checkloop(check_func, args, pause, alert_prefix,
                        renotify, max_starts_per_sec,
                        timeout, if_in_a_row):
    prefix_ctx.set(alert_prefix)
    renotify_ctx.set(renotify)
    if_in_a_row_ctx.set(if_in_a_row)

    await throttle_runs("start_check", 25)

    throttler_key = tuple(alert_prefix[:2])  # file and func

    while True:
        try:
            await throttle_runs(throttler_key, max_starts_per_sec)

            alerts_precheck_hook(args_str=str(args))
            metrics_precheck_hook(args_str=str(args))
            await asyncio.wait_for(check_func(*args), timeout=timeout)
            metrics_postcheck_hook()
            alerts_postcheck_hook()
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

            await asyncio.sleep(pause)


def reg_checker(checker, subj, pause, renotify, max_starts_per_sec, timeout, if_in_a_row):
    if subj is None:
        args = []
    else:
        args = [subj]

    filename = file_name_ctx.get()

    alert_prefix = (filename, checker.__name__, subj)
    prefix_to_checks_cnt[alert_prefix] = 0

    checkloop = run_checkloop(checker, args, pause, alert_prefix=alert_prefix,
                              renotify=renotify,
                              max_starts_per_sec=max_starts_per_sec,
                              timeout=timeout, if_in_a_row=if_in_a_row)

    task = asyncio.create_task(checkloop)

    filename_to_tasks[filename].append(task)


def checker(*, pause, timeout=None, args=[], renotify=float("inf"),
            max_starts_per_sec=0, if_in_a_row=1):
    if not file_name_ctx.get():
        # if script runs directly, execute immidiately
        def new_f(f):
            if not args:
                print(f"Dry running {f.__name__}():")
                asyncio.run(f())
            else:
                async def dry_runner():
                    for arg in args:
                        print(f"Dry running {f.__name__}({arg!r}):")
                        await f(arg)

                asyncio.run(dry_runner())
        return new_f

    kwargs = {
        "pause": pause,
        "renotify": renotify,
        "max_starts_per_sec": max_starts_per_sec,
        "timeout": timeout,
        "if_in_a_row": if_in_a_row
    }

    def decorator(f):
        if not args:
            reg_checker(f, subj=None, **kwargs)
        else:
            for arg in args:
                reg_checker(f, subj=arg, **kwargs)
        return f

    return decorator


def reset_checks_cnt(filename):
    global prefix_to_checks_cnt
    for p in list(prefix_to_checks_cnt):
        if p[0] == filename:
            del prefix_to_checks_cnt[p]


async def reg_checker_module(filename, full_filename):
    global prefix_to_checks_cnt

    file_name_ctx.set(filename)
    reset_checks_cnt(filename)
    prefix_ctx.set((filename, "__loading__", None))

    try:
        spec = importlib.util.spec_from_file_location(filename, full_filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        recover_alerts(filename, unregistered_only=True)
        return module
    except Exception as E:
        traceback.print_exc()
        alert(f"Failed to load {filename}: {str(E)}")


def cancel_task(filename):
    for task in filename_to_tasks[filename]:
        task.cancel()

    filename_to_tasks.pop(filename, None)
    gc.collect()

class SurviveReloadsVar:
    def __init__(self, name, obj):
        global reload_survivers
        self.k = (file_name_ctx.get(), name)

        if self.k not in reload_survivers:
            reload_survivers[self.k] = obj

    def get(self):
        global reload_survivers
        return reload_survivers.get(self.k)


    def set(self, obj):
        global reload_survivers
        reload_survivers[self.k] = obj

def clean_survivers(filename):
    global reload_survivers
    for f, obj in list(reload_survivers):
        if f == filename and (f, obj) in reload_survivers:
            del reload_survivers[(f, obj)]


async def run(directory="."):
    file_name_ctx.set("asmon.py")
    prefix_ctx.set(("asmon.py", "core", None))
    
    load_alerts()

    try:
        try_reload_send_alerts(directory)
    except Exception:
        log("Failed to load send_alerts function from send_alerts.py, exiting")
        traceback.print_exc()
        exit(1)

    alert_sender = asyncio.create_task(alert_sender_loop())
    alert_reloader = asyncio.create_task(send_alert_reloader_loop(directory))
    stat_printer = asyncio.create_task(alert_stats_loop())
    alert_saver = asyncio.create_task(alert_save_loop())
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
                recover_alerts(filename)
                clean_survivers(filename)
                filename_to_mod_time.pop(filename, None)
            except Exception:
                log(f"failed to unload {filename}")
                traceback.print_exc()
                exceptions_cnt["core"] += 1

        await asyncio.sleep(PAUSE_RESCANS)

