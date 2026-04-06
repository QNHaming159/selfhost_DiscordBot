import json
import os
import discord
from discord.ext import commands

# Load configuration
with open("data/server_config.json", "r") as f:
    config = json.load(f)

GUILD_ID = config["guild_id"]
ADMIN_ROLE_IDS = config["admin_role_ids"]

# Define a check for admin roles
def is_admin():
    async def predicate(ctx: discord.ApplicationContext):
        if not ctx.guild:
            return False
        author_roles = [role.id for role in ctx.author.roles]
        return any(role_id in author_roles for role_id in ADMIN_ROLE_IDS)
    return commands.check(predicate)

class AdminBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        intents.reactions = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Load reaction role cog
        await self.load_extension("cogs.reaction_roles")
        # Sync commands to the specific guild only
        self.synced = False

    async def on_ready(self):
        if not self.synced:
            guild = discord.Object(id=GUILD_ID)
            self.add_view(self.get_cog("ReactionRoles").persistent_view)  # will be set later
            await self.sync_commands(guild=guild)
            self.synced = True
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("------")

    async def sync_commands(self, guild):
        await self.sync_commands(guild=guild)

bot = AdminBot()

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("DISCORD_TOKEN environment variable not set")
    bot.run(token)