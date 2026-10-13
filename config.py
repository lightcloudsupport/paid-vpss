import os
from dotenv import load_dotenv

load_dotenv()


def _ints(v: str):
    return [int(x) for x in v.replace(" ", "").split(",") if x.strip().isdigit()]


TOKEN = os.getenv("DISCORD_TOKEN", "")
OWNER_IDS = _ints(os.getenv("OWNER_IDS", ""))
BRAND = os.getenv("BRAND_NAME", "LightCloud")
LOGO_URL = os.getenv("LOGO_URL", "")
COLOR = int(os.getenv("EMBED_COLOR", "0x2ECC71"), 0)
GUILD_ID = int(os.getenv("GUILD_ID")) if os.getenv("GUILD_ID", "").isdigit() else None
PUBLIC_IP = os.getenv("PUBLIC_IP", "0.0.0.0")
PREFIX = os.getenv("VPS_PREFIX", "lc-")
DEFAULT_IMAGE = os.getenv("DEFAULT_IMAGE", "images:ubuntu/22.04")
PORT_START = int(os.getenv("PORT_RANGE_START", "20000"))
PORT_END = int(os.getenv("PORT_RANGE_END", "29999"))
PANEL_URL = os.getenv("PANEL_URL", "")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID")) if os.getenv("LOG_CHANNEL_ID", "").isdigit() else None

VERSION = "v1.0-Paid-LXC"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "paid.db")

# Defaults applied to every new paid VPS
DEFAULT_PORT_LIMIT = 5
DEFAULT_SNAP_LIMIT = 5
