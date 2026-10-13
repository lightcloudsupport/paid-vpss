import discord
import config
from utils import lxc
from utils.helpers import ago, expiry_text


def base(title: str, desc: str = "", color: int | None = None) -> discord.Embed:
    e = discord.Embed(title=title, description=desc, color=color or config.COLOR)
    e.set_footer(text=f"✨ {config.BRAND} • {config.VERSION}")
    if config.LOGO_URL:
        e.set_thumbnail(url=config.LOGO_URL)
    return e


def ok(msg: str) -> discord.Embed:
    return base("✅ Success", msg)


def err(msg: str) -> discord.Embed:
    return base("❌ Error", msg, 0xE74C3C)


def panel(v, c) -> discord.Embed:
    st = lxc.status(c)
    if v["suspended"]:
        color, dot, label = 0xE67E22, "🟠", "Suspended"
    elif st == "Running":
        color, dot, label = 0x2ECC71, "🟢", "Running"
    else:
        color, dot, label = 0xE74C3C, "🔴", st
    ip = lxc.ipv4(c) or "—"
    tunnel = v["tunnel"] or "not connected"
    e = discord.Embed(title=f"🖥️ {v['name']}", color=color)
    e.description = (
        f"{dot} **Status:** {label}\n"
        f"💎 **Plan:** Paid • ⏳ Expires: {expiry_text(v)}\n"
        f"🧩 **Specs:** `{v['ram_gb']} GB RAM` • `{v['cpu']} vCPU` • `{v['disk_gb']} GB Disk`\n"
        f"🌐 **Internal IP:** `{ip}`\n"
        f"🔌 **Tunnel:** `{tunnel}`\n"
        f"(Click 🔄 **Tunnel** to reconnect if disconnected)\n\n"
        f"➤ 🧠 **{config.BRAND} AI Protection**\n"
        f"{'🟢 Priority auto-recovery agent enabled' if v['auto_restart'] else '🔴 Auto-recovery disabled'}\n"
        f"Last repair attempt: `{ago(v['last_repair'])}`\n"
        f"Auto-backup: {'🟢 daily' if v['auto_backup'] else '⚪ off'}\n\n"
        f"➤ 🎮 **Controls**\n"
        f"Use the buttons below to manage your VPS"
    )
    e.set_footer(text=f"✨ {config.BRAND} • {config.VERSION}")
    e.timestamp = discord.utils.utcnow()
    if config.LOGO_URL:
        e.set_thumbnail(url=config.LOGO_URL)
    return e
