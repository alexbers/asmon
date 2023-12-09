import asyncio
import contextvars
import time
import traceback
import sys
import os
import json
from dataclasses import dataclass, asdict

import httpx

from config import BOT_TOKEN, TG_DEST_ID, LANGUAGE
from .commons import (log, prefix_to_id_to_alert, prefix_to_str, prefix_ctx,
                      file_name_ctx, renotify_ctx, if_in_a_row_ctx,
                      prefix_to_checks_cnt)
from . import metrics

MAX_TG_MSG_LEN = 4096
MAX_ALERT_MSG_LEN = 1024

fired_alerts_ctx = contextvars.ContextVar("fired_alerts", default=set())

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


def format_seconds(sec, lang="EN"):
    sec = int(sec)
    if sec < 120:
        return f"{sec} сек." if lang == "RU" else f"{sec} sec."
    elif sec < 120*60:
        return f"{sec//60} мин." if lang == "RU" else f"{sec//60} min."
    elif sec < 48*60*60:
        return f"{sec//60//60} ч." if lang == "RU" else f"{sec//60//60} hours."
    else:
        return f"{sec//60//60//24} дн." if lang == "RU" else f"{sec//60//60//24} days."


def format_alert(alert, lang="EN", max_len=MAX_ALERT_MSG_LEN):
    text = ""
    if alert.recovered:
        broken_time = format_seconds(time.time() - alert.start_time, lang=lang)
        if lang == "RU":
            text = f"🎉 починилось, было сломано {broken_time}: {alert.text}"
        else:
            text = f"🎉 fixed, was broken {broken_time}: {alert.text}"
    elif alert.last_send_time == 0:
        if lang == "RU":
            text = f"🔥 сломалось: {alert.text}"
        else:
            text = f"🔥 broken: {alert.text}"
    else:
        broken_time = format_seconds(time.time() - alert.start_time, lang=lang)
        if lang == "RU":
            text = f"⏱ сломано уже {broken_time}: {alert.text}"
        else:
            text = f"⏱ broken for {broken_time}: {alert.text}"

    if len(text) > max_len:
        text = text[:max_len][:-3] + "..."

    return text


def delete_alert(alert):
    if alert.alert_id in prefix_to_id_to_alert[alert.prefix]:
        del prefix_to_id_to_alert[alert.prefix][alert.alert_id]
        if not prefix_to_id_to_alert[alert.prefix]:
            del prefix_to_id_to_alert[alert.prefix]


async def send_msg(user_id, text):
    log("send_msg", user_id, text)

    url = "https://api.telegram.org/bot%s/sendMessage" % BOT_TOKEN
    payload = {"chat_id": user_id, "text": text,}

    try:
        async with httpx.AsyncClient() as client:
            resp = httpx.post(url, json=payload)
            if resp.status_code != 200:
                log(f"Failed to send msg to {user_id}: {text} " +
                    f"{resp.status_code} {resp.text}")
                metrics.tg_fails += 1
            return resp.status_code == 200
    except OSError:
        traceback.print_exc()
        metrics.exceptions_cnt["alert_sender"] += 1
        return False


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


def get_alert_group(alert):
    return alert.filename


async def send_alerts(alerts):
    group_to_alerts = {}
    for alert in alerts:
        group = get_alert_group(alert)
        if group not in group_to_alerts:
            group_to_alerts[group] = []
        group_to_alerts[group].append(alert)

    for group, alerts in group_to_alerts.items():
        msg = ""
        alerts_to_send = []

        for alert in alerts:
            msg_part = format_alert(alert, lang=LANGUAGE)

            if len(msg) + len(msg_part) + 1 >= MAX_TG_MSG_LEN:
                break

            msg += msg_part + "\n"
            alerts_to_send.append(alert)

        if not msg:
            continue

        success = await send_msg(TG_DEST_ID, msg)
        if success:
            for alert in alerts_to_send:
                alert.last_send_time = time.time()


async def send_new_alerts():
    sendable_alerts = get_sendable_alerts()
    send_start_time = time.time()

    try:
        await send_alerts(sendable_alerts)
    finally:
        # clean recovered alerts
        for alert in sendable_alerts:
            if alert.recovered and alert.last_send_time >= send_start_time:
                delete_alert(alert)



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
