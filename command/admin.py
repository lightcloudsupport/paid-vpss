import time
import discord
import psutil
from discord import app_commands
from discord.ext import commands

import config
from utils import lxc, embeds, provision
from utils.helpers import gen_password, own_vps_ac, code
from views.panel import send_panel, update_panel

IMAGES = [
    app_commands.Choice(name="Ubuntu 22.04", value="images:ubuntu/22.04"),
    app_commands.Choice(name="Ubuntu 24.04", value="images:ubuntu/24.04"),
    app_commands.Choice(name="Debian 12", value="images:debian/12"),
]


async def admin_check(i: discord.Interaction) -> bool:
    if await i.client.db.is_admin(i.user.id):
        return True
    raise app_commands.CheckFailure("Admins only.")


def admin_only():
    return app_commands.check(admin_check)


class AdminCog(commands.GroupCog, name="admin"):
    """Manage who can use the admin commands."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="add", description="Make a user an admin")
    @admin_only()
    async def add(self, i: discord.Interaction, user: discord.User):
        if user.bot:
            return await i.response.send_message(embed=embeds.err("Bots can't be admins."), ephemeral=True)
        if await self.bot.db.is_admin(user.id):
            return await i.response.send_message(embed=embeds.err(f"{user.mention} is already an admin."), ephemeral=True)
        await self.bot.db.add_admin(user.id, i.user.id)
        await i.response.send_message(embed=embeds.ok(f"{user.mention} is now an admin."))

    @app_commands.command(name="remove", description="Remove a user from admins")
    @admin_only()
    async def remove(self, i: discord.Interaction, user: discord.User):
        if user.id in config.OWNER_IDS:
            return await i.response.send_message(embed=embeds.err("Owners can't be removed."), ephemeral=True)
        if not await self.bot.db.is_admin(user.id):
            return await i.response.send_message(embed=embeds.err(f"{user.mention} isn't an admin."), ephemeral=True)
        await self.bot.db.remove_admin(user.id)
        await i.response.send_message(embed=embeds.ok(f"{user.mention} is no longer an admin."))

    @app_commands.command(name="list", description="List all admins")
    @admin_only()
    async def list(self, i: discord.Interaction):
        rows = await self.bot.db.list_admins()
        lines = [f"👑 <@{o}> (owner)" for o in config.OWNER_IDS] + [f"🛡️ <@{r['user_id']}> — added by <@{r['added_by']}>" for r in rows]
        await i.response.send_message(embed=embeds.base("🛡️ Admins", "\n".join(lines) or "None"), ephemeral=True)


class VPSAdminCog(commands.GroupCog, name="vps"):
    """Admin tools for paid VPS."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="create", description="Create a paid VPS for a user")
    @app_commands.describe(user="Owner", ram="RAM in GB", cpu="vCPU cores", disk="Disk in GB", days="Duration in days (0 = lifetime)", image="OS image")
    @app_commands.choices(image=IMAGES)
    @admin_only()
    async def create(self, i: discord.Interaction, user: discord.User, ram: app_commands.Range[int, 1, 64],
                     cpu: app_commands.Range[int, 1, 32], disk: app_commands.Range[int, 5, 1000],
                     days: app_commands.Range[int, 0, 3650] = 30, image: app_commands.Choice[str] | None = None):
        await i.response.defer(ephemeral=True, thinking=True)
        db = self.bot.db
        import secrets
        name = f"{config.PREFIX}{secrets.token_hex(3)}"
        img = image.value if image else config.DEFAULT_IMAGE
        pw = gen_password()
        ok, res = await provision.build(name, img, cpu, ram, disk, pw)
        if not ok:
            await lxc.delete(name)
            return await i.followup.send(embed=embeds.err(f"Creation failed:\n{code(res)}"), ephemeral=True)
        exp = int(time.time()) + days * 86400 if days else 0
        await db.create_vps(name, user.id, ram, cpu, disk, img, pw, exp)
        v = await db.get_vps(name)
        sent = await send_panel(user, v, await lxc.info(name))
        await i.followup.send(embed=embeds.ok(
            f"VPS `{name}` created for {user.mention}\n`{ram}GB • {cpu} vCPU • {disk}GB` • {'lifetime' if not days else f'{days} days'}\n"
            f"{'📬 Panel sent to their DMs.' if sent else '⚠️ Their DMs are closed — they can run `/manage`.'}"), ephemeral=True)

    @app_commands.command(name="delete", description="Delete a VPS")
    @admin_only()
    async def delete(self, i: discord.Interaction, vps: str):
        v = await self.bot.db.get_vps(vps)
        if not v:
            return await i.response.send_message(embed=embeds.err("VPS not found."), ephemeral=True)
        await i.response.defer(ephemeral=True, thinking=True)
        await lxc.delete(vps)
        await self.bot.db.delete_vps(vps)
        await i.followup.send(embed=embeds.ok(f"`{vps}` deleted."), ephemeral=True)

    @app_commands.command(name="suspend", description="Suspend a VPS (stops it)")
    @admin_only()
    async def suspend(self, i: discord.Interaction, vps: str):
        if not await self.bot.db.get_vps(vps):
            return await i.response.send_message(embed=embeds.err("VPS not found."), ephemeral=True)
        await i.response.defer(ephemeral=True)
        await self.bot.db.update_vps(vps, suspended=1)
        await lxc.lxc("stop", vps, "--force", timeout=90)
        await i.followup.send(embed=embeds.ok(f"`{vps}` suspended."), ephemeral=True)

    @app_commands.command(name="unsuspend", description="Unsuspend and start a VPS")
    @admin_only()
    async def unsuspend(self, i: discord.Interaction, vps: str):
        if not await self.bot.db.get_vps(vps):
            return await i.response.send_message(embed=embeds.err("VPS not found."), ephemeral=True)
        await i.response.defer(ephemeral=True)
        await self.bot.db.update_vps(vps, suspended=0, manual_stop=0)
        await lxc.lxc("start", vps)
        await i.followup.send(embed=embeds.ok(f"`{vps}` unsuspended."), ephemeral=True)

    @app_commands.command(name="extend", description="Extend a VPS by N days")
    @admin_only()
    async def extend(self, i: discord.Interaction, vps: str, days: app_commands.Range[int, 1, 3650]):
        v = await self.bot.db.get_vps(vps)
        if not v:
            return await i.response.send_message(embed=embeds.err("VPS not found."), ephemeral=True)
        await i.response.defer(ephemeral=True)
        start = max(v["expires_at"], int(time.time()))
        await self.bot.db.update_vps(vps, expires_at=start + days * 86400, notified=0, suspended=0, manual_stop=0)
        if v["suspended"]:
            await lxc.lxc("start", vps)
        await i.followup.send(embed=embeds.ok(f"`{vps}` extended by **{days}** days → <t:{start + days * 86400}:F>"), ephemeral=True)

    @app_commands.command(name="upgrade", description="Change a VPS's resources")
    @admin_only()
    async def upgrade(self, i: discord.Interaction, vps: str, ram: app_commands.Range[int, 1, 64] | None = None,
                      cpu: app_commands.Range[int, 1, 32] | None = None, disk: app_commands.Range[int, 5, 1000] | None = None,
                      port_limit: app_commands.Range[int, 0, 100] | None = None, snap_limit: app_commands.Range[int, 1, 50] | None = None):
        v = await self.bot.db.get_vps(vps)
        if not v:
            return await i.response.send_message(embed=embeds.err("VPS not found."), ephemeral=True)
        await i.response.defer(ephemeral=True, thinking=True)
        upd = {}
        if ram:
            await lxc.lxc("config", "set", vps, "limits.memory", f"{ram}GB"); upd["ram_gb"] = ram
        if cpu:
            await lxc.lxc("config", "set", vps, "limits.cpu", str(cpu)); upd["cpu"] = cpu
        if disk:
            rc, out = await lxc.set_disk(vps, disk)
            if rc:
                return await i.followup.send(embed=embeds.err(f"Disk resize failed:\n{code(out)}"), ephemeral=True)
            upd["disk_gb"] = disk
        if port_limit is not None:
            upd["port_limit"] = port_limit
        if snap_limit:
            upd["snap_limit"] = snap_limit
        await self.bot.db.update_vps(vps, **upd)
        await i.followup.send(embed=embeds.ok(f"`{vps}` updated: " + (", ".join(f"{k}={x}" for k, x in upd.items()) or "nothing changed")), ephemeral=True)

    @app_commands.command(name="transfer", description="Transfer a VPS to another user")
    @admin_only()
    async def transfer(self, i: discord.Interaction, vps: str, user: discord.User):
        if not await self.bot.db.get_vps(vps):
            return await i.response.send_message(embed=embeds.err("VPS not found."), ephemeral=True)
        await self.bot.db.update_vps(vps, owner_id=user.id)
        v = await self.bot.db.get_vps(vps)
        sent = await send_panel(user, v, await lxc.info(vps))
        await i.response.send_message(embed=embeds.ok(f"`{vps}` → {user.mention}" + ("" if sent else " (DMs closed, they can use `/manage`)")), ephemeral=True)

    @app_commands.command(name="listall", description="List every paid VPS")
    @admin_only()
    async def listall(self, i: discord.Interaction):
        rows = await self.bot.db.all_vps()
        lines = [
            f"{'🟠' if r['suspended'] else '🟢'} `{r['name']}` <@{r['owner_id']}> • {r['ram_gb']}GB/{r['cpu']}c/{r['disk_gb']}GB • "
            + ("♾️" if not r["expires_at"] else f"<t:{r['expires_at']}:R>")
            for r in rows
        ]
        text = "\n".join(lines) or "No VPS yet."
        await i.response.send_message(embed=embeds.base(f"📋 Paid VPS ({len(rows)})", text[:4000]), ephemeral=True)

    @app_commands.command(name="node", description="Host machine stats")
    @admin_only()
    async def node(self, i: discord.Interaction):
        vm, du = psutil.virtual_memory(), psutil.disk_usage("/")
        rows = await self.bot.db.all_vps()
        e = embeds.base("🖧 Node Stats")
        e.add_field(name="CPU", value=f"`{psutil.cpu_percent(interval=0.5)}%` • {psutil.cpu_count()} cores")
        e.add_field(name="RAM", value=f"`{vm.used / 2**30:.1f} / {vm.total / 2**30:.1f} GB`")
        e.add_field(name="Disk", value=f"`{du.used / 2**30:.0f} / {du.total / 2**30:.0f} GB`")
        e.add_field(name="Paid VPS", value=f"`{len(rows)}` • allocated RAM `{sum(r['ram_gb'] for r in rows)} GB`")
        await i.response.send_message(embed=e, ephemeral=True)

    for _fn in (delete, suspend, unsuspend, extend, upgrade, transfer):
        _fn.autocomplete("vps")(own_vps_ac)
    del _fn


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
    await bot.add_cog(VPSAdminCog(bot))
