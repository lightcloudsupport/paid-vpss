import re
import time
import discord
import config
from utils import lxc, embeds, provision
from utils.helpers import code, gen_password, can_access, expiry_text, ago
from views.ui import Confirm, PathModal, CmdModal

S = discord.ButtonStyle
# action, label, emoji, style, row
BUTTONS = [
    ("reinstall", "Reinstall", "🔄", S.danger, 0), ("start", "Start", "▶️", S.success, 0),
    ("stop", "Stop", "⏸️", S.secondary, 0), ("restart", "Restart", "🔁", S.primary, 0),
    ("stats", "Stats", "📊", S.secondary, 0),
    ("network", "Network", "🌐", S.primary, 1), ("logs", "Console Logs", "📜", S.secondary, 1),
    ("backup", "Backup", "💾", S.success, 1), ("password", "Password", "🔑", S.primary, 1),
    ("files", "File Manager", "📁", S.primary, 1),
    ("ssh", "SSH", "🔐", S.primary, 2), ("sshx", "SSHX", "🌐", S.primary, 2),
    ("tunnel", "Tunnel", "🔄", S.primary, 2), ("console", "VPS Console", "🖥️", S.primary, 2),
    ("cpanel", "cPanel", "🌐", S.secondary, 2),
    ("health", "AI Health", "🩺", S.success, 3), ("chpass", "Change Password", "🔁", S.primary, 3),
    ("delete", "Delete VPS", "🗑️", S.danger, 3), ("refresh", "Refresh", "🔄", S.secondary, 3),
    # ── paid-only row ──
    ("snapshots", "Snapshots", "📸", S.primary, 4), ("ports", "Port Forward", "🔌", S.primary, 4),
    ("autobackup", "Auto-Backup", "🗓️", S.secondary, 4), ("docker", "Docker", "🐳", S.primary, 4),
    ("plan", "Plan Info", "💎", S.secondary, 4),
]
SPEC = {b[0]: b for b in BUTTONS}
NO_DEFER = {"files", "console", "delete", "reinstall"}
ALLOWED_WHEN_SUSPENDED = {"refresh", "plan", "password"}


def panel_view(name: str) -> discord.ui.View:
    v = discord.ui.View(timeout=None)
    for a, *_ in BUTTONS:
        v.add_item(ManageButton(a, name))
    return v


async def send_panel(user: discord.abc.User, v, c) -> bool:
    try:
        await user.send(embed=embeds.panel(v, c), view=panel_view(v["name"]))
        return True
    except discord.HTTPException:
        return False


async def update_panel(i: discord.Interaction, name: str):
    db = i.client.db
    v = await db.get_vps(name)
    if not v or not i.message:
        return
    try:
        await i.message.edit(embed=embeds.panel(v, await lxc.info(name)), view=panel_view(name))
    except discord.HTTPException:
        pass


class ManageButton(discord.ui.DynamicItem[discord.ui.Button], template=r"lc:(?P<action>[a-z]+):(?P<vps>[a-z0-9-]+)"):
    def __init__(self, action: str, vps: str):
        _, label, emoji, style, row = SPEC[action]
        super().__init__(discord.ui.Button(label=label, emoji=emoji, style=style, row=row, custom_id=f"lc:{action}:{vps}"))
        self.action, self.vps = action, vps

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        if match["action"] not in SPEC:
            raise ValueError("unknown action")
        return cls(match["action"], match["vps"])

    async def interaction_check(self, i: discord.Interaction) -> bool:
        v = await i.client.db.get_vps(self.vps)
        if not v:
            await i.response.send_message("❌ This VPS no longer exists.", ephemeral=True)
            return False
        if not await can_access(i, v):
            await i.response.send_message("❌ This isn't your VPS.", ephemeral=True)
            return False
        if v["suspended"] and self.action not in ALLOWED_WHEN_SUSPENDED:
            await i.response.send_message("🟠 This VPS is suspended/expired. Contact staff to renew.", ephemeral=True)
            return False
        return True

    async def callback(self, i: discord.Interaction):
        v = await i.client.db.get_vps(self.vps)
        if self.action not in NO_DEFER:
            await i.response.defer(ephemeral=self.action != "refresh", thinking=self.action != "refresh")
        try:
            await ACTIONS[self.action](i, v)
        except Exception as e:  # keep the panel alive no matter what
            msg = f"❌ Something went wrong: `{type(e).__name__}: {e}`"
            if i.response.is_done():
                await i.followup.send(msg, ephemeral=True)
            else:
                await i.response.send_message(msg, ephemeral=True)


# ───────────────────────── actions ─────────────────────────
async def say(i, text=None, **kw):
    await i.followup.send(text, ephemeral=True, **kw)


async def a_start(i, v):
    rc, out = await lxc.lxc("start", v["name"])
    await i.client.db.update_vps(v["name"], manual_stop=0)
    await say(i, "✅ VPS started." if rc == 0 else f"❌ {code(out)}")
    await update_panel(i, v["name"])


async def a_stop(i, v):
    await i.client.db.update_vps(v["name"], manual_stop=1)
    rc, out = await lxc.lxc("stop", v["name"], "--force", timeout=90)
    await say(i, "⏸️ VPS stopped." if rc == 0 else f"❌ {code(out)}")
    await update_panel(i, v["name"])


async def a_restart(i, v):
    rc, out = await lxc.lxc("restart", v["name"], "--force", timeout=120)
    await i.client.db.update_vps(v["name"], manual_stop=0)
    await say(i, "🔁 VPS restarted." if rc == 0 else f"❌ {code(out)}")
    await update_panel(i, v["name"])


async def a_refresh(i, v):
    await update_panel(i, v["name"])


async def _running(i, v):
    c = await lxc.info(v["name"])
    if lxc.status(c) != "Running":
        await say(i, "⚠️ Your VPS is not running. Press **Start** first.")
        return None
    return c


async def a_stats(i, v):
    c = await _running(i, v)
    if not c:
        return
    rc, up = await lxc.sh(v["name"], "uptime -p; cut -d' ' -f1-3 /proc/loadavg")
    e = embeds.base("📊 VPS Stats")
    e.add_field(name="🧠 RAM", value=f"`{lxc.mem_used_mb(c):.0f} MB / {v['ram_gb'] * 1024} MB`")
    e.add_field(name="💽 Disk", value=f"`{lxc.disk_used_gb(c):.2f} GB / {v['disk_gb']} GB`")
    e.add_field(name="⚙️ CPU time", value=f"`{lxc.cpu_seconds(c):.0f}s` • {v['cpu']} vCPU")
    e.add_field(name="📋 Processes", value=f"`{lxc.procs(c)}`")
    e.add_field(name="⏱️ Uptime / Load", value=code(up, 300))
    await say(i, embed=e)


async def a_network(i, v):
    c = await lxc.info(v["name"])
    ports = await i.client.db.ports(v["name"])
    lines = "\n".join(f"`{config.PUBLIC_IP}:{p['public_port']}` → `{p['private_port']}/{p['proto']}`" for p in ports) or "None — use `/portforward add`"
    e = embeds.base("🌐 Network")
    e.add_field(name="Internal IPv4", value=f"`{lxc.ipv4(c) or '—'}`", inline=False)
    e.add_field(name="Hostname", value=f"`{v['hostname'] or v['name']}`", inline=False)
    e.add_field(name=f"Port forwards ({len(ports)}/{v['port_limit']})", value=lines, inline=False)
    await say(i, embed=e)


async def a_logs(i, v):
    rc, out = await lxc.lxc("console", v["name"], "--show-log")
    if rc or not out.strip():
        rc, out = await lxc.sh(v["name"], "journalctl -n 40 --no-pager 2>&1 || dmesg | tail -n 40")
    await say(i, "📜 **Console Logs**\n" + code(out))


async def a_backup(i, v):
    ok, res = await provision.make_snapshot(v, "backup")
    await i.client.db.update_vps(v["name"], last_backup=int(time.time())) if ok else None
    await say(i, f"💾 Backup created: `{res}`" if ok else f"❌ {code(res)}")


async def a_password(i, v):
    await say(i, f"🔑 **Root login**\nUser: `root`\nPassword: ||`{v['root_password']}`||")


async def a_chpass(i, v):
    c = await _running(i, v)
    if not c:
        return
    pw = gen_password()
    rc, out = await lxc.sh(v["name"], f"echo 'root:{pw}' | chpasswd")
    if rc:
        return await say(i, f"❌ {code(out)}")
    await i.client.db.update_vps(v["name"], root_password=pw)
    await say(i, f"🔁 New root password: ||`{pw}`||")


async def a_files(i, v):
    await i.response.send_modal(PathModal(v["name"]))


async def a_console(i, v):
    await i.response.send_modal(CmdModal(v["name"]))


async def a_ssh(i, v):
    if not await _running(i, v):
        return
    await say(i, "⏳ Starting SSH session (up to 60s)…")
    cmd = (
        "command -v tmate >/dev/null || (apt-get update -y >/dev/null 2>&1 && apt-get install -y tmate >/dev/null 2>&1); "
        "pkill tmate 2>/dev/null; rm -f /tmp/tmate.sock; "
        "tmate -S /tmp/tmate.sock new-session -d && tmate -S /tmp/tmate.sock wait tmate-ready && "
        "tmate -S /tmp/tmate.sock display -p '#{tmate_ssh}'"
    )
    rc, out = await lxc.sh(v["name"], cmd, timeout=90)
    await say(i, f"🔐 **SSH**\n{code(out.splitlines()[-1] if out else out, 300)}" if rc == 0 else f"❌ {code(out)}")


async def a_sshx(i, v):
    if not await _running(i, v):
        return
    await say(i, "⏳ Starting SSHX (up to 30s)…")
    cmd = (
        "pkill sshx 2>/dev/null; "
        "nohup sh -c 'curl -sSf https://sshx.io/get | sh -s run' >/tmp/sshx.log 2>&1 & "
        "sleep 12; grep -o 'https://sshx.io/s/[^ ]*' /tmp/sshx.log | head -1"
    )
    rc, out = await lxc.sh(v["name"], cmd, timeout=60)
    await say(i, f"🌐 **SSHX link:** {out}" if out.startswith("https://") else f"❌ Couldn't get a link.\n{code(out)}")


async def a_tunnel(i, v):
    if not await _running(i, v):
        return
    await say(i, "⏳ (Re)connecting tunnel…")
    cmd = (
        "pkill -f a.pinggy.io 2>/dev/null; "
        "nohup ssh -tt -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -p 443 -R0:localhost:22 tcp@a.pinggy.io >/tmp/tunnel.log 2>&1 & "
        "sleep 10; grep -o 'tcp://[^ ]*' /tmp/tunnel.log | head -1 | tr -d '\\r'"
    )
    rc, out = await lxc.sh(v["name"], cmd, timeout=60)
    m = re.match(r"tcp://([^:\s]+):(\d+)", out)
    if not m:
        return await say(i, f"❌ Tunnel failed.\n{code(out)}")
    ssh = f"ssh root@{m[1]} -p {m[2]}"
    await i.client.db.update_vps(v["name"], tunnel=f"{m[1]}:{m[2]}")
    await say(i, f"🔌 **Tunnel connected**\n{code(ssh, 300)}")
    await update_panel(i, v["name"])


async def a_cpanel(i, v):
    c = await lxc.info(v["name"])
    if config.PANEL_URL:
        url = config.PANEL_URL.format(name=v["name"], ip=lxc.ipv4(c) or "")
        return await say(i, f"🌐 **Panel:** {url}")
    await say(i, "🌐 No panel URL is configured by staff yet.\nTip: install any web panel in your VPS and expose it with **Port Forward** (`/portforward add`).")


async def a_health(i, v):
    name = v["name"]
    c = await lxc.info(name)
    repaired = []
    if lxc.status(c) != "Running":
        await lxc.lxc("start", name)
        await i.client.db.update_vps(name, manual_stop=0)
        repaired.append("Started stopped VPS")
        await lxc.wait_network(name, 15)
    score, rows = 100, []
    _, load = await lxc.sh(name, "cut -d' ' -f1 /proc/loadavg")
    _, ram = await lxc.sh(name, r"""free | awk '/Mem:/ {printf "%d", $3*100/$2}'""")
    _, dsk = await lxc.sh(name, r"""df / | awk 'NR==2 {gsub("%",""); print $5}'""")
    _, ssh = await lxc.sh(name, "systemctl is-active ssh || systemctl is-active sshd")
    _, net = await lxc.sh(name, "ping -c1 -W2 1.1.1.1 >/dev/null 2>&1 && echo ok || echo fail")
    try:
        if float(load) > v["cpu"] * 1.5:
            score -= 15
        rows.append(f"⚙️ Load: `{load}`")
    except ValueError:
        score -= 30
    for lbl, val in (("🧠 RAM", ram), ("💽 Disk", dsk)):
        if val.isdigit():
            rows.append(f"{lbl}: `{val}%`")
            if int(val) > 90:
                score -= 15
        else:
            score -= 20
    if "active" not in ssh.split("\n")[0] or ssh.startswith("inactive"):
        await lxc.sh(name, "systemctl restart ssh || systemctl restart sshd", timeout=30)
        repaired.append("Restarted SSH service")
        score -= 10
    rows.append(f"🔐 SSH: `{ssh.splitlines()[0] if ssh else '?'}`")
    if net != "ok":
        await lxc.lxc("restart", name, "--force", timeout=120)
        repaired.append("Restarted VPS (no network)")
        score -= 20
    rows.append(f"🌍 Internet: `{net}`")
    if repaired:
        await i.client.db.update_vps(name, last_repair=int(time.time()))
    score = max(score, 0)
    color = 0x2ECC71 if score >= 80 else 0xF1C40F if score >= 50 else 0xE74C3C
    e = embeds.base(f"🩺 AI Health — {score}/100", "\n".join(rows), color)
    e.add_field(name="🛠️ Auto-repair", value="\n".join(f"• {r}" for r in repaired) or "Nothing needed ✅", inline=False)
    await say(i, embed=e)
    await update_panel(i, name)


async def a_snapshots(i, v):
    snaps = await lxc.snapshots(v["name"])
    body = "\n".join(f"• `{s['name']}`" for s in snaps) or "No snapshots yet."
    await say(i, embed=embeds.base(f"📸 Snapshots ({len(snaps)}/{v['snap_limit']})", body + "\n\nManage with `/snapshot create|restore|delete`"))


async def a_ports(i, v):
    await a_network(i, v)


async def a_autobackup(i, v):
    new = 0 if v["auto_backup"] else 1
    await i.client.db.update_vps(v["name"], auto_backup=new)
    await say(i, f"🗓️ Daily auto-backup is now **{'ON' if new else 'OFF'}** (keeps the last 3).")
    await update_panel(i, v["name"])


async def a_docker(i, v):
    name = v["name"]
    await say(i, "🐳 Enabling Docker support… this can take a few minutes.")
    for k in ("security.nesting", "security.syscalls.intercept.mknod", "security.syscalls.intercept.setxattr"):
        await lxc.lxc("config", "set", name, k, "true")
    await lxc.lxc("restart", name, "--force", timeout=120)
    if not await lxc.wait_network(name):
        return await say(i, "❌ VPS didn't come back with network.")
    rc, out = await lxc.sh(name, "command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh; systemctl enable --now docker; docker --version", timeout=420)
    await say(i, f"{'✅' if rc == 0 else '❌'} Docker\n{code(out, 500)}")


async def a_plan(i, v):
    e = embeds.base("💎 Paid Plan")
    e.add_field(name="Resources", value=f"`{v['ram_gb']}GB RAM • {v['cpu']} vCPU • {v['disk_gb']}GB`", inline=False)
    e.add_field(name="Expires", value=expiry_text(v))
    e.add_field(name="Limits", value=f"Ports: `{v['port_limit']}` • Snapshots: `{v['snap_limit']}`")
    e.add_field(name="Perks", value="Docker/nesting • Port forwarding • Snapshots • Daily auto-backup • Priority auto-recovery • Custom hostname", inline=False)
    await say(i, embed=e)


async def a_delete(i, v):
    view = Confirm(i.user.id)
    await i.response.send_message(f"⚠️ Permanently delete **{v['name']}** and all its data?", view=view, ephemeral=True)
    await view.wait()
    if not view.value:
        return await i.edit_original_response(content="Cancelled.", view=None)
    await i.edit_original_response(content="🗑️ Deleting…", view=None)
    await lxc.delete(v["name"])
    await i.client.db.delete_vps(v["name"])
    await i.edit_original_response(content=f"🗑️ `{v['name']}` deleted.")
    if i.message:
        try:
            await i.message.edit(embed=embeds.err(f"`{v['name']}` was deleted."), view=None)
        except discord.HTTPException:
            pass


async def a_reinstall(i, v):
    view = Confirm(i.user.id)
    await i.response.send_message(f"⚠️ Reinstall **{v['name']}**? ALL data and snapshots will be wiped.", view=view, ephemeral=True)
    await view.wait()
    if not view.value:
        return await i.edit_original_response(content="Cancelled.", view=None)
    await i.edit_original_response(content="🔄 Reinstalling… (several minutes)", view=None)
    db, name = i.client.db, v["name"]
    await lxc.delete(name)
    pw = gen_password()
    ok, res = await provision.build(name, v["image"], v["cpu"], v["ram_gb"], v["disk_gb"], pw)
    if not ok:
        return await i.edit_original_response(content=f"❌ Reinstall failed:\n{code(res)}")
    await db.update_vps(name, root_password=pw, tunnel=None, manual_stop=0)
    for p in await db.ports(name):
        await lxc.add_proxy(name, p["public_port"], p["private_port"], p["proto"])
    await i.edit_original_response(content=f"✅ Reinstalled! New root password: ||`{pw}`||")
    await update_panel(i, name)


ACTIONS = {
    "start": a_start, "stop": a_stop, "restart": a_restart, "refresh": a_refresh, "stats": a_stats,
    "network": a_network, "logs": a_logs, "backup": a_backup, "password": a_password, "chpass": a_chpass,
    "files": a_files, "console": a_console, "ssh": a_ssh, "sshx": a_sshx, "tunnel": a_tunnel,
    "cpanel": a_cpanel, "health": a_health, "snapshots": a_snapshots, "ports": a_ports,
    "autobackup": a_autobackup, "docker": a_docker, "plan": a_plan, "delete": a_delete, "reinstall": a_reinstall,
}
