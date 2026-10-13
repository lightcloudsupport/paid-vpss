"""Background services: auto-recovery, expiry handling, daily auto-backups."""
import time
import discord
from discord.ext import commands, tasks

import config
from utils import lxc, provision


class Background(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.recovery.start()
        self.expiry.start()
        self.autobackup.start()

    def cog_unload(self):
        self.recovery.cancel()
        self.expiry.cancel()
        self.autobackup.cancel()

    async def dm(self, uid: int, text: str):
        try:
            user = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
            await user.send(text)
        except discord.HTTPException:
            pass

    # Priority auto-recovery: restart VPS that stopped without the owner asking.
    @tasks.loop(seconds=60)
    async def recovery(self):
        for v in await self.bot.db.all_vps():
            if v["suspended"] or v["manual_stop"] or not v["auto_restart"]:
                continue
            c = await lxc.info(v["name"])
            if c and lxc.status(c) == "Stopped":
                rc, _ = await lxc.lxc("start", v["name"])
                if rc == 0:
                    await self.bot.db.update_vps(v["name"], last_repair=int(time.time()))

    @tasks.loop(minutes=10)
    async def expiry(self):
        now = int(time.time())
        for v in await self.bot.db.all_vps():
            if not v["expires_at"] or v["suspended"]:
                continue
            left = v["expires_at"] - now
            if left <= 0:
                await self.bot.db.update_vps(v["name"], suspended=1)
                await lxc.lxc("stop", v["name"], "--force", timeout=90)
                await self.dm(v["owner_id"], f"🟠 Your VPS **{v['name']}** has expired and was suspended. Contact staff to renew — your data is kept for now.")
            elif left < 86400 and v["notified"] < 2:
                await self.bot.db.update_vps(v["name"], notified=2)
                await self.dm(v["owner_id"], f"⏰ Your VPS **{v['name']}** expires in less than 24 hours (<t:{v['expires_at']}:R>).")
            elif left < 3 * 86400 and v["notified"] < 1:
                await self.bot.db.update_vps(v["name"], notified=1)
                await self.dm(v["owner_id"], f"⏳ Your VPS **{v['name']}** expires <t:{v['expires_at']}:R>. Renew to avoid downtime.")

    @tasks.loop(hours=1)
    async def autobackup(self):
        now = int(time.time())
        for v in await self.bot.db.all_vps():
            if v["auto_backup"] and not v["suspended"] and now - v["last_backup"] >= 86400:
                ok, _ = await provision.make_snapshot(v, "auto")
                if ok:
                    await self.bot.db.update_vps(v["name"], last_backup=now)

    @recovery.before_loop
    @expiry.before_loop
    @autobackup.before_loop
    async def _wait(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Background(bot))
