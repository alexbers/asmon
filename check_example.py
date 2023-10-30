# Use this file as check template.
# Files that starts with checks_ are loaded automatically
# If file is modified it is reloaded
# For dry run just launch the script directly

import asyncio
import json

import httpx

from asmon import checker, alert, metric, common_checks


@checker(pause=5)
async def just_check():
    """
    I am just_check() function in check_example.py
    The system periodicaly runs me and gets my alerts
    To make me run more often, modify set_checker_defaults call above
    You can modify me and system will reload me automatically
    """

    alert("this is a test alert, please edit check_example.py")


# @checker(pause=5, timeout=60)
# async def check_google_port80():
#     """
#     An example of basic checker, checks if TCP port is open every 5 seconds.
#     """

#     HOST = "alexbers.com"
#     PORT = 4439
#     try:
#         reader, writer = await asyncio.wait_for(asyncio.open_connection(HOST, PORT), timeout=10)
#         writer.close()
#     except Exception as E:
#         alert(f"port {PORT} on host {HOST} is unreachable: {E!r}")


# @checker(args=["ya.ru", "google.com"], pause=1*60*60, timeout=600)
# async def check_certs(host):
#     """
#     You can specify several hosts to check, every arg is a task
#     You can export some data as metrics
#     """
#     try:
#         days_left = await common_checks.get_cert_expire_days(host, timeout=10)
#         metric("ssl_days_left", days_left)

#         if days_left < 10000:
#             alert(f"certificate on {host} will expire in {days_left:.01f} days", 1)

#     except Exception as E:
#         alert(f"port 443 on host {host} is unreachable: {E!r}")



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
