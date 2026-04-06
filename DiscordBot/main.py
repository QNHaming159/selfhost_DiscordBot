import json
import discord
from discord.ext import commands

# Load single config file
def load_config():
    with open("data/server_config.json", "r") as f:
        return json.load(f)

config = load_config()
TOKEN = config["discord_token"]
GUILD_ID = config["guild_id"]
ADMIN_ROLE_IDS = config["admin_role_ids"]

# Admin check using loaded admin role IDs
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
        await self.load_extension("cogs.reaction_roles")
        self.synced = False

    async def on_ready(self):
        if not self.synced:
            guild = discord.Object(id=GUILD_ID)
            await self.sync_commands(guild=guild)
            self.synced = True
        print(f"Logged in as {self.user} (ID: {self.user.id})")

bot = AdminBot()

if __name__ == "__main__":
    bot.run(TOKEN)