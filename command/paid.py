"""Paid-only slash commands: snapshots, port forwarding, hostname, auto-backup, auto-recovery."""
import random
import re
import shlex
import discord
from discord import app_commands
from discord.ext import commands

import config
from utils import lxc, embeds, provision
from utils.helpers import own_vps_ac, resolve_vps, code
from views.panel import update_panel  # noqa: F401  (kept for future use)

SNAP_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,30}$")
HOST_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")


class SnapshotCog(commands.GroupCog, name="snapshot"):
    """Snapshots of your VPS."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="create", description="Create a snapshot")
    async def create(self, i: discord.Interaction, name: str, vps: str | None = None):
        v = await resolve_vps(i, vps)
        if not v:
            return
        if not SNAP_RE.match(name) or name.startswith(("backup-", "auto-")):
            return await i.response.send_message(embed=embeds.err("Use letters/numbers/-/_ only (max 31), not starting with backup- or auto-."), ephemeral=True)
        await i.response.defer(ephemeral=True, thinking=True)
        ok, res = await provision.make_snapshot(v, name)
        await i.followup.send(embed=embeds.ok(f"Snapshot `{res}` created.") if ok else embeds.err(res), ephemeral=True)

    @app_commands.command(name="list", description="List snapshots")
    async def list(self, i: discord.Interaction, vps: str | None = None):
        v = await resolve_vps(i, vps)
        if not v:
            return
        await i.response.defer(ephemeral=True)
        snaps = await lxc.snapshots(v["name"])
        body = "\n".join(f"• `{s['name']}`" for s in snaps) or "No snapshots."
        await i.followup.send(embed=embeds.base(f"📸 {v['name']} ({len(snaps)}/{v['snap_limit']})", body), ephemeral=True)

    @app_commands.command(name="restore", description="Restore a snapshot (current data is overwritten)")
    async def restore(self, i: discord.Interaction, snapshot: str, vps: str | None = None):
        v = await resolve_vps(i, vps)
        if not v:
            return
        await i.response.defer(ephemeral=True, thinking=True)
        rc, out = await lxc.lxc("restore", v["name"], snapshot, timeout=300)
        if rc == 0 and not v["manual_stop"]:
            await lxc.lxc("start", v["name"])
        await i.followup.send(embed=embeds.ok(f"Restored `{snapshot}`.") if rc == 0 else embeds.err(code(out)), ephemeral=True)

    @app_commands.command(name="delete", description="Delete a snapshot")
    async def delete(self, i: discord.Interaction, snapshot: str, vps: str | None = None):
        v = await resolve_vps(i, vps)
        if not v:
            return
        await i.response.defer(ephemeral=True)
        rc, out = await lxc.lxc("delete", f"{v['name']}/{snapshot}")
        await i.followup.send(embed=embeds.ok(f"Deleted `{snapshot}`.") if rc == 0 else embeds.err(code(out)), ephemeral=True)

    for _fn in (create, list, restore, delete):
        _fn.autocomplete("vps")(own_vps_ac)
    del _fn

    async def _snap_ac(self, i: discord.Interaction, current: str):
        name = getattr(i.namespace, "vps", None)
        if not name:
            rows = await self.bot.db.user_vps(i.user.id)
            name = rows[0]["name"] if len(rows) == 1 else None
        v = await self.bot.db.get_vps(name) if name else None
        if not v or (v["owner_id"] != i.user.id and not await self.bot.db.is_admin(i.user.id)):
            return []
        return [app_commands.Choice(name=s["name"], value=s["name"]) for s in await lxc.snapshots(name) if current.lower() in s["name"].lower()][:25]

    @restore.autocomplete("snapshot")
    async def _ac1(self, i, current):
        return await self._snap_ac(i, current)

    @delete.autocomplete("snapshot")
    async def _ac2(self, i, current):
        return await self._snap_ac(i, current)


class PortCog(commands.GroupCog, name="portforward"):
    """Expose ports of your VPS to the internet."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="add", description="Forward a public port to a port inside your VPS")
    @app_commands.describe(private_port="Port inside your VPS", public_port="Public port (random if empty)")
    @app_commands.choices(protocol=[app_commands.Choice(name="TCP", value="tcp"), app_commands.Choice(name="UDP", value="udp")])
    async def add(self, i: discord.Interaction, private_port: app_commands.Range[int, 1, 65535],
                  public_port: app_commands.Range[int, 1024, 65535] | None = None,
                  protocol: app_commands.Choice[str] | None = None, vps: str | None = None):
        v = await resolve_vps(i, vps)
        if not v:
            return
        db, proto = self.bot.db, (protocol.value if protocol else "tcp")
        if len(await db.ports(v["name"])) >= v["port_limit"]:
            return await i.response.send_message(embed=embeds.err(f"Port limit reached ({v['port_limit']})."), ephemeral=True)
        if public_port is None:
            for _ in range(200):
                p = random.randint(config.PORT_START, config.PORT_END)
                if not await db.port_taken(p, proto):
                    public_port = p
                    break
            if public_port is None:
                return await i.response.send_message(embed=embeds.err("No free public ports."), ephemeral=True)
        elif not (config.PORT_START <= public_port <= config.PORT_END):
            return await i.response.send_message(embed=embeds.err(f"Public port must be {config.PORT_START}-{config.PORT_END}."), ephemeral=True)
        elif await db.port_taken(public_port, proto):
            return await i.response.send_message(embed=embeds.err("That public port is already used."), ephemeral=True)
        await i.response.defer(ephemeral=True, thinking=True)
        rc, out = await lxc.add_proxy(v["name"], public_port, private_port, proto)
        if rc:
            return await i.followup.send(embed=embeds.err(code(out)), ephemeral=True)
        await db.add_port(v["name"], public_port, private_port, proto)
        await i.followup.send(embed=embeds.ok(f"`{config.PUBLIC_IP}:{public_port}` → VPS `:{private_port}/{proto}`"), ephemeral=True)

    @app_commands.command(name="remove", description="Remove a forwarded port")
    @app_commands.choices(protocol=[app_commands.Choice(name="TCP", value="tcp"), app_commands.Choice(name="UDP", value="udp")])
    async def remove(self, i: discord.Interaction, public_port: int, protocol: app_commands.Choice[str] | None = None, vps: str | None = None):
        v = await resolve_vps(i, vps)
        if not v:
            return
        proto = protocol.value if protocol else "tcp"
        if not any(p["public_port"] == public_port and p["proto"] == proto for p in await self.bot.db.ports(v["name"])):
            return await i.response.send_message(embed=embeds.err("That port isn't forwarded on this VPS."), ephemeral=True)
        await i.response.defer(ephemeral=True)
        await lxc.remove_proxy(v["name"], public_port, proto)
        await self.bot.db.del_port(v["name"], public_port, proto)
        await i.followup.send(embed=embeds.ok(f"Removed `{public_port}/{proto}`."), ephemeral=True)

    @app_commands.command(name="list", description="List forwarded ports")
    async def list(self, i: discord.Interaction, vps: str | None = None):
        v = await resolve_vps(i, vps)
        if not v:
            return
        ports = await self.bot.db.ports(v["name"])
        body = "\n".join(f"`{config.PUBLIC_IP}:{p['public_port']}` → `{p['private_port']}/{p['proto']}`" for p in ports) or "None"
        await i.response.send_message(embed=embeds.base(f"🔌 Ports ({len(ports)}/{v['port_limit']})", body), ephemeral=True)

    for _fn in (add, remove, list):
        _fn.autocomplete("vps")(own_vps_ac)
    del _fn


class PaidMiscCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="hostname", description="Set a custom hostname for your VPS")
    @app_commands.autocomplete(vps=own_vps_ac)
    async def hostname(self, i: discord.Interaction, hostname: str, vps: str | None = None):
        v = await resolve_vps(i, vps)
        if not v:
            return
        hostname = hostname.lower()
        if not HOST_RE.match(hostname):
            return await i.response.send_message(embed=embeds.err("Use a-z, 0-9 and `-` (max 31)."), ephemeral=True)
        await i.response.defer(ephemeral=True)
        h = shlex.quote(hostname)
        rc, out = await lxc.sh(v["name"], f"hostnamectl set-hostname {h} 2>/dev/null || hostname {h}; echo {h} > /etc/hostname")
        if rc == 0:
            await self.bot.db.update_vps(v["name"], hostname=hostname)
        await i.followup.send(embed=embeds.ok(f"Hostname set to `{hostname}`.") if rc == 0 else embeds.err(code(out)), ephemeral=True)

    @app_commands.command(name="autobackup", description="Toggle daily automatic backups (keeps last 3)")
    @app_commands.autocomplete(vps=own_vps_ac)
    async def autobackup(self, i: discord.Interaction, enabled: bool, vps: str | None = None):
        v = await resolve_vps(i, vps)
        if not v:
            return
        await self.bot.db.update_vps(v["name"], auto_backup=int(enabled))
        await i.response.send_message(embed=embeds.ok(f"Auto-backup **{'ON' if enabled else 'OFF'}**."), ephemeral=True)

    @app_commands.command(name="autorecovery", description="Toggle the priority auto-recovery agent")
    @app_commands.autocomplete(vps=own_vps_ac)
    async def autorecovery(self, i: discord.Interaction, enabled: bool, vps: str | None = None):
        v = await resolve_vps(i, vps)
        if not v:
            return
        await self.bot.db.update_vps(v["name"], auto_restart=int(enabled))
        await i.response.send_message(embed=embeds.ok(f"Auto-recovery **{'ON' if enabled else 'OFF'}**."), ephemeral=True)


async def setup(bot):
    await bot.add_cog(SnapshotCog(bot))
    await bot.add_cog(PortCog(bot))
    await bot.add_cog(PaidMiscCog(bot))
