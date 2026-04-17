import json
import logging
from pathlib import Path

from attr import dataclass
import hikari
import lightbulb

# Logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ReactionRoleBot")

# Check Data directory
data_dir = Path(".data")
if not data_dir.exists():
    data_dir.mkdir()

# Config set up
CONFIG_FILE = Path("server_config.json")
if not CONFIG_FILE.exists():
    json_data = {
        "discord_token": "YOUR_BOT_TOKEN_HERE",
        "guild_id": [ 123456789012345678 ],
        "admin_role_ids": [ 987654321098765432, 987654321098765430 ]
    }
    CONFIG_FILE.write_text(json.dumps(json_data, indent=4))
    logger.error("Enter your discord_token in 'server_config.json' then restart the bot.") 
    exit(1)
config = json.loads(CONFIG_FILE.read_text())
if not config.get("discord_token") or not config.get("guild_id"):
    logger.error("Missing token or guild_id in server_config.json")
    exit(1)

# Bot set up
bot = hikari.GatewayBot(token=config["discord_token"])
lb_client = lightbulb.client_from_app(bot,default_enabled_guilds=[config["guild_id"]])

# Load any extensions
@bot.listen(hikari.StartingEvent)
async def on_starting(_: hikari.StartingEvent) -> None:
    import extensions
    await lb_client.load_extensions_from_package(extensions)

    import examples
    await lb_client.load_extensions_from_package(examples)

# Ensure the Lightbulb_client starts
bot.subscribe(hikari.StartingEvent, lb_client.start)

if __name__ == "__main__":
    bot.run()