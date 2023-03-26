# The example of check
# Files that starts with checks_ are loaded automatically
# If file is modified it is reloaded

# See more examples in asmon_checkers.py

import asyncio

import httpx

from asmon import checker, alert
import asmon_checkers

# you can dynamically edit this file, it will be reloaded
@checker
async def just_check():
    print("I am just_check() function in check_example.py")
    print("The system periodicaly runs me and gets my alerts")
    print("To make me run more ofter, modify CHECK_PAUSE in config.py")
    print("You can modify me and system will reload me automatically")

    # comment and uncomment the next line to test the dynamic reloading
    alert("this is test alert, please edit check_example.py")


# an example of basic checker, checks if TCP port is open every 5 seconds
# also you can use checkers from asmon_checkers, see more examples there
@checker(pause=5, timeout=20)
async def check_google_port80():
    await asmon_checkers.check_tcp_port("google.com", 80)


# you can specify several hosts to check, every arg is a task
@checker(args=["ya.ru", "google.com"], pause=1*60*60, timeout=60)
async def check_certs(host):
    await asmon_checkers.check_cert_expire(host, days=10000)


# more complex checks, shows how easy you can write custom checks
# alert_repeat_after is a reminder period for alerts
@checker(pause=5, alerts_repeat_after=60*60*48, timeout=60)
async def check_wikipedia():
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://wikipedia.org/", follow_redirects=True)
            if resp.status_code != 200:
                alert(f"википедия вернула плохой статус ответа {resp.status_code}")

            if "wikipedia" not in resp.text:
                alert(f"википедия вернула плохую страничку")
    except OSError as E:
        alert(f"википедия недоступна {E}")
