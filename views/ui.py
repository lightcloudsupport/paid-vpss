import discord
from utils import lxc
from utils.helpers import code


class Confirm(discord.ui.View):
    def __init__(self, uid: int):
        super().__init__(timeout=60)
        self.uid = uid
        self.value = False

    async def interaction_check(self, i: discord.Interaction) -> bool:
        return i.user.id == self.uid

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def yes(self, i: discord.Interaction, b: discord.ui.Button):
        self.value = True
        await i.response.defer()
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def no(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.defer()
        self.stop()


class PathModal(discord.ui.Modal, title="📁 File Manager"):
    path = discord.ui.TextInput(label="Directory or file path", default="/root", max_length=200)

    def __init__(self, name: str):
        super().__init__()
        self.name = name

    async def on_submit(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True, thinking=True)
        import shlex
        p = shlex.quote(self.path.value.strip())
        rc, out = await lxc.sh(self.name, f"if [ -d {p} ]; then ls -lah {p}; elif [ -f {p} ]; then head -c 1500 {p}; else echo 'Not found'; fi")
        await i.followup.send(f"📁 `{self.path.value}`\n{code(out)}", ephemeral=True)


class CmdModal(discord.ui.Modal, title="💻 VPS Console"):
    cmd = discord.ui.TextInput(label="Command to run as root", style=discord.TextStyle.paragraph, max_length=500)

    def __init__(self, name: str):
        super().__init__()
        self.name = name

    async def on_submit(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True, thinking=True)
        rc, out = await lxc.sh(self.name, self.cmd.value, timeout=45)
        await i.followup.send(f"💻 `exit {rc}`\n{code(out)}", ephemeral=True)
