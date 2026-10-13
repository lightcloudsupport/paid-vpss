import re
import secrets
import string
import time
import discord
from discord import app_commands

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{2,30}$")


def gen_password(n: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


def code(text: str, limit: int = 1800, lang: str = "") -> str:
    text = (text or "(no output)").replace("```", "'''")
    if len(text) > limit:
        text = "…" + text[-limit:]
    return f"```{lang}\n{text}\n```"


def ago(ts: int) -> str:
    if not ts:
        return "never"
    s = int(time.time()) - ts
    if s < 60:
        return f"{s}s ago"
    if s < 3600:
        return f"{s // 60}m ago"
    if s < 86400:
        return f"{s // 3600}h ago"
    return f"{s // 86400}d ago"


def expiry_text(v) -> str:
    if not v["expires_at"]:
        return "♾️ Lifetime"
    return f"<t:{v['expires_at']}:R> (<t:{v['expires_at']}:d>)"


async def can_access(interaction: discord.Interaction, v) -> bool:
    if v is None:
        return False
    if interaction.user.id == v["owner_id"]:
        return True
    return await interaction.client.db.is_admin(interaction.user.id)


async def own_vps_ac(interaction: discord.Interaction, current: str):
    db = interaction.client.db
    rows = await db.all_vps() if await db.is_admin(interaction.user.id) else await db.user_vps(interaction.user.id)
    cur = current.lower()
    return [
        app_commands.Choice(name=f"{r['name']} ({r['ram_gb']}GB/{r['cpu']}vCPU)"[:100], value=r["name"])
        for r in rows if cur in r["name"].lower()
    ][:25]


async def resolve_vps(interaction: discord.Interaction, name):
    """Pick the VPS a slash command targets. Returns row or None (already replied)."""
    db = interaction.client.db
    if name:
        v = await db.get_vps(name)
        if not await can_access(interaction, v):
            await interaction.response.send_message("❌ VPS not found or it isn't yours.", ephemeral=True)
            return None
        return v
    rows = await db.user_vps(interaction.user.id)
    if len(rows) == 1:
        return rows[0]
    msg = "❌ You don't have any VPS." if not rows else "❓ You have multiple VPS — pick one in the `vps` option."
    await interaction.response.send_message(msg, ephemeral=True)
    return None
