import asyncio
import time
import traceback
import contextvars
from collections import Counter, defaultdict

from config import IP_WHITELIST
from .commons import (log, prefix_to_str, prefix_to_id_to_alert, filename_to_tasks,
                      prefix_to_checks_cnt, prefix_ctx)

# metrics
tg_fails = 0
exceptions_cnt = Counter({"core": 0, "alert_sender": 0})

# prefix => {description) => value
user_metrics = defaultdict(dict)

# current metrics
new_metrics_ctx = contextvars.ContextVar("user_metrics", default=set())

START_TIME = time.time()



def metrics_precheck_hook(args_str):
    new_metrics_ctx.set(set())


def metrics_postcheck_hook():
    new_metrics = new_metrics_ctx.get()
    prefix = prefix_ctx.get()

    # unset old metrics
    user_metrics[prefix] = {k: v for k, v in user_metrics[prefix].items() if k in new_metrics}


def metric(name, value):
    new_metrics_ctx.get().add(name)
    prefix = prefix_ctx.get()
    user_metrics[prefix][name] = value


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

        active_alerts = sum(len(vals) for vals in prefix_to_id_to_alert.values())
        metrics.append(['alerts_total', "counter", "number of alerts", active_alerts])

        for prefix, count in prefix_to_checks_cnt.items():
            metrics.append(["checks", "counter", "checks counter by prefix",
                           {"prefix": prefix_to_str(prefix), "val": count}])


        for prefix, id_to_alert in prefix_to_id_to_alert.items():
            metrics.append(["alerts", "counter", "alerts counter by prefix",
                           {"prefix": prefix_to_str(prefix), "val": len(id_to_alert)}])


        for func_name, count in exceptions_cnt.items():
            metrics.append(["exceptions", "counter", "exceptions counter by function",
                           {"function": func_name, "val": count}])

        for filename, tasks in filename_to_tasks.items():
            metrics.append(["active_tasks", "counter", "tasks by filename",
                           {"filename": filename, "val": len(tasks)}])

        for prefix, name_to_val in user_metrics.items():
            for name, val in name_to_val.items():
                metrics.append(["metric", "gauge", "user metrics",
                               {"prefix": prefix_to_str(prefix), "name": name, "val": val}])

        pkt = make_metrics_pkt(metrics)

        writer.write(pkt.encode())
        await writer.drain()

    except Exception:
        traceback.print_exc()
    finally:
        writer.close()


async def start_metrics_srv():
    PORT = 9325
    if not IP_WHITELIST:
        log(f"to export metrics in the Prometheus format on port {PORT}, specify IP_WHITELIST in config.py")
        return
    await asyncio.start_server(handle_metrics, "0.0.0.0", PORT)
