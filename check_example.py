# The example of check
# Files that starts with checks_ are loaded automatically
# If file is modified it is reloaded

# See more examples in asmon_checkers.py

import asyncio
import aiohttp

from asmon import checker, alert
import asmon_checkers

# an example of basic checker, checks if TCP port is open
@checker(pause=5, alerts_repeat_after=300, timeout=20)
async def check_port80():
    try:
        reader, writer = await asyncio.open_connection("google.com", 80)
        writer.close()
        await writer.wait_closed()
    except OSError as E:
        alert(f"недоступен порт 80 на узле {host}: {E}")


# you can specify several hosts to check, every arg is a task
# also you can use checkers from common library
@checker(args=["ya.ru", "google.com"], pause=1*60*60, alerts_repeat_after=60*60*48, timeout=60)
async def check_certs(host):
    await asmon_checkers.check_cert_expire(host, days=10000)


# more complex checks, shows how easy you can write custom checks
@checker(pause=5, alerts_repeat_after=60*60*48, timeout=60)
async def check_https():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://wikipedia.org/") as resp:
                if resp.status != 200:
                    alert(f"википедия вернула плохой статус ответа {resp.status}")

                resp_text = await resp.text()
                if "wikipedia" not in resp_text:
                    alert(f"википедия вернула плохую страничку")
    except OSError as E:
        alert(f"википедия недоступна {E}")


# also you can dynamically edit this file, it will be reloaded
@checker
async def just_check():
    print("I am just a do-nothing print")
    print("You can modify CHECK_PAUSE in config.py to make me run more often")

    # comment and uncomment the next line to see the dynamic reloading
    alert("test")
