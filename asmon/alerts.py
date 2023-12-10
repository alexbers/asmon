import asyncio
import contextvars
import time
import traceback
import sys
import os
import json
import importlib
import gc
from dataclasses import dataclass, asdict

from .commons import (log, prefix_to_id_to_alert, prefix_to_str, prefix_ctx,
                      file_name_ctx, renotify_ctx, if_in_a_row_ctx,
                      prefix_to_checks_cnt)
from . import metrics


SEND_ALERTS_FILENAME = "send_alerts.py"

fired_alerts_ctx = contextvars.ContextVar("fired_alerts", default=set())

send_alerts = None  # dynamicaly loaded
send_alerts_mod_time = 0

@dataclass
class Alert:
    filename: str
    funcname: str
    funcarg: object
    alert_id: str
    text: str
    start_time: float
    last_update_time: float
    last_send_time: float
    renotify: float
    in_a_row: int
    notify_if_in_a_row: int
    recovered: bool

    @property
    def prefix(self):
        return (self.filename, self.funcname, self.funcarg)


def alerts_precheck_hook(args_str):
    fired_alerts_ctx.set(set())


def alerts_postcheck_hook():
    active = [a for a in prefix_to_id_to_alert[prefix_ctx.get()].values()]

    # if alert not fired during the check, recover it
    for alert in active:
        if alert.alert_id not in fired_alerts_ctx.get():
            alert.last_update_time = time.time()
            alert.recovered = True

            # if alert flaps, remove it
            if alert.in_a_row < alert.notify_if_in_a_row:
                delete_alert(alert)


def recover_alerts(filename, unregistered_only=False):
    global prefix_to_checks_cnt

    for id_to_alert in prefix_to_id_to_alert.values():
        for alert in id_to_alert.values():
            if alert.filename != filename:
                continue

            if alert.prefix not in prefix_to_checks_cnt or not unregistered_only:
                alert.last_update_time = time.time()
                alert.recovered = True


def alert(text, alert_id="default", renotify=None, if_in_a_row=None):
    if not file_name_ctx.get():
        # if script runs directly, do nothing
        log(text)
        return

    if if_in_a_row is None:
        if_in_a_row = if_in_a_row_ctx.get()

    alert_id = str(alert_id)
    fired_alerts_ctx.get().add(alert_id)

    if renotify is None:
        renotify = renotify_ctx.get()

    prefix = prefix_ctx.get()
    id_to_alert = prefix_to_id_to_alert[prefix]
    filename, funcname, funcarg = prefix

    if alert_id not in id_to_alert:
        id_to_alert[alert_id] = Alert(alert_id=alert_id, text=text, filename=filename,
                                      funcname=funcname, funcarg=funcarg,
                                      start_time=time.time(),
                                      last_update_time=time.time(), last_send_time=0,
                                      renotify=renotify, in_a_row=1,
                                      notify_if_in_a_row=if_in_a_row,
                                      recovered=False)
    else:
        id_to_alert[alert_id].text = text
        id_to_alert[alert_id].last_update_time = time.time()
        id_to_alert[alert_id].renotify = renotify
        id_to_alert[alert_id].in_a_row += 1
        id_to_alert[alert_id].notify_if_in_a_row = if_in_a_row
        id_to_alert[alert_id].recovered = False


def get_sendable_alerts():
    sendable_alerts = []

    cur_time = time.time()
    for id_to_alert in prefix_to_id_to_alert.values():
        for a in id_to_alert.values():
            if not a.recovered and not prefix_to_checks_cnt[a.prefix] and a.prefix[1] != "__loading__":
                # there was no checks after reloading
                continue

            if a.last_update_time < a.last_send_time:
                # the alert is not updated since the last report
                continue

            if not a.recovered and a.in_a_row < a.notify_if_in_a_row:
                # the alert is not fired enough
                continue

            if (a.recovered or a.last_send_time == 0 or
                    a.last_send_time + a.renotify < cur_time):
                sendable_alerts.append(a)

    sendable_alerts.sort(key=lambda k: (k.recovered, k.last_send_time, k.start_time))
    return sendable_alerts


async def send_new_alerts():
    sendable_alerts = get_sendable_alerts()
    send_start_time = time.time()

    try:
        await send_alerts(sendable_alerts)
    finally:
        sucessful_cnt = 0
        for alert in sendable_alerts:
            if alert.last_send_time >= send_start_time:
                sucessful_cnt += 1

        if not sucessful_cnt:
            metrics.tg_fails += 1

        metrics.send_alert_queue_size = len(sendable_alerts) - sucessful_cnt

        # clean recovered alerts
        for alert in sendable_alerts:
            if alert.recovered and alert.last_send_time >= send_start_time:
                delete_alert(alert)


def delete_alert(alert):
    if alert.alert_id in prefix_to_id_to_alert[alert.prefix]:
        del prefix_to_id_to_alert[alert.prefix][alert.alert_id]
        if not prefix_to_id_to_alert[alert.prefix]:
            del prefix_to_id_to_alert[alert.prefix]


def try_reload_send_alerts(directory):
    global send_alerts_mod_time
    global send_alerts

    full_filename = os.path.join(directory, SEND_ALERTS_FILENAME)

    mod_time = os.path.getmtime(full_filename)
    if mod_time == send_alerts_mod_time and send_alerts:
        return

    if not send_alerts:
        log("file", SEND_ALERTS_FILENAME, "found, loading")
    else:
        log("file", SEND_ALERTS_FILENAME, "changed, reloading")

    spec = importlib.util.spec_from_file_location(SEND_ALERTS_FILENAME, full_filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    send_alerts = module.send_alerts
    send_alerts_mod_time = mod_time
    gc.collect()


async def alert_sender_loop():
    ALERT_PAUSE = 10
    while True:
        try:
            await send_new_alerts()
        except Exception:
            traceback.print_exc()
            metrics.exceptions_cnt["alert_sender"] += 1
        finally:
            await asyncio.sleep(ALERT_PAUSE)


async def send_alert_reloader_loop(directory):
    global send_alerts

    RELOAD_PAUSE = 10
    while True:
        try:
            try_reload_send_alerts(directory)
        except Exception:
            traceback.print_exc()
        finally:
            await asyncio.sleep(RELOAD_PAUSE)


async def alert_stats_loop():
    STATS_PAUSE = 60
    while True:
        try:
            if prefix_to_checks_cnt:
                log(f"Stats:")
            for prefix, checks_count in prefix_to_checks_cnt.items():
                alerts_count = len(prefix_to_id_to_alert[prefix])
                str_prefix = prefix_to_str(prefix)
                log(f" {str_prefix} {checks_count} checks, {alerts_count} active alerts")
        except Exception:
            traceback.print_exc()
            metrics.exceptions_cnt["alert_printer"] += 1
        finally:
            await asyncio.sleep(STATS_PAUSE)


async def alert_save_loop():
    SAVE_PAUSE = 60
    while True:
        try:
            with open("alerts.json.tmp", "w") as file:
                for id_to_alert in prefix_to_id_to_alert.values():
                    for alert in id_to_alert.values():
                        file.write(json.dumps(asdict(alert), ensure_ascii=False) + "\n")

            os.rename("alerts.json.tmp", "alerts.json")
        except Exception:
            traceback.print_exc()
            metrics.exceptions_cnt["alert_saver"] += 1
        finally:
            await asyncio.sleep(SAVE_PAUSE)


def load_alerts():
    try:
        loaded = 0
        with open("alerts.json") as file:
            for line in file:
                try:
                    alert_dict = json.loads(line)
                    alert = Alert(**alert_dict)
                    prefix_to_id_to_alert[alert.prefix][alert.alert_id] = alert
                    loaded +=1
                except Exception as E:
                    log(f"bad line in alerts.json, {E}: {line}")
            log(f"loaded {loaded} alerts from alerts.json")
    except FileNotFoundError:
        pass
    except Exception:
        traceback.print_exc()
