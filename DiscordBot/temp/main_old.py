import discord
from discord.ext import commands
import json
import os

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Required for role management
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Database file path
DB_FILE = 'config.json'

def load_db():
    """Load reaction role configurations from JSON file"""
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, 'r') as f:
        return json.load(f)

def save_db(data):
    """Save reaction role configurations to JSON file"""
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=4)