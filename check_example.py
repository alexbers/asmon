# The example of check
# Files that starts with checks_ are loaded automatically
# If file is modified it is reloaded
# For dry run just launch the script directly

# See more examples in common_checks.py

import asyncio
import json

import httpx

from asmon import checker, alert, metric, set_checker_defaults
import common_checks

set_checker_defaults(
    pause=15,                # pause between checks, default is 60
    timeout=600,             # checker timeout, default is infinite
    alerts_repeat_after=60,  # repeat alerts delay in secs, default is never repeat
    max_starts_per_sec=100,  # throttle starts of a single check function, default is infinite,
    if_in_a_row=1            # alert only if it occurs this number in a row, default is 1
)


@checker
async def just_check():
    """
    I am just_check() function in check_example.py
    The system periodicaly runs me and gets my alerts
    To make me run more often, modify set_checker_defaults call above
    You can modify me and system will reload me automatically
    """

    alert("this is a test alert, please edit check_example.py")


# @checker(pause=5, timeout=600)
# async def check_google_port80():
#     """
#     An example of basic checker, checks if TCP port is open every 5 seconds.
#     Also you can use checker functions from common_checks.py, see more examples there
#     """
#     await common_checks.check_tcp_port("google.com", 80)


# @checker(args=["ya.ru", "google.com"], pause=1*60*60, timeout=600)
# async def check_certs(host):
#     """
#     You can specify several hosts to check, every arg is a task
#     You can export some data as metrics
#     """
#     days_left = await common_checks.check_cert_expire(host, days=10000)
#     metric("ssl_days_left", days_left)


# @checker(pause=60, alerts_repeat_after=60*60*48, timeout=600)
# async def check_rest_api():
#     """
#     More complex checks, shows how easy you can write custom checks
#     alert_repeat_after is a reminder period for alerts
#     """
#     try:
#         async with httpx.AsyncClient() as client:
#             resp = await client.get("https://reqres.in/api/users", timeout=300)
#             if resp.status_code != 200:
#                 alert(f"test rest-service returned bad answer status {resp.status_code}")
#                 return
#             if "data" not in resp.json():
#                 alert(f"test rest-service returned json without 'data' field")
#     except httpx.RequestError as E:
#         alert(f"test rest-service is unavailable {E}")
#     except json.decoder.JSONDecodeError:
#         alert("test rest-service returned bad json")
