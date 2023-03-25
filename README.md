# Async Monitoring #

The asyncronous platform to check your services and send Telegram alerts if something goes wrong.

## Starting Up ##
    
1. `git clone https://github.com/alexbers/asmon.git; cd asmon`
2. edit *config.py*, set **TG_DEST_ID**, and **BOT_TOKEN**
3. `docker-compose up -d` (or just `python3 asmon.py` if you don't like Docker)
4. modify check_example.py with your checks, platform runs them automatically


## Goals ##

1. Small code amount, which makes it easy to patch it for your needs
2. Customizability, all checks are developed using Python, which gives unlimited posibilities
3. Speed, all checks are asyncronous

## Idea ##

This is a monitoring platform which periodicaly runs your checkers on Python
and sends Telegram messages if something goes wrong.

It has simple API, you need only two things:

1. `checker` decorator to specify how often to run your function
2. `alert` function to signalize if something is wrong


Example of *check_something.py*:

```
from asmon import checker, alert

@checker(args=["ya.ru", "google.com"], pause=5, alerts_repeat_after=300, timeout=20)
async def test_port80(host):
    writer = None
    try:
        reader, writer = await asyncio.open_connection(host, 80)
    except OSError as E:
        alert(f"unreachable port 80 on {host}: {E}")
    finally:
        writer.close()
```

The platform can send messages about recoveries and remind you about unrecovered alerts with some interval.

Scripts should begin with "check_". If you modify some script, the platform will do its magic and
you don't have to restart anything.

The platform exports its metrics in Prometheus format, so you can monitor the monitoring.

See more examples in `check_example.py`


### Advanced usage ###

If you want to distinguish between different error conditions and have different alert for them, use the second parameter of alert function - the alert\_id.

Example:

```
@checker
async def f():
   alert("AAAA", 1)
   alert("BBBB", 2)
```

You will get two alerts: "AAAA" and "BBBB". If you comment them out, you will get two recovery messages.
