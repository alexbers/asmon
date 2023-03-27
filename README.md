# Asmon — Asyncronous Monitoring Platform #

Asmon is a Python platform to monitor your services and send Telegram alerts if something goes wrong.

This platform periodicaly runs your checkers.

![Demo](https://alexbers.com/asmon.png)

## Goals ##

1. Customizability, unlimited checking and alerting posibilities
2. Speed
3. Small amount of code

## Starting Up ##

1. `git clone https://github.com/alexbers/asmon.git; cd asmon`
2. edit *config.py*, set **TG_DEST_ID**, and **BOT_TOKEN**
3. `docker-compose up -d` (or just `python3 asmon.py` if you don't like Docker)
4. modify check_example.py with your checks, platform runs them automatically

## Performance ##

In other monitoring platforms, running custom checks involves running an external program, which is
expensive in terms of CPU and RAM.

Asmon allows developers to create custom checks in Python using asyncronous functions. Each check consumes approximately 10KB of memory, so you can run 100 000 simultanious checks per gigabyte of RAM.

The check speed depends on the check function complexity. For example, when checking SSL certificate
expiration, you can expect a speed of about 1 000 checks/sec on the cheapest VM available
on Digital Ocean hosting.


## How to Develop Checkers  ##

The platfom has a simple API, that requires knowledge of two things:

1. The `checker` decorator to mark your function to be periodicaly launched
2. The `alert` function to signal if something is wrong


Example of *check_my_service.py*:

```python
import json
import httpx
from asmon import checker, alert

@checker
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
        alert(f"rest service is down: {E}")
    except json.decoder.JSONDecodeError:
        alert("rest service returned bad JSON")
```

The `checker` decorator can have these arguments:

- args: create multiple tasks, one per argument. Default: single task without arguments is created
- pause: pause after check in seconds until the next check. Default: see config.py
- max_starts_per_sec: limits the number of function calls per second. Useful if you have many tasks. Default: no limit
- alerts_repeat_after: if alert remain active for a specified time, send a reminder message. Default: no reminders
- timeout: timeout of check function. Default: no timeout

Another example, *check_certs.py*, showing `checker` decorator usage with arguments and a built-in
check for TLS certificate expiration:

```python
from asmon import checker, alert
import asmon_checkers

SITES_TO_CHECK = ["google.com", "microsoft.com"]

@checker(args=SITES_TO_CHECK, pause=60, timeout=10, alerts_repeat_after=30)
async def check_certs(host):
    await asmon_checkers.check_cert_expire(host, days=100)
```

The platform sends messages about recoveries and reminds you about unrecovered alerts at intervals.

Scripts should begin with "check_". If you modify a script, the platform will do its magic and
automaticaly reload it.

The platform exports its metrics in Prometheus format, so you can monitor the monitoring.

For more examples, see `check_example.py`


### Advanced usage ###

If you want to distinguish between different error conditions and have different alerts for them, use the second parameter of alert function - the alert\_id.

Example:

```python
@checker
async def f():
   alert("AAAA", 1)
   alert("BBBB", 2)
```

This will produce two alerts: "AAAA" and "BBBB". If you comment them out, you will receive two recovery messages.

If you want to skip the rest checks, for example, if the site is down, use

```python
@checker
async def f():
    if ...:
        alert("site is down, skip checks")
        raise Exception()
    alert("bad page 1", 1)
    alert("bad page 2", 2)
```

In this case, if there will be "site is down" alert, you will not get spam messages about recoveries of other two alerts, if they were fired before.
