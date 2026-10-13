import time
from utils import lxc

SETUP = r"""export DEBIAN_FRONTEND=noninteractive
apt-get update -y >/dev/null 2>&1
apt-get install -y openssh-server openssh-client curl wget sudo nano tmate net-tools ca-certificates >/dev/null 2>&1
echo 'root:__PW__' | chpasswd
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
systemctl enable --now ssh >/dev/null 2>&1 || service ssh restart >/dev/null 2>&1
echo done
"""


async def build(name, image, cpu, ram, disk, password):
    """Create + start + provision a container. Returns (ok, ip_or_error)."""
    rc, out = await lxc.create(name, image, cpu, ram, disk)
    if rc:
        return False, out
    ip = await lxc.wait_network(name)
    if not ip:
        return False, "VPS started but never received an IP address."
    await lxc.sh(name, SETUP.replace("__PW__", password), timeout=480)
    return True, ip


async def make_snapshot(v, prefix: str):
    """prefix: 'backup' / 'auto' rotate automatically; anything else is a manual snapshot."""
    name = v["name"]
    snaps = await lxc.snapshots(name)
    if prefix in ("backup", "auto"):
        mine = [s for s in snaps if s["name"].startswith(prefix + "-")]
        keep = v["snap_limit"] if prefix == "backup" else 3
        while len(mine) >= keep:
            await lxc.lxc("delete", f"{name}/{mine.pop(0)['name']}")
        snap = f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}"
    else:
        if len(snaps) >= v["snap_limit"]:
            return False, f"Snapshot limit reached ({v['snap_limit']}). Delete one first."
        snap = prefix
    rc, out = await lxc.lxc("snapshot", name, snap, timeout=300)
    return rc == 0, (snap if rc == 0 else out)
