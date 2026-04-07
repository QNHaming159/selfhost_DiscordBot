import json
import logging
from pathlib import Path

import extensions

import hikari
import lightbulb
import miru

# logger setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("ReactionRoleBot")

# config set up
CONFIG_FILE = Path("server_config.json")
if not CONFIG_FILE.exists():
    logger.error("Fill server_config.json and restart.")
    exit(1)
config = json.loads(CONFIG_FILE.read_text())
if not config.get("discord_token") or not config.get("guild_id"):
    logger.error("Missing token or guild_id in server_config.json")
    exit(1)

# bot set up
bot = hikari.GatewayBot(token=config["discord_token"])
lb_client = lightbulb.client_from_app(bot)
mr_client = miru.Client(bot)

# load extensions
@bot.listen(hikari.StartingEvent)
async def on_starting(_: hikari.StartingEvent) -> None:
    await lb_client.load_extensions_from_package(extensions)

# load the bot
bot.subscribe(hikari.StartingEvent, lb_client.start)

# Finale
if __name__ == "__main__":
    bot.run()