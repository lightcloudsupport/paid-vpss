import asyncio
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands

import config
from database import DB
from utils import embeds
from views.panel import ManageButton

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("paid-vps")


class PaidBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=commands.when_mentioned, intents=discord.Intents.default(), help_command=None)
        self.db = DB()

    async def setup_hook(self):
        await self.db.connect()
        self.add_dynamic_items(ManageButton)  # keeps panels working after restarts
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "commands")
        for f in sorted(os.listdir(base)):
            if f.endswith(".py") and not f.startswith("_"):
                await self.load_extension(f"commands.{f[:-3]}")
                log.info("Loaded commands/%s", f)
        if config.GUILD_ID:
            guild = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self):
        log.info("Logged in as %s (%s)", self.user, self.user.id)
        await self.change_presence(activity=discord.Game(name=f"💎 {config.BRAND} Paid VPS"))


bot = PaidBot()


@bot.tree.error
async def on_app_error(i: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        msg = "🚫 You don't have permission to use this command."
    else:
        log.exception("Command error", exc_info=error)
        msg = f"❌ Unexpected error: `{type(error).__name__}`"
    if i.response.is_done():
        await i.followup.send(msg, ephemeral=True)
    else:
        await i.response.send_message(msg, ephemeral=True)


if __name__ == "__main__":
    if not config.TOKEN:
        raise SystemExit("Set DISCORD_TOKEN in .env first (copy .env.example → .env)")
    bot.run(config.TOKEN)
