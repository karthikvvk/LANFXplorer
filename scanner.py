# scanner_ping_threaded.py
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "172.18.0."
THREADS = 5
START = 1
END = 254  # inclusive

def ping_range(start: int, end: int, base: str, timeout_seconds: int = 1):
    """Ping each IP in [start, end] and return list of live IPs."""
    live = []
    for i in range(start, end + 1):
        ip = f"{base}{i}"
        # Run ping; suppress output
        res = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout_seconds), ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        if res.returncode == 0:
            live.append(ip)
    return live

def chunk_ranges(start: int, end: int, parts: int):
    """Yield (chunk_start, chunk_end) pairs splitting [start,end] into parts."""
    total = end - start + 1
    base_chunk = total // parts
    remainder = total % parts
    cur = start
    for i in range(parts):
        extra = 1 if i < remainder else 0
        chunk_size = base_chunk + extra
        if chunk_size == 0:
            yield (cur, cur - 1)  # empty
        else:
            chunk_start = cur
            chunk_end = cur + chunk_size - 1
            yield (chunk_start, chunk_end)
            cur = chunk_end + 1

def gethostlist(thread_count: int = THREADS, base: str = BASE, start: int = START, end: int = END):
    ranges = list(chunk_ranges(start, end, thread_count))
    live_hosts = []

    with ThreadPoolExecutor(max_workers=thread_count) as exe:
        futures = {}
        for (s, e) in ranges:
            if s > e:
                continue
            futures[exe.submit(ping_range, s, e, base)] = (s, e)

        for fut in as_completed(futures):
            s, e = futures[fut]
            try:
                res = fut.result()
                print(f"[+] Chunk {s}-{e} -> {len(res)} live")
                live_hosts.extend(res)
            except Exception as exc:
                print(f"[-] Chunk {s}-{e} generated exception: {exc}")

    live_hosts_sorted = sorted(live_hosts, key=lambda ip: list(map(int, ip.split('.'))))
    print(f"[+] {len(live_hosts_sorted)} live hosts found")
    return live_hosts_sorted
