# This file contains implementation of some common checkers
# Use it as examples to develop your own checkers
# If you edit this file, it will be not autoreloaded

import asyncio
import time

import httpx

from asmon import alert


client = None

async def check_tcp_port(host, port):
    writer = None
    try:
        reader, writer = await asyncio.open_connection(host, port)
    except OSError as E:
        alert(f"недоступен порт {port} на узле {host}: {E}")
    finally:
        if writer:
            writer.close()


async def check_cert_expire(host, days=7, timeout=30):
    global client
    try:
        if client is None:
            timeout = httpx.Timeout(timeout, pool=timeout*10)
            client = httpx.AsyncClient(timeout=timeout)

        r = await client.head(f"https://{host}/", follow_redirects=False)

        network_stream = r.extensions["network_stream"]
        ssl_object = network_stream.get_extra_info("ssl_object")
        cert = ssl_object.getpeercert()

        TIME_FMT = "%b %d %H:%M:%S %Y %Z"
        expire_time = time.mktime(time.strptime(cert["notAfter"], TIME_FMT))

        time_left = int(expire_time - time.time())
        if time_left < 0:
            alert(f"сертификат {host} закончился {-time_left//60//60//24} дн. назад", 1)
        elif time_left < 60*60*24*days:
            alert(f"сертификат {host} закончится через {time_left//60//60//24} дн.", 1)

    except asyncio.TimeoutError as E:
        alert(f"не получилось подключиться по https к {host}: таймаут", 2)
    except Exception as E:
        err = str(E)
        if not err:
            err = type(E).__name__
        alert(f"не получилось подключиться по https к {host}: {err}", 2)


if __name__ == "__main__":
    print("MAIN")
    # asyncio.run(check_cert_expire("alexbers.com"))
    # asyncio.run(check_cert_expire("expired.badssl.com"))
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
