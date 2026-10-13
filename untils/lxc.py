"""Thin async wrapper around the `lxc` CLI. Never uses a shell on the host."""
import asyncio
import json


async def run(*args, timeout: int = 60):
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
    except FileNotFoundError:
        return 127, f"`{args[0]}` not found on this machine"
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 124, "Timed out"
    return proc.returncode, out.decode(errors="replace").strip()


async def lxc(*args, timeout: int = 60):
    return await run("lxc", *args, timeout=timeout)


async def sh(name: str, cmd: str, timeout: int = 60):
    """Run a bash command *inside* the container."""
    return await lxc("exec", name, "--", "bash", "-c", cmd, timeout=timeout)


async def info(name: str):
    rc, out = await lxc("list", name, "--format", "json")
    if rc:
        return None
    try:
        for c in json.loads(out):
            if c.get("name") == name:
                return c
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def status(c) -> str:
    return (c or {}).get("status", "Missing")


def _state(c) -> dict:
    return (c or {}).get("state") or {}


def ipv4(c):
    for dev, d in (_state(c).get("network") or {}).items():
        if dev == "lo":
            continue
        for a in d.get("addresses", []):
            if a.get("family") == "inet" and a.get("scope") == "global":
                return a["address"]
    return None


def mem_used_mb(c) -> float:
    return (_state(c).get("memory") or {}).get("usage", 0) / 1048576


def disk_used_gb(c) -> float:
    return ((_state(c).get("disk") or {}).get("root") or {}).get("usage", 0) / 1073741824


def cpu_seconds(c) -> float:
    return (_state(c).get("cpu") or {}).get("usage", 0) / 1e9


def procs(c) -> int:
    return _state(c).get("processes", 0)


async def wait_network(name: str, tries: int = 40):
    for _ in range(tries):
        ip = ipv4(await info(name))
        if ip:
            return ip
        await asyncio.sleep(2)
    return None


async def set_disk(name: str, gb: int):
    rc, out = await lxc("config", "device", "override", name, "root", f"size={gb}GB")
    if rc:
        rc, out = await lxc("config", "device", "set", name, "root", f"size={gb}GB")
    return rc, out


async def create(name: str, image: str, cpu: int, ram_gb: int, disk_gb: int):
    rc, out = await lxc("init", image, name, timeout=900)
    if rc:
        return rc, out
    await lxc("config", "set", name, "limits.cpu", str(cpu))
    await lxc("config", "set", name, "limits.memory", f"{ram_gb}GB")
    # paid perk: nested containers / Docker out of the box
    await lxc("config", "set", name, "security.nesting", "true")
    await lxc("config", "set", name, "security.syscalls.intercept.mknod", "true")
    await lxc("config", "set", name, "security.syscalls.intercept.setxattr", "true")
    await set_disk(name, disk_gb)
    return await lxc("start", name)


async def delete(name: str):
    await lxc("stop", name, "--force", timeout=60)
    return await lxc("delete", name, "--force", timeout=120)


async def snapshots(name: str):
    rc, out = await lxc("query", f"/1.0/instances/{name}/snapshots?recursion=1")
    if rc:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    snaps = [{"name": s["name"].split("/")[-1], "created_at": s.get("created_at", "")} for s in data]
    return sorted(snaps, key=lambda s: s["created_at"])


async def add_proxy(name: str, pub: int, priv: int, proto: str):
    return await lxc(
        "config", "device", "add", name, f"pf-{proto}-{pub}", "proxy",
        f"listen={proto}:0.0.0.0:{pub}", f"connect={proto}:127.0.0.1:{priv}",
    )


async def remove_proxy(name: str, pub: int, proto: str):
    return await lxc("config", "device", "remove", name, f"pf-{proto}-{pub}")
