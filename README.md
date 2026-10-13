<div align="center">

<img src="logo.png" alt="LightCloud" width="220">

# 💎 LightCloud — Paid VPS Bot

**A slash-command Discord bot that sells and manages LXC/LXD VPS for paid users.**
Same control panel as the free bot, plus snapshots, port forwarding, Docker, auto-backup and priority auto-recovery.

</div>

---

## ✨ Features

**Control panel** (`/manage` → sent to DMs, buttons survive bot restarts)

| Row | Buttons |
|---|---|
| 1 | 🔄 Reinstall · ▶️ Start · ⏸️ Stop · 🔁 Restart · 📊 Stats |
| 2 | 🌐 Network · 📜 Console Logs · 💾 Backup · 🔑 Password · 📁 File Manager |
| 3 | 🔐 SSH · 🌐 SSHX · 🔄 Tunnel · 🖥️ VPS Console · 🌐 cPanel |
| 4 | 🩺 AI Health · 🔁 Change Password · 🗑️ Delete VPS · 🔄 Refresh |
| 5 💎 | 📸 Snapshots · 🔌 Port Forward · 🗓️ Auto-Backup · 🐳 Docker · 💎 Plan Info |

**Paid-only perks**
- 📸 Manual snapshots (`/snapshot`) + rotating backups
- 🔌 Public port forwarding (`/portforward`) via LXD proxy devices
- 🐳 Docker / nested containers enabled out of the box
- 🗓️ Daily auto-backup (keeps last 3)
- 🧠 Priority auto-recovery agent (restarts a VPS that dies, checked every 60s)
- 🏷️ Custom hostname, ⏳ expiry reminders by DM, auto-suspend on expiry

**Admin tools**
- `/admin add` · `/admin remove` · `/admin list` — admins manage admins (owners in `.env` can't be removed)
- `/vps create | delete | suspend | unsuspend | extend | upgrade | transfer | listall | node`

## 📁 Structure

```
logo.png           project logo (also used for embeds)
main.py            bot entry (auto-loads every file in commands/)
config.py          reads .env
database.py        SQLite (admins, vps, ports)
commands/          admin.py  vps.py  paid.py  help.py  background.py
views/             panel.py (buttons + actions)  ui.py (modals / confirm)
utils/             lxc.py  provision.py  embeds.py  helpers.py
install.sh         one-shot installer + systemd service
```

## 🚀 Setup

```bash
git clone https://github.com/lightcloudsupport/paid-vpss.git
cd paid-vpss
sudo bash install.sh
nano .env                      # token, OWNER_IDS, PUBLIC_IP …
sudo systemctl start paid-vps-bot
journalctl -u paid-vps-bot -f
```

Requirements: Ubuntu/Debian host, root access, LXD (`lxc` CLI) working, Python 3.10+.
In the Discord Developer Portal invite the bot with the `applications.commands` + `bot` scopes and make sure users can receive DMs from the server.

## ⚙️ Notes

- Containers are named `PREFIX + 6 hex chars` (default `lc-xxxxxx`).
- `SSH` uses **tmate**, `SSHX` uses **sshx.io**, `Tunnel` uses **Pinggy** (`a.pinggy.io`) — the VPS needs outbound internet.
- `cPanel` shows `PANEL_URL` from `.env` (`{name}` and `{ip}` are replaced). Leave empty if you don't run one.
- Disk limits need an LXD storage pool that supports quotas (ZFS / btrfs / LVM). On a plain `dir` pool, resizing disk may fail.
- Port forwards use the range `PORT_RANGE_START–PORT_RANGE_END`; open it in your firewall.
