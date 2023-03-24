# This file contains implementation of some common checkers
# Use it as examples to develop your own checkers
# If you edit this file, it will be not autoreloaded

import asyncio
import time

import aiohttp

from asmon import alert

async def check_cert_expire(host, days=7, timeout=10):
    expire_time = 0
    class MyConnector(aiohttp.TCPConnector):
        async def connect(self, *args, **kwargs):
            TIME_FMT = "%b %d %H:%M:%S %Y %Z"

            c = await aiohttp.TCPConnector.connect(self, *args, **kwargs)
            sslobj = c.transport.get_extra_info("ssl_object")
            cert = sslobj.getpeercert()

            nonlocal expire_time
            expire_time = time.mktime(time.strptime(cert["notAfter"], TIME_FMT))
            return c
    try:
        timeout = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(connector=MyConnector(), timeout=timeout) as session:
            async with session.head(f'https://{host}/') as resp:
                pass
    except aiohttp.client_exceptions.ClientConnectorCertificateError as E:
        alert(f"битый сертификат {host}: {E.certificate_error}", 2)
    except aiohttp.client_exceptions.ClientConnectorError as E:
        alert(f"не получилось подключиться к {host}: {E.os_error}", 2)
    except aiohttp.client_exceptions.ServerTimeoutError as E:
        alert(f"не получилось подключиться по https к {host}: таймаут", 2)

    if not expire_time:
        return

    time_left = int(expire_time - time.time())
    if time_left < 0:
        alert(f"сертификат {host} закончился {-time_left//60//60//24} дн. назад", 1)
    elif time_left < 60*60*24*days:
        alert(f"сертификат {host} закончится через {time_left//60//60//24} дн.", 1)

if __name__ == "__main__":
    # print("MAIN")
    asyncio.run(check_cert_expire("expired.badssl.com"))
    # asyncio.run(check_cert_expire("wrong.host.badssl.com"))
    # asyncio.run(check_cert_expire("self-signed.badssl.com"))
    # asyncio.run(check_cert_expire("untrusted-root.badssl.com"))
    # asyncio.run(check_cert_expire("revoked.badssl.com"))
    # asyncio.run(check_cert_expire("pinning-test.badssl.com"))
    # asyncio.run(check_cert_expire("no-common-name.badssl.com"))
    # asyncio.run(check_cert_expire("no-subject.badssl.com"))
    # asyncio.run(check_cert_expire("incomplete-chain.badssl.com"))
    # asyncio.run(check_cert_expire("sha256.badssl.com"))
    # asyncio.run(check_cert_expire("10000-sans.badssl.com"))
    # asyncio.run(check_cert_expire("client.badssl.com"))
    # asyncio.run(check_cert_expire("rc4-md5.badssl.com"))
    # asyncio.run(check_cert_expire("rc4.badssl.com"))
    # asyncio.run(check_cert_expire("dh1024.badssl.com"))
    # asyncio.run(check_cert_expire("no-sct.badssl.com"))
    # asyncio.run(check_cert_expire("sha1-intermediate.badssl.com"))
