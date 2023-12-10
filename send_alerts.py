"""This file contains the logic to send alerts

By default messages are grouped and sent to some Telegram account or group.

You should modify this file only if you have specific needs, like to notify
several people or use other method to deliver alerts. After modifications,
changes will be applied automatically, no need to restart the service. Be careful

Only one function is required - send_alerts(alerts). This function should send
at least one alert and mark it as sent by updating last_send_time of this alert.

"""

import asyncio
import time

from config import BOT_TOKEN, TG_DEST_ID, LANGUAGE
from asmon import log

import httpx


MAX_TG_MSG_LEN = 4096
MAX_ALERT_MSG_LEN = 1024


async def send_alerts(alerts):
    """ Alert sending logic is here """
    group_to_alerts = group_alerts(alerts)

    for group, alerts_in_group in group_to_alerts.items():
        msg, alerts_to_send = format_alerts(alerts_in_group)
        if not msg:
            continue
        success = await send_msg(TG_DEST_ID, msg, BOT_TOKEN)
        if success:
            for alert in alerts_to_send:
                alert.last_send_time = time.time()


def group_alerts(alerts):
    group_to_alerts = {}
    for alert in alerts:
        group = get_alert_group(alert)
        if group not in group_to_alerts:
            group_to_alerts[group] = []
        group_to_alerts[group].append(alert)
    return group_to_alerts


def get_alert_group(alert):
    return alert.filename


async def send_msg(user_id, text, token=BOT_TOKEN):
    log("send_msg", user_id, text)

    url = "https://api.telegram.org/bot%s/sendMessage" % token
    payload = {"chat_id": user_id, "text": text,}

    try:
        async with httpx.AsyncClient() as client:
            resp = httpx.post(url, json=payload)
            if resp.status_code != 200:
                log(f"Failed to send msg to {user_id}: {text} " +
                    f"{resp.status_code} {resp.text}")
            return resp.status_code == 200
    except OSError:
        traceback.print_exc()
        return False


def format_alerts(alerts):
    msg = ""
    chosen_alerts = []

    for alert in alerts:
        curr_msg = format_alert(alert, lang=LANGUAGE)

        if len(msg) + len(curr_msg) + 1 >= MAX_TG_MSG_LEN:
            break

        msg += curr_msg + "\n"
        chosen_alerts.append(alert)
    return msg, chosen_alerts


def format_alert(alert, lang, max_len=MAX_ALERT_MSG_LEN):
    text = ""
    if alert.recovered:
        broken_time = format_seconds(time.time() - alert.start_time, lang=lang)
        if lang != "RU":
            text = f"🎉 fixed, was broken {broken_time}: {alert.text}"
        else:
            text = f"🎉 починилось, было сломано {broken_time}: {alert.text}"
    elif alert.last_send_time == 0:
        if lang != "RU":
            text = f"🔥 broken: {alert.text}"
        else:
            text = f"🔥 сломалось: {alert.text}"
    else:
        broken_time = format_seconds(time.time() - alert.start_time, lang=lang)
        if lang != "RU":
            text = f"⏱ broken for {broken_time}: {alert.text}"
        else:
            text = f"⏱ сломано уже {broken_time}: {alert.text}"

    if len(text) > max_len:
        text = text[:max_len][:-3] + "..."
    return text


def format_seconds(sec, lang):
    sec = int(sec)
    if sec < 120:
        return f"{sec} sec." if lang != "RU" else f"{sec} сек."
    elif sec < 120*60:
        return f"{sec//60} min." if lang != "RU" else f"{sec//60} мин."
    elif sec < 48*60*60:
        return f"{sec//60//60} hours." if lang != "RU" else f"{sec//60//60} ч."
    else:
        return f"{sec//60//60//24} days." if lang != "RU" else f"{sec//60//60//24} дн."



######################## THIS IS A GOOD PLACE TO EMULATE SOME ALERTS #######################

if __name__ == "__main__":
    async def send_msg(user_id, text, token=BOT_TOKEN):
        print(f"emulate sending message to {user_id!r}:\n{text}")
        return True


    def simple_alert(text, filename="check_something.py", funcname="somefunc", funcarg="somearg",
                     alert_id="default", start_time=1, last_update_time=1,
                     last_send_time=0, renotify=10, in_a_row=1,
                     notify_if_in_a_row=1, recovered=False):
        from asmon.alerts import Alert
        return Alert(text=text, filename=filename, funcname=funcname, funcarg=funcarg, alert_id=alert_id,
                     start_time=start_time, last_update_time=last_update_time, last_send_time=last_send_time,
                     renotify=renotify, in_a_row=in_a_row, notify_if_in_a_row=notify_if_in_a_row, recovered=recovered)

    a1 = simple_alert(text="first")
    a2 = simple_alert(text="second", recovered=True)
    a3 = simple_alert(text="third", filename="check_something2.py")
    asyncio.run(send_alerts([a1, a2, a3]))

    a1 = simple_alert(text="first", last_send_time=1)
    a2 = simple_alert(text="second", filename="check_something2.py")
    asyncio.run(send_alerts([a1, a2]))

