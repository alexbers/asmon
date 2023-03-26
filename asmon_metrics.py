import asyncio
import time
import traceback
from collections import Counter

from asmon_core import filename_to_tasks, prefix_to_checks_cnt

from config import IP_WHITELIST

START_TIME = time.time()

# Metrics
exceptions_cnt = Counter({"core": 0, "alert_sender": 0})
tg_fails = 0


def prefix_to_str(prefix):
    if len(prefix) == 3 and not prefix[2]:
        return f"{prefix[0]}:{prefix[1]}"
    return f"{prefix[0]}:{prefix[1]}:{prefix[2]}"


def make_metrics_pkt(metrics):
    pkt_body_list = []
    used_names = set()

    for name, m_type, desc, val in metrics:
        name = "asmon_" + name
        if name not in used_names:
            pkt_body_list.append(f"# HELP {name} {desc}")
            pkt_body_list.append(f"# TYPE {name} {m_type}")
            used_names.add(name)

        if isinstance(val, dict):
            tags = []
            for tag, tag_val in val.items():
                if tag == "val":
                    continue
                tag_val = tag_val.replace('"', r'\"')
                tags.append(f'{tag}="{tag_val}"')
            pkt_body_list.append(f"{name}{{{','.join(tags)}}} {val['val']}")
        else:
            pkt_body_list.append(f"{name} {val}")
    pkt_body = "\n".join(pkt_body_list) + "\n"

    # pkt_body = "\n".join(map(str,asyncio.all_tasks())) + pkt_body

    pkt_header_list = []
    pkt_header_list.append("HTTP/1.1 200 OK")
    pkt_header_list.append("Connection: close")
    pkt_header_list.append(f"Content-Length: {len(pkt_body)}")
    pkt_header_list.append("Content-Type: text/plain; version=0.0.4; charset=utf-8")
    pkt_header_list.append("Date: " + time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime()))

    pkt_header = "\r\n".join(pkt_header_list)

    pkt = pkt_header + "\r\n\r\n" + pkt_body
    return pkt


async def handle_metrics(reader, writer):
    request = await reader.read(1024)

    client_ip = writer.get_extra_info("peername")[0]
    if IP_WHITELIST and client_ip not in IP_WHITELIST:
        writer.close()
        return

    try:
        metrics = []
        metrics.append(["uptime", "counter", "asmon uptime", time.time() - START_TIME])
        metrics.append(["tg_fails", "counter", "tg send fails", tg_fails])
        metrics.append(["tasks", "counter", "number of tasks", len(asyncio.all_tasks())])
        metrics.append(['checks_total', "counter", "number of checks", sum(prefix_to_checks_cnt.values())])

        for prefix, count in prefix_to_checks_cnt.items():
            metrics.append(["checks", "counter", "checks counter",
                           {"prefix": prefix_to_str(prefix), "val": count}])

        for func_name, count in exceptions_cnt.items():
            metrics.append(["exceptions", "counter", "exceptions counter",
                           {"function": func_name, "val": count}])

        for filename, tasks in filename_to_tasks.items():
            metrics.append(["active_tasks", "counter", "tasks per file",
                           {"filename": func_name, "val": len(tasks)}])

        pkt = make_metrics_pkt(metrics)

        writer.write(pkt.encode())
        await writer.drain()

    except Exception:
        traceback.print_exc()
    finally:
        writer.close()


async def start_metrics_srv():
    await asyncio.start_server(handle_metrics, "0.0.0.0", 9325)
