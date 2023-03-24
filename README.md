# Async Monitoring #

The asyncronous platform to run custom checks on your servers

## Starting Up ##
    
1. `git clone https://github.com/alexbers/asmon.git; cd asmon`
2. edit *config.py*, set **TG_DEST_ID**, and **BOT_TOKEN**
3. `docker-compose up -d` (or just `python3 asmon.py` if you don't like Docker)
4. write check_something.py file with your checkers, platform runs them automatically


## Goals ##

1. Small code amount, which makes it easy to patch it for your needs
2. Customizability, all checks are developed using Python, which gives unlimited posibilities
3. Absense of state, ability to dynamicaly change checks

## Idea ##

This is a monitoring platform that allows you to develop custom check scripts on Python, run
them and get Telegram messages if something goes wrong.

It has very simple API, you need only two things:

1. checker decorator to specify how to run your function, timeouts, how often to check,
and so on
2. alert function, that queues the alert message


Example of check_something.py:

```
from asmon import checker, alert

@checker(args=["ya.ru", "google.com"], pause=5, alerts_repeat_after=300, timeout=20)
async def test_port80(host):
    try:
        reader, writer = await asyncio.open_connection(host, 80)
        writer.close()
        await writer.wait_closed()
    except OSError as E:
        alert(f"unreachable port 80 on {host}: {E}")
```

Under the hood the platform finds check scripts, runs decorated checker functions, groups alerts and sends them using Telegram. Also the platform sends messages about recoveries and reminds about unrecovered alerts with specified interval.

If you modify some script, the platform will do its magic and you don't have to restart anything.

The platform exports its metrics in Prometheus format.

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

Here you will get two alerts: "AAAA" and "BBBB". If you comment them out, you will get two recovery messages.
