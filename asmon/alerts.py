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
                      filename_to_tasks, prefix_to_checks_cnt)
from . import metrics

MAX_TG_MSG_LEN = 4096
MAX_ALERT_MSG_LEN = 1024

fired_alerts_ctx = contextvars.ContextVar("fired_alerts", default=set())

@dataclass
class Alert:
    prefix: tuple
    alert_id: str
    text: str
    start_time: float
    last_update_time: float
    last_send_time: float
    renotify: float
    in_a_row: int
    send_if_in_a_row: int
    recovered: bool


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
            if alert.in_a_row < alert.send_if_in_a_row:
                delete_alert(alert)


def recover_alerts(filename):
    filename_to_alerts = make_filename_to_alerts()
    for alert in filename_to_alerts.get(filename, []):
        alert.recovered = True


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

    if len(text) > MAX_ALERT_MSG_LEN:
        text = text[:MAX_ALERT_MSG_LEN-3] + "..."

    prefix = prefix_ctx.get()
    id_to_alert = prefix_to_id_to_alert[prefix]

    if alert_id not in id_to_alert:
        id_to_alert[alert_id] = Alert(prefix, alert_id, text, start_time=time.time(),
                                      last_update_time=time.time(), last_send_time=0,
                                      renotify=renotify, in_a_row=1,
                                      send_if_in_a_row=if_in_a_row,
                                      recovered=False)
    else:
        id_to_alert[alert_id].text = text
        id_to_alert[alert_id].last_update_time = time.time()
        id_to_alert[alert_id].renotify = renotify
        id_to_alert[alert_id].in_a_row += 1
        id_to_alert[alert_id].send_if_in_a_row = if_in_a_row
        id_to_alert[alert_id].recovered = False


def format_seconds(sec, lang="EN"):
    sec = int(sec)
    if sec < 120:
        return f"{sec} сек." if lang == "RU" else f"{sec} sec."
    elif sec < 120*60:
        return f"{sec//60} мин." if lang == "RU" else f"{sec} min."
    elif sec < 48*60*60:
        return f"{sec//60//60} ч." if lang == "RU" else f"{sec} hours."
    else:
        return f"{sec//60//60//24} дн." if lang == "RU" else f"{sec} days."


def make_filename_to_alerts():
    filename_to_alerts = {}
    for prefix, id_to_alert in prefix_to_id_to_alert.items():
        filename = prefix[0]

        if filename not in filename_to_alerts:
            filename_to_alerts[filename] = []

        for alert_id, alert in id_to_alert.items():
            filename_to_alerts[filename].append(alert)
    return filename_to_alerts


def delete_alert(alert):
    if alert.alert_id in prefix_to_id_to_alert[alert.prefix]:
        del prefix_to_id_to_alert[alert.prefix][alert.alert_id]
        if not prefix_to_id_to_alert[alert.prefix]:
            del prefix_to_id_to_alert[alert.prefix]


async def send_new_alerts():
    filename_to_alerts = make_filename_to_alerts()
    for filename, alerts in filename_to_alerts.items():
        msg = ""
        alerts_in_send_batch = []

        cur_time = time.time()

        good_alerts = []
        for a in alerts:
            if not prefix_to_checks_cnt[a.prefix] and a.prefix[1] != "__loading__":
                # there was no checks after reloading
                continue

            if a.last_update_time < a.last_send_time:
                # the alert is not updated since the last report
                continue

            if not a.recovered and a.in_a_row < a.send_if_in_a_row:
                # the alert is not fired enough
                continue

            if (a.recovered or a.last_send_time == 0 or
                    a.last_send_time + a.renotify < cur_time):
                good_alerts.append(a)


        good_alerts.sort(key=lambda k: (k.recovered, k.last_send_time, k.start_time))

        for alert in good_alerts:
            if alert.recovered:
                broken_time = format_seconds(cur_time - alert.start_time, lang=LANGUAGE)
                if LANGUAGE == "RU":
                    msg_part = f"🎉 починилось, было сломано {broken_time}: {alert.text}"
                else:
                    msg_part = f"🎉 fixed, was broken {broken_time}: {alert.text}"
            elif alert.last_send_time == 0:
                if LANGUAGE == "RU":
                    msg_part = f"🔥 сломалось: {alert.text}"
                else:
                    msg_part = f"🔥 broken: {alert.text}"
            else:
                broken_time = format_seconds(cur_time - alert.start_time, lang=LANGUAGE)
                if LANGUAGE == "RU":
                    msg_part = f"⏱ сломано уже {broken_time}: {alert.text}"
                else:
                    msg_part = f"⏱ broken for {broken_time}: {alert.text}"

            if len(msg) + len(msg_part) + 1 >= MAX_TG_MSG_LEN:
                break

            msg += msg_part + "\n"
            alerts_in_send_batch.append(alert)

        if not msg:
            continue

        success = await send_msg(TG_DEST_ID, msg)
        if success:
            for alert in alerts_in_send_batch:
                alert.last_send_time = cur_time
                filename = alert.prefix[0]
                task_is_died = not filename_to_tasks[filename]
                if alert.recovered or task_is_died:
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
                for prefix, id_to_alert in prefix_to_id_to_alert.items():
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
                    alert = json.loads(line)
                    alert["prefix"] = tuple(alert["prefix"])
                    prefix = alert["prefix"]
                    alert_id = alert["alert_id"]
                    prefix_to_id_to_alert[prefix][alert_id] = Alert(**alert)
                    loaded +=1
                except Exception as E:
                    log(f"bad line in alerts.json, {E}: {line}")
            log(f"loaded {loaded} alerts from alerts.json")
    except FileNotFoundError:
        pass
    except Exception:
        traceback.print_exc()
