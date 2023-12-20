# Asmon — Asyncronous Monitoring Platform #

Asmon is a Python library to write checkers for your services and produce metrics.

Also it is a script to run periodicaly run your checkers and send Telegram alerts if something goes wrong.

![Demo](https://alexbers.com/asmon_en.png)

The library has a simple interface, you need only know two things to develop checkers:

1. The `checker` decorator to mark the function to be periodicaly launched
2. The `alert` function to signal that something is wrong

Unlike other platforms you have unlimited checking posibilities and the performance of asynchronous Python.
It is **hundreds times faster** than to launch some program or script on every check. That means that you can monitor
thousands services from the **cheapest VM** on some hosting without any CPU or RAM problems.

Alert messages are customizable, so you can include **only relevant data** in alert messages. The alert messages are
automatically **grouped**.

The script autodetects when the problem is fixed and sends a note about it. Also, it reminds about the problem on specified intervals.

When you change some checker, you don't need to restart the service, the runner will **reload it automatically**.

If needed, the Asmon can export its metrics in Prometheus format so your can **monitor** the Asmon. Also you can export custom metrics in checkers.

## Use Cases ##

- Check if your sites are up and their TLS certificates are not about to expire
- Check Telegram bots with Telethon library
- Monitor hosts behind NAT. If the host is alive it can periodicaly connect to some port opened by checker
- Remind about your best friends' birthdays :)

## Starting Up ##

1. `git clone https://github.com/alexbers/asmon.git; cd asmon`
2. use *@BotFather* bot to  get your **BOT_TOKEN**, use *@userinfobot* to get your **TG_DEST_ID**
3. edit *config.py*, set **TG_DEST_ID**, and **BOT_TOKEN**
3. `docker compose up -d` (or just `python3 asmon.py` if you don't like Docker)
4. (optional) modify check_example.py or add some check_\*.py file, the platform will find and run them

## Dry Run ##

To test your check script just run it *directly*: `python3 check_example.py`. All alerts will be in console.

## Checker Examples ##

Example of *check_minimal.py*:
```python
from asmon import checker, alert

@checker(pause=10)
async def just_alert():
    alert("This is a simple alert")
```

Example of *check_rest.py*, checks if some REST API works as expected:

```python
import json
import httpx
from asmon import checker, alert

@checker(pause=10)
async def check_rest_api():
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://reqres.in/api/users", timeout=10)
            if resp.status_code != 200:
                alert(f"rest service returned bad status code {resp.status_code}")
                return
            if "data" not in resp.json():
                alert(f"rest service returned json without 'data' field")
    except httpx.RequestError as E:
        alert(f"rest service is down: {E!r}")
    except json.decoder.JSONDecodeError:
        alert("rest service returned bad JSON")
```

The `checker` decorator also can have these arguments:

- **pause**: pause after check in seconds until the next check. This is *mandatory* arg.
- **timeout**: timeout of check function. *Default*: no timeout
- **renotify**: if alert remain active for a specified time, send a reminder message. *Default*: no reminders
- **if_in_a_row**: notify if event occurs some number of times in a row to prevent flapping. *Default*: 1
- **max_starts_per_sec**: limits the number of function calls per second. Useful if you have many tasks. *Default*: no limit
- **args**: create multiple tasks, one per argument. *Default*: single task without arguments is created

Another example, *check_certs.py*, showing `checker` decorator usage with arguments and a built-in
check for TLS-certificate expiration:

```python
from asmon import checker, alert, useful_checks

SITES_TO_CHECK = ["google.com", "microsoft.com"]

@checker(args=SITES_TO_CHECK, pause=60, timeout=60, renotify=1*60*60)
async def check_certs(host):
    try:
        days_left = await useful_checks.get_cert_expire_days(host, timeout=10)
        metric("ssl_days_left", days_left)
        if days_left < 7:
            alert(f"certificate on {host} will expire in {days_left:.01f} days")
    except Exception as E:
        alert(f"port 443 on host {host} is unreachable: {E!r}", if_in_a_row=2)

```

For more examples, see `check_example.py`


### Advanced usage ###

#### Alert Ids ####
If you want to distinguish between different error conditions and have different alerts for them, use the second parameter of alert function - the **alert\_id**.

Example:

```python
@checker(pause=10)
async def f():
   alert("AAAA", 1)
   alert("BBBB", 2)
```

This will produce two alerts: "AAAA" and "BBBB". If you comment them out, you will receive two recovery messages.

If you want to skip the rest checks, for example, if the site is down, use

```python
@checker(pause=10)
async def f():
    if ...:
        alert("site is down, skip checks")
        raise Exception()
    alert("bad page 1", 1)
    alert("bad page 2", 2)
```

In this case, if there will be "site is down" alert, you will not get spam messages about recoveries of other two alerts, if they were fired before.

#### Events ####
Some problems can not be expressed in terms broken/fixed, instead they can be expressed as events. For example if some user logged in, this is an event. In these cases pass `event=True` keyword argument to *alert*
call.

```python
@checker(pause=10)
async def f():
   alert("AAAA", event=True)
   alert("BBBB", event=True)
```

The system will notify once about every alert. It is up to you to ensure the events not created every time the function runs. For example if you parse logs, you need a global variable to track already handled lines.

#### Metrics ####

Asmon exports its metrics in the Prometheus format on port specified in **METRICS_PORT** constant in config.py. By default access is restricted from all addresses, to add some modify ***IP_WHITELIST*** constant in config.py

Built in metrics:
- **asmon_uptime**: uptime of asmon in seconds
- **asmon_tg_fails**: number of times when no message was sent from send queue, if it growns, alerts are not defivered
- **asmon_send_alert_queue_size**: number of alerts in send queue. If it is not zero, something is likely wrong
- **asmon_tasks**: number of asyncio tasks. If it growns, it is strange
- **asmon_active_tasks**: number of check tasks grouped by file with checkers
- **asmon_checks_total**: number of finished checks, should grown linearly
- **asmon_checks**: number of finished checks per check checker function, should grown linearly
- **asmon_alerts_total**: number of active alerts, usually zero
- **asmon_alerts**: number of active alerts per check checker function, usually zero
- **asmon_exceptions**: exceptions count in asmon core, should be zero
- **asmon_metrics**: user metrics, see bellow

It is good idea to deliver messages about alert delivery problems using some reserve channel like SMS or email.

#### Export Custom Mertics ####

Use the `metric` function:

Example:
```python
from asmon import checker, metric

@checker(args=[123, 456], pause=10)
async def func(arg):
   metric("answer", arg)
```

The metric are called like:
`asmon_metric{prefix="check_somename.py:funk:123",name="answer"}`

#### Survive Reload ####

When you want some variable to surive script reloads use a `SurviveReloadsVar` wrapper. It has `get` and `set` methods:

```python
from telethon import TelegramClient
from asmon import SurviveReloadsVar

client_var = SurviveReloadsVar("client",
                               TelegramClient('9222222222', api_id=111111,
                               api_hash="55555555555555555555555555555555"))
client = client_var.get()
client_var.set(1234)
```

In this example there will be no any Telegram reconnects if the script has been modified and reloaded.

#### Customizing Notifications ####

By default alert messages are grouped and send to some Telegram account or group.

It is possible to customize it, for example to change how messages look, how they grouped, to whom they delivered and so on. It is even possible to use other platform instead of Telegram.

To customize notifications you should modify *send\_alerts.py* script. The changes will be applied automaticaly, no need to restart the service. This script should contain `send_alerts` async function which takes the array of alerts as an argument and sends at least one alert from it. Sent alerts should be marked by updating their last_send_time attribute to current time.
