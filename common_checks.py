# This file contains implementation of some common checks
# Use it as examples to develop your own
# If you edit this file, it will be not autoreloaded

import asyncio
import time

from asmon import alert


async def wait_for_with_attempts(task, timeout, attempts):
    for attempt in range(attempts):
        try:
            return await asyncio.wait_for(task, timeout=timeout)
        except TimeoutError:
            if attempt == attempts - 1:
                raise


async def check_tcp_port(host, port, timeout=10, attempts=30):
    writer = None
    try:
        reader, writer = await wait_for_with_attempts(
            asyncio.open_connection(host, port), timeout=timeout, attempts=attempts)
    except (OSError, TimeoutError, asyncio.exceptions.TimeoutError) as E:
        err = str(E)
        if not err:
            err = type(E).__name__
        alert(f"port {port} on host {host} is unreachable: {err}")
    finally:
        if writer:
            writer.close()


async def check_cert_expire(host, port=443, days=7, timeout=10, attempts=30):
    writer = None
    try:
        reader, writer = await wait_for_with_attempts(
            asyncio.open_connection(
                host, port, ssl=True, server_hostname=host, limit=4096), timeout=timeout, attempts=attempts)
        ssl_object = writer.get_extra_info("ssl_object")
        cert = ssl_object.getpeercert()

        TIME_FMT = "%b %d %H:%M:%S %Y %Z"
        expire_time = time.mktime(time.strptime(cert["notAfter"], TIME_FMT))

        days_left = (expire_time - time.time())/60/60/24
        if days_left < days:
            alert(f"certificate on {host} will expire in {time_left//60//60//24} days", 1)
        return days_left

    except (OSError, TimeoutError, asyncio.exceptions.TimeoutError) as E:
        err = str(E)
        if not err:
            err = type(E).__name__
        alert(f"port {port} on host {host} is unreachable: {err}")
    finally:
        if writer:
            writer.close()


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