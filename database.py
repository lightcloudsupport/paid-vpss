import os
import time
import aiosqlite
from config import DB_PATH, OWNER_IDS, DEFAULT_PORT_LIMIT, DEFAULT_SNAP_LIMIT

SCHEMA = """
CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, added_by INTEGER, added_at INTEGER);
CREATE TABLE IF NOT EXISTS vps (
    name TEXT PRIMARY KEY,
    owner_id INTEGER NOT NULL,
    ram_gb INTEGER NOT NULL,
    cpu INTEGER NOT NULL,
    disk_gb INTEGER NOT NULL,
    image TEXT NOT NULL,
    root_password TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER DEFAULT 0,
    suspended INTEGER DEFAULT 0,
    manual_stop INTEGER DEFAULT 0,
    auto_backup INTEGER DEFAULT 0,
    auto_restart INTEGER DEFAULT 1,
    hostname TEXT,
    last_repair INTEGER DEFAULT 0,
    last_backup INTEGER DEFAULT 0,
    tunnel TEXT,
    notified INTEGER DEFAULT 0,
    port_limit INTEGER DEFAULT 5,
    snap_limit INTEGER DEFAULT 5
);
CREATE TABLE IF NOT EXISTS ports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vps TEXT NOT NULL,
    public_port INTEGER NOT NULL,
    private_port INTEGER NOT NULL,
    proto TEXT NOT NULL DEFAULT 'tcp',
    UNIQUE(public_port, proto)
);
"""

VPS_FIELDS = {
    "owner_id", "ram_gb", "cpu", "disk_gb", "root_password", "expires_at", "suspended",
    "manual_stop", "auto_backup", "auto_restart", "hostname", "last_repair", "last_backup",
    "tunnel", "notified", "port_limit", "snap_limit", "created_at",
}


class DB:
    def __init__(self):
        self.conn: aiosqlite.Connection | None = None

    async def connect(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self.conn = await aiosqlite.connect(DB_PATH)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def one(self, q, a=()):
        async with self.conn.execute(q, a) as cur:
            return await cur.fetchone()

    async def all(self, q, a=()):
        async with self.conn.execute(q, a) as cur:
            return await cur.fetchall()

    async def run(self, q, a=()):
        cur = await self.conn.execute(q, a)
        await self.conn.commit()
        return cur.lastrowid

    # ── admins ──────────────────────────────
    async def is_admin(self, uid: int) -> bool:
        if uid in OWNER_IDS:
            return True
        return await self.one("SELECT 1 FROM admins WHERE user_id=?", (uid,)) is not None

    async def add_admin(self, uid: int, by: int):
        await self.run("INSERT OR IGNORE INTO admins VALUES (?,?,?)", (uid, by, int(time.time())))

    async def remove_admin(self, uid: int):
        await self.run("DELETE FROM admins WHERE user_id=?", (uid,))

    async def list_admins(self):
        return await self.all("SELECT * FROM admins ORDER BY added_at")

    # ── vps ─────────────────────────────────
    async def create_vps(self, name, owner_id, ram, cpu, disk, image, password, expires_at):
        await self.run(
            "INSERT INTO vps (name,owner_id,ram_gb,cpu,disk_gb,image,root_password,created_at,expires_at,port_limit,snap_limit)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (name, owner_id, ram, cpu, disk, image, password, int(time.time()), expires_at,
             DEFAULT_PORT_LIMIT, DEFAULT_SNAP_LIMIT),
        )

    async def get_vps(self, name):
        return await self.one("SELECT * FROM vps WHERE name=?", (name,))

    async def user_vps(self, uid):
        return await self.all("SELECT * FROM vps WHERE owner_id=? ORDER BY created_at", (uid,))

    async def all_vps(self):
        return await self.all("SELECT * FROM vps ORDER BY created_at")

    async def update_vps(self, name, **fields):
        bad = set(fields) - VPS_FIELDS
        if bad:
            raise ValueError(f"bad fields: {bad}")
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        await self.run(f"UPDATE vps SET {sets} WHERE name=?", (*fields.values(), name))

    async def delete_vps(self, name):
        await self.run("DELETE FROM ports WHERE vps=?", (name,))
        await self.run("DELETE FROM vps WHERE name=?", (name,))

    # ── ports ───────────────────────────────
    async def ports(self, vps):
        return await self.all("SELECT * FROM ports WHERE vps=? ORDER BY public_port", (vps,))

    async def add_port(self, vps, pub, priv, proto):
        await self.run("INSERT INTO ports (vps,public_port,private_port,proto) VALUES (?,?,?,?)", (vps, pub, priv, proto))

    async def del_port(self, vps, pub, proto):
        await self.run("DELETE FROM ports WHERE vps=? AND public_port=? AND proto=?", (vps, pub, proto))

    async def port_taken(self, pub, proto):
        return await self.one("SELECT 1 FROM ports WHERE public_port=? AND proto=?", (pub, proto)) is not None
