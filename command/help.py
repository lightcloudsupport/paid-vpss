import discord
from discord import app_commands
from discord.ext import commands

import config
from utils import embeds

PAGES = {
    "user": ("👤 User", "`/manage [vps]` — open the control panel (sent to DMs)\n`/myvps` — list your VPS\n`/help` — this menu"),
    "paid": ("💎 Paid Perks",
             "`/snapshot create|list|restore|delete` — manual snapshots\n"
             "`/portforward add|remove|list` — public ports → your VPS\n"
             "`/hostname` — custom hostname\n"
             "`/autobackup` — daily backups (last 3 kept)\n"
             "`/autorecovery` — priority auto-restart agent\n"
             "Panel extras: 🐳 Docker • 📸 Snapshots • 🔌 Port Forward • 🗓️ Auto-Backup • 💎 Plan Info"),
    "admin": ("🛡️ Admin",
              "`/admin add|remove|list` — manage admins\n"
              "`/vps create` — new paid VPS\n`/vps delete|suspend|unsuspend|extend|upgrade|transfer`\n"
              "`/vps listall` • `/vps node`"),
}


class HelpSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="Choose a category…", options=[
            discord.SelectOption(label=t.split(" ", 1)[1], value=k, emoji=t.split(" ", 1)[0]) for k, (t, _) in PAGES.items()
        ])

    async def callback(self, i: discord.Interaction):
        t, body = PAGES[self.values[0]]
        await i.response.edit_message(embed=embeds.base(f"{config.BRAND} — {t}", body))


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Show all commands")
    async def help(self, i: discord.Interaction):
        view = discord.ui.View(timeout=120)
        view.add_item(HelpSelect())
        t, body = PAGES["user"]
        await i.response.send_message(embed=embeds.base(f"{config.BRAND} — {t}", body), view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(HelpCog(bot))
