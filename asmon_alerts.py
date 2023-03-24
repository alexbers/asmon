import aiohttp
import asyncio
import contextvars
import time
import traceback
import sys
from collections import defaultdict
from dataclasses import dataclass

from config import BOT_TOKEN, TG_DEST_ID, ALERT_PAUSE

from asmon_core import prefix_ctx, file_name_ctx, alerts_repeat_after_ctx, prefix_to_checks_cnt
import asmon_metrics

DEBUG = False

MAX_TG_MSG_LEN = 4096
MAX_ALERT_MSG_LEN = 1024

fired_alerts_ctx = contextvars.ContextVar("fired_alerts", default=set())
prefix_to_id_to_alert = defaultdict(dict)

@dataclass
class Alert:
    prefix: tuple
    alert_id: str
    text: str
    start_time: float
    last_send_time: float
    repeat_after: float
    recovered: bool


def log(*args, **kwargs):
    print(*args, **kwargs, file=sys.stderr, flush=True)


def precheck_hook(args_str):
    fired_alerts_ctx.set(set())


def postcheck_hook():
    active = [a for a in prefix_to_id_to_alert[prefix_ctx.get()].values()]
    for alert in active:
        if alert.alert_id not in fired_alerts_ctx.get():
            alert.recovered = True


async def send_msg(user_id, text):
    if DEBUG:
        log("send_msg emulate only", user_id, text)
        return True


    url = "https://api.telegram.org/bot%s/sendMessage" % BOT_TOKEN
    payload = {"chat_id": user_id, "text": text,}

    try:
        async with aiohttp.request("POST", url, json=payload) as resp:
            if resp.status != 200:
                print(3)
                asmon_metrics.tg_fails += 1
                resp_text = await resp.text()
                log(f"Failed to send msg to {user_id}: {text} " +
                    f"{resp.status} {resp.reason} {resp_text}")
            return resp.status == 200
    except OSError:
        traceback.print_exc()
        asmon_metrics.exceptions_cnt["alert_sender"] += 1
        return False


def alert(text, alert_id="default", repeat_after=None):
    if not file_name_ctx.get():
        # if script runs directly, do nothing
        log(text)
        return

    alert_id = str(alert_id)
    fired_alerts_ctx.get().add(alert_id)

    if repeat_after is None:
        repeat_after = alerts_repeat_after_ctx.get()

    if len(text) > MAX_ALERT_MSG_LEN:
        text = text[:MAX_ALERT_MSG_LEN-3] + "..."

    prefix = prefix_ctx.get()

    id_to_alert = prefix_to_id_to_alert[prefix]

    if alert_id not in id_to_alert:
        id_to_alert[alert_id] = Alert(prefix, alert_id, text, start_time=time.time(),
                                      last_send_time=0, repeat_after=repeat_after,
                                      recovered=False)
    else:
        id_to_alert[alert_id].text = text
        id_to_alert[alert_id].repeat_after = repeat_after
        id_to_alert[alert_id].recovered = False


def format_seconds(sec):
    sec = int(sec)
    if sec < 120:
        return f"{sec} сек."
    elif sec < 120*60:
        return f"{sec//60} мин."
    elif sec < 48*60*60:
        return f"{sec//60//60} ч."
    else:
        return f"{sec//60//60/24} дн."


def form_filename_to_alerts():
    filename_to_alerts = {}
    for prefix, id_to_alert in prefix_to_id_to_alert.items():
        filename = prefix[0]

        if filename not in filename_to_alerts:
            filename_to_alerts[filename] = []

        for alert_id, alert in id_to_alert.items():
            filename_to_alerts[filename].append(alert)
    return filename_to_alerts


async def send_new_alerts():
    filename_to_alerts = form_filename_to_alerts()
    for filename, alerts in filename_to_alerts.items():
        msg = ""
        alerts_in_send_batch = []

        cur_time = time.time()

        good_alerts = []
        for a in alerts:
            if not prefix_to_checks_cnt[a.prefix]:
                # there was no checks after reloading
                continue

            if (a.recovered or a.last_send_time == 0 or
                    a.last_send_time + a.repeat_after < cur_time):
                good_alerts.append(a)


        good_alerts.sort(key=lambda k: (k.recovered, k.last_send_time, k.start_time))

        for alert in good_alerts:
            if alert.recovered:
                broken_time = format_seconds(cur_time - alert.start_time)
                msg_part = f"🎉 починилось, было сломано {broken_time}: {alert.text}"
            elif alert.last_send_time == 0:
                msg_part = f"🔥 сломалось: {alert.text}"
            else:
                broken_time = format_seconds(cur_time - alert.start_time)
                msg_part = f"⚠ сломано уже {broken_time}: {alert.text}"
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
                if alert.recovered:
                    # delete alert
                    if alert.alert_id in prefix_to_id_to_alert[alert.prefix]:
                        del prefix_to_id_to_alert[alert.prefix][alert.alert_id]
                        if not prefix_to_id_to_alert[alert.prefix]:
                            del prefix_to_id_to_alert[alert.prefix]


async def alert_sender_loop():
    while True:
        try:
            await send_new_alerts()
        except Exception:
            traceback.print_exc()
            asmon_metrics.exceptions_cnt["alert_sender"] += 1
        finally:
            await asyncio.sleep(ALERT_PAUSE)
