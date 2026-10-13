import discord
from discord import app_commands
from discord.ext import commands

from utils import lxc, embeds
from utils.helpers import own_vps_ac, resolve_vps, expiry_text
from views.panel import send_panel


class UserCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="manage", description="Open the control panel for your VPS (sent to your DMs)")
    @app_commands.autocomplete(vps=own_vps_ac)
    async def manage(self, i: discord.Interaction, vps: str | None = None):
        v = await resolve_vps(i, vps)
        if not v:
            return
        await i.response.defer(ephemeral=True)
        c = await lxc.info(v["name"])
        if await send_panel(i.user, v, c):
            return await i.followup.send(embed=embeds.ok("📬 Control panel sent to your DMs."), ephemeral=True)
        from views.panel import panel_view
        await i.followup.send(embed=embeds.panel(v, c), view=panel_view(v["name"]), ephemeral=True)

    @app_commands.command(name="myvps", description="List your VPS")
    async def myvps(self, i: discord.Interaction):
        rows = await self.bot.db.user_vps(i.user.id)
        if not rows:
            return await i.response.send_message(embed=embeds.err("You don't have any paid VPS."), ephemeral=True)
        await i.response.defer(ephemeral=True)
        lines = []
        for r in rows:
            st = "🟠 Suspended" if r["suspended"] else ("🟢 Running" if lxc.status(await lxc.info(r["name"])) == "Running" else "🔴 Stopped")
            lines.append(f"**{r['name']}** — {st}\n`{r['ram_gb']}GB • {r['cpu']} vCPU • {r['disk_gb']}GB` • Expires {expiry_text(r)}")
        await i.followup.send(embed=embeds.base("💎 Your Paid VPS", "\n\n".join(lines)), ephemeral=True)


async def setup(bot):
    await bot.add_cog(UserCog(bot))
