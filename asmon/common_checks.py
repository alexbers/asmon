# This file contains implementation of some common checks
# If you edit this file, it will be not autoreloaded

import asyncio
import time


async def get_cert_expire_days(host, port=443, timeout=10):
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(
            host, port, ssl=True, server_hostname=host, limit=4096), timeout=timeout)
    ssl_object = writer.get_extra_info("ssl_object")
    writer.close()
    cert = ssl_object.getpeercert()

    TIME_FMT = "%b %d %H:%M:%S %Y %Z"
    expire_time = time.mktime(time.strptime(cert["notAfter"], TIME_FMT))
    days_left = (expire_time - time.time())/60/60/24
    return days_left
