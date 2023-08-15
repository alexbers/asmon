# The example of check
# Files that starts with checks_ are loaded automatically
# If file is modified it is reloaded
# For dry run just launch the script directly

# See more examples in checks.py

import asyncio
import json

import httpx

from asmon import checker, alert
import checks

@checker
async def just_check():
    """
    I am just_check() function in check_example.py
    The system periodicaly runs me and gets my alerts
    To make me run more often, modify CHECK_PAUSE in config.py
    You can modify me and system will reload me automatically
    """

    # comment and uncomment the next line to test the dynamic reloading
    alert("this is a test alert, please edit check_example.py")


# @checker(pause=5, timeout=20)
# async def check_google_port80():
#     """
#     An example of basic checker, checks if TCP port is open every 5 seconds.
#     Also you can use checker functions from checks.py, see more examples there
#     """
#     await checks.check_tcp_port("google.com", 80)


# @checker(args=["ya.ru", "google.com"], pause=1*60*60, timeout=60)
# async def check_certs(host):
#     """
#     You can specify several hosts to check, every arg is a task
#     """
#     await checks.check_cert_expire(host, days=10000)


# @checker(pause=60, alerts_repeat_after=60*60*48, timeout=30)
# async def check_rest_api():
#     """
#     More complex checks, shows how easy you can write custom checks
#     alert_repeat_after is a reminder period for alerts
#     """
#     try:
#         async with httpx.AsyncClient() as client:
#             resp = await client.get("https://reqres.in/api/users", timeout=10)
#             if resp.status_code != 200:
#                 alert(f"тестовый rest-сервис вернул плохой статус ответа {resp.status_code}")
#                 return
#             if "data" not in resp.json():
#                 alert(f"тестовый rest-сервис вернул json без поля 'data'")
#     except httpx.RequestError as E:
#         alert(f"тестовый rest-сервис недоступен {E}")
#     except json.decoder.JSONDecodeError:
#         alert("тестовый rest-сервис вернул плохой json")
