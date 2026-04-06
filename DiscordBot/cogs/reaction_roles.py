import json
import asyncio
import discord
from discord.ext import commands
from discord import Option, SlashCommandGroup
from typing import Dict, List, Optional, Union

# Load config for guild ID and admin roles
with open("data/server_config.json", "r") as f:
    CONFIG = json.load(f)
GUILD_ID = CONFIG["guild_id"]
ADMIN_ROLE_IDS = CONFIG["admin_role_ids"]

# Helper to check admin
def is_admin():
    async def predicate(ctx: discord.ApplicationContext):
        if not ctx.guild:
            return False
        author_roles = [r.id for r in ctx.author.roles]
        return any(rid in author_roles for rid in ADMIN_ROLE_IDS)
    return commands.check(predicate)

# ---------------------------
# Persistent Storage
# ---------------------------
class ReactionRoleStore:
    DATA_FILE = "data/reaction_roles.json"

    @classmethod
    def load(cls) -> dict:
        try:
            with open(cls.DATA_FILE, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    @classmethod
    def save(cls, data: dict):
        with open(cls.DATA_FILE, "w") as f:
            json.dump(data, f, indent=4)

    @classmethod
    def get_entry(cls, message_id: int) -> Optional[dict]:
        data = cls.load()
        return data.get(str(message_id))

    @classmethod
    def set_entry(cls, message_id: int, entry: dict):
        data = cls.load()
        data[str(message_id)] = entry
        cls.save(data)

    @classmethod
    def delete_entry(cls, message_id: int):
        data = cls.load()
        if str(message_id) in data:
            del data[str(message_id)]
            cls.save(data)

# ---------------------------
# Persistent View for Buttons
# ---------------------------
class RoleButtonView(discord.ui.View):
    def __init__(self, role_mapping: Dict[str, int], message_id: int):
        super().__init__(timeout=None)  # persistent
        self.role_mapping = role_mapping
        self.message_id = message_id
        # Add buttons dynamically
        for custom_id, role_id in role_mapping.items():
            button = discord.ui.Button(
                label=custom_id,  # label is the stored role name
                custom_id=custom_id,
                style=discord.ButtonStyle.primary
            )
            button.callback = self.create_callback(role_id)
            self.add_item(button)

    def create_callback(self, role_id: int):
        async def callback(interaction: discord.Interaction):
            member = interaction.user
            role = interaction.guild.get_role(role_id)
            if not role:
                await interaction.response.send_message("Role no longer exists.", ephemeral=True)
                return
            if role in member.roles:
                await member.remove_roles(role)
                msg = f"Removed {role.mention} from you."
            else:
                await member.add_roles(role)
                msg = f"Gave you {role.mention}."
            await interaction.response.send_message(msg, ephemeral=True)
            # Auto-delete after 30 seconds
            await asyncio.sleep(30)
            await interaction.delete_original_response()
        return callback

# ---------------------------
# Cog
# ---------------------------
class ReactionRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.persistent_view = None  # will be populated after loading stored entries

    async def cog_load(self):
        """Load all stored reaction role messages and restore persistent views."""
        data = ReactionRoleStore.load()
        for msg_id_str, entry in data.items():
            if entry["type"] == "button":
                view = RoleButtonView(entry["role_mapping"], int(msg_id_str))
                self.bot.add_view(view, message_id=int(msg_id_str))
                # Keep one reference for the persistent view attribute
                if self.persistent_view is None:
                    self.persistent_view = view

    # ---------------------------
    # Slash Commands
    # ---------------------------
    reaction_role = SlashCommandGroup("reactionrole", "Manage reaction roles", guild_ids=[GUILD_ID])

    @reaction_role.command(name="create", description="Create a new reaction role embed")
    @is_admin()
    async def create_reaction_role(self, ctx: discord.ApplicationContext):
        """Start the interactive creation wizard."""
        await ctx.respond("Starting creation wizard...", ephemeral=True)
        creator = ReactionRoleCreator(ctx, self.bot)
        await creator.start()

    @reaction_role.command(name="edit", description="Edit an existing reaction role embed")
    @is_admin()
    async def edit_reaction_role(self, ctx: discord.ApplicationContext,
                                 message_id: Option(str, "The ID of the reaction role message to edit")):
        """Edit an existing reaction role embed by providing its message ID."""
        # Validate that message_id exists in storage
        entry = ReactionRoleStore.get_entry(int(message_id))
        if not entry:
            await ctx.respond("No reaction role found with that message ID.", ephemeral=True)
            return
        await ctx.respond(f"Editing message {message_id}...", ephemeral=True)
        editor = ReactionRoleEditor(ctx, self.bot, int(message_id), entry)
        await editor.start()

# ---------------------------
# Creation Wizard (State Machine)
# ---------------------------
class ReactionRoleCreator:
    def __init__(self, ctx: discord.ApplicationContext, bot):
        self.ctx = ctx
        self.bot = bot
        self.data = {
            "title": None,
            "description": None,
            "image_url": None,
            "color": None,
            "type": None,          # "button" or "emoji"
            "channel": None,
            "roles": []            # list of dicts: {"name": str, "role_id": int}
        }
        self.step = 0
        self.message = None        # the ephemeral interaction message

    async def start(self):
        await self.step_embed_details()

    async def step_embed_details(self):
        """Open modal for embed title, description, image URL, color."""
        modal = EmbedDetailsModal(self)
        await self.ctx.send_modal(modal)

    async def after_embed_details(self, title, description, image_url, color):
        self.data["title"] = title
        self.data["description"] = description
        self.data["image_url"] = image_url if image_url else None
        self.data["color"] = color
        await self.step_choice_type()

    async def step_choice_type(self):
        """Ask for reaction type: button or emoji."""
        view = TypeChoiceView(self)
        embed = discord.Embed(title="Step 2: Choose reaction type", description="Select whether users will use buttons or emojis to get roles.")
        await self.update_ephemeral(embed=embed, view=view)

    async def after_choice_type(self, choice):
        self.data["type"] = choice
        await self.step_choose_channel()

    async def step_choose_channel(self):
        """Ask for target channel."""
        view = ChannelSelectView(self)
        embed = discord.Embed(title="Step 3: Choose target channel", description="Select the text channel where the reaction role embed will be sent.")
        await self.update_ephemeral(embed=embed, view=view)

    async def after_channel(self, channel):
        self.data["channel"] = channel
        await self.step_add_roles()

    async def step_add_roles(self):
        """Menu to add roles one by one."""
        view = RoleManagementView(self)
        embed = discord.Embed(title="Step 4: Add roles", description="Click 'Add Role' to add a role mapping. When finished, click 'Finish'.")
        if self.data["roles"]:
            role_list = "\n".join([f"- {r['name']} → <@&{r['role_id']}>" for r in self.data["roles"]])
            embed.add_field(name="Current roles", value=role_list, inline=False)
        await self.update_ephemeral(embed=embed, view=view)

    async def add_role(self, name, role_id):
        self.data["roles"].append({"name": name, "role_id": role_id})
        await self.step_add_roles()  # refresh

    async def finish_creation(self):
        """Build and send the embed with components."""
        # Build embed
        embed = discord.Embed(
            title=self.data["title"],
            description=self.data["description"],
            color=int(self.data["color"].lstrip("#"), 16)
        )
        if self.data["image_url"]:
            embed.set_image(url=self.data["image_url"])

        # Prepare role mapping
        if self.data["type"] == "button":
            role_mapping = {r["name"]: r["role_id"] for r in self.data["roles"]}
            view = RoleButtonView(role_mapping, message_id=0)  # placeholder ID
        else:  # emoji
            view = None
            # We will store emoji-to-role mapping separately

        target_channel = self.bot.get_channel(self.data["channel"].id)
        if not target_channel:
            await self.ctx.followup.send("Target channel not found.", ephemeral=True)
            return

        msg = await target_channel.send(embed=embed, view=view)

        # Save to storage
        entry = {
            "guild_id": self.ctx.guild_id,
            "channel_id": target_channel.id,
            "type": self.data["type"],
            "role_mapping": {r["name"]: r["role_id"] for r in self.data["roles"]} if self.data["type"] == "button" else None,
            "emoji_mapping": None,  # would store {emoji_str: role_id} for emoji type
            "embed_data": {
                "title": self.data["title"],
                "description": self.data["description"],
                "image_url": self.data["image_url"],
                "color": self.data["color"]
            }
        }
        if self.data["type"] == "emoji":
            # For emoji type, we need to add the mapping after user adds reactions?
            # For simplicity, we'll assume they will add emojis manually? Better to extend wizard.
            # In this version, we skip emoji mapping collection; you'd need extra step.
            entry["emoji_mapping"] = {}
        ReactionRoleStore.set_entry(msg.id, entry)

        # If button type, add persistent view to bot
        if self.data["type"] == "button":
            self.bot.add_view(view, message_id=msg.id)

        await self.ctx.followup.send(f"Reaction role embed created in {target_channel.mention}!", ephemeral=True)
        await self.delete_ephemeral()

    async def update_ephemeral(self, embed=None, view=None):
        """Edit the ephemeral message or send a new one."""
        if self.message is None:
            self.message = await self.ctx.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await self.message.edit(embed=embed, view=view)

    async def delete_ephemeral(self):
        if self.message:
            await self.message.delete()

# ---------------------------
# Modal for Embed Details
# ---------------------------
class EmbedDetailsModal(discord.ui.Modal):
    def __init__(self, creator: ReactionRoleCreator):
        super().__init__(title="Embed Details")
        self.creator = creator
        self.add_item(discord.ui.InputText(label="Title", placeholder="Embed title"))
        self.add_item(discord.ui.InputText(label="Description", placeholder="Embed description", style=discord.InputTextStyle.long))
        self.add_item(discord.ui.InputText(label="Image URL", placeholder="https://... (optional)", required=False))
        self.add_item(discord.ui.InputText(label="Color", placeholder="#RRGGBB or hex", required=False, default="#00ff00"))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        title = self.children[0].value
        desc = self.children[1].value
        img_url = self.children[2].value or None
        color = self.children[3].value
        if not color.startswith("#"):
            color = "#" + color
        await self.creator.after_embed_details(title, desc, img_url, color)

# ---------------------------
# Type Choice View
# ---------------------------
class TypeChoiceView(discord.ui.View):
    def __init__(self, creator: ReactionRoleCreator):
        super().__init__(timeout=60)
        self.creator = creator

    @discord.ui.button(label="Buttons", style=discord.ButtonStyle.primary)
    async def buttons_btn(self, button, interaction):
        await interaction.response.defer(ephemeral=True)
        await self.creator.after_choice_type("button")

    @discord.ui.button(label="Emojis", style=discord.ButtonStyle.secondary)
    async def emojis_btn(self, button, interaction):
        await interaction.response.defer(ephemeral=True)
        await self.creator.after_choice_type("emoji")

# ---------------------------
# Channel Select View
# ---------------------------
class ChannelSelectView(discord.ui.View):
    def __init__(self, creator: ReactionRoleCreator):
        super().__init__(timeout=60)
        self.creator = creator
        self.add_item(ChannelSelect(self))

class ChannelSelect(discord.ui.Select):
    def __init__(self, parent_view: ChannelSelectView):
        self.parent_view = parent_view
        options = []
        for channel in parent_view.creator.ctx.guild.text_channels:
            options.append(discord.SelectOption(label=f"#{channel.name}", value=str(channel.id)))
        super().__init__(placeholder="Choose a text channel", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        channel_id = int(self.values[0])
        channel = interaction.guild.get_channel(channel_id)
        await interaction.response.defer(ephemeral=True)
        await self.parent_view.creator.after_channel(channel)

# ---------------------------
# Role Management View (Add/Finish)
# ---------------------------
class RoleManagementView(discord.ui.View):
    def __init__(self, creator: ReactionRoleCreator):
        super().__init__(timeout=120)
        self.creator = creator

    @discord.ui.button(label="Add Role", style=discord.ButtonStyle.success)
    async def add_role_btn(self, button, interaction):
        modal = AddRoleModal(self.creator)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Finish", style=discord.ButtonStyle.danger)
    async def finish_btn(self, button, interaction):
        await interaction.response.defer(ephemeral=True)
        if not self.creator.data["roles"]:
            await interaction.followup.send("You must add at least one role.", ephemeral=True)
            return
        await self.creator.finish_creation()

class AddRoleModal(discord.ui.Modal):
    def __init__(self, creator: ReactionRoleCreator):
        super().__init__(title="Add Role Mapping")
        self.creator = creator
        self.add_item(discord.ui.InputText(label="Button/Emoji Label", placeholder="e.g., Get Member"))
        self.add_item(discord.ui.InputText(label="Role ID", placeholder="Right-click role -> Copy ID"))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        name = self.children[0].value
        role_id = int(self.children[1].value)
        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.followup.send("Invalid role ID.", ephemeral=True)
            return
        await self.creator.add_role(name, role_id)

# ---------------------------
# Editor Wizard (simplified – similar to creator but pre‑filled)
# ---------------------------
class ReactionRoleEditor:
    def __init__(self, ctx, bot, message_id, entry):
        self.ctx = ctx
        self.bot = bot
        self.message_id = message_id
        self.entry = entry
        self.data = entry.copy()
        self.message = None

    async def start(self):
        # For brevity, we skip full reimplementation; you would replicate the creation
        # steps with the existing data pre‑filled.
        await self.ctx.followup.send("Editing not fully implemented in this version. Please delete and re‑create.", ephemeral=True)

# ---------------------------
# Reaction event handler for emoji type
# ---------------------------
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.guild_id != GUILD_ID:
            return
        entry = ReactionRoleStore.get_entry(payload.message_id)
        if not entry or entry["type"] != "emoji":
            return
        # In a full implementation, you would check the emoji mapping
        # and add/remove roles accordingly, then send ephemeral confirmation.
        pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        # Similar to above
        pass

def setup(bot):
    bot.add_cog(ReactionRoles(bot))