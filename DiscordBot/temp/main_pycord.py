#!/usr/bin/env python3
"""
Main entry point for the Discord Reaction Role Bot.
Loads configuration, sets up the bot, and loads the reaction roles cog.
"""

import json
import logging
import sys
from pathlib import Path

import discord
from discord import Intents

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ReactionRoleBot")

# Configuration file path
CONFIG_FILE = Path("server_config.json")

def load_config():
    """Load or create the server configuration file."""
    if not CONFIG_FILE.exists():
        # Create default config and ask user to fill it
        default_config = {
            "discord_token": "",
            "guild_id": 0,
            "admin_role_ids": []
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(default_config, f, indent=2)
        logger.error(
            "server_config.json created. Please fill in your discord_token, "
            "guild_id, and admin_role_ids, then restart the bot."
        )
        sys.exit(1)

    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse server_config.json: {e}")
        sys.exit(1)

    # Validate required fields
    if not config.get("discord_token"):
        logger.error("discord_token missing or empty in server_config.json")
        sys.exit(1)
    if not config.get("guild_id"):
        logger.error("guild_id missing or zero in server_config.json")
        sys.exit(1)

    return config

def main():
    config = load_config()

    # Set up bot intents
    intents = Intents.default()
    intents.members = True          # Required to manage member roles
    intents.reactions = True        # Required for reaction events
    intents.message_content = True  # Optional, but helpful for debugging

    # Create bot with debug_guilds to restrict commands to a single guild
    # This ensures slash commands are only registered for the specified guild
    bot = discord.Bot(
        intents=intents,
        debug_guilds=[config["guild_id"]]  # Restrict commands to this guild only
    )

    @bot.event
    async def on_ready():
        logger.info(f"Bot ready: {bot.user} (ID: {bot.user.id})")
        logger.info(f"Slash commands restricted to guild ID: {config['guild_id']}")

    # Load the reaction roles cog
    from cogs.reaction_roles import ReactionRoles
    bot.add_cog(ReactionRoles(bot, config))

    # Run the bot
    try:
        bot.run(config["discord_token"])
    except discord.LoginFailure:
        logger.error("Invalid Discord token. Please check server_config.json")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Unexpected error while running bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()