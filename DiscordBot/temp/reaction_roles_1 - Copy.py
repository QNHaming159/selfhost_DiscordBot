import json
import asyncio
import os
import discord
from discord.ext import commands
from discord import Option, SlashCommandGroup
from typing import Dict, Optional

# ---------- Config ----------
def load_config():
    with open("server_config.json", "r") as f:
        return json.load(f)

CONFIG = load_config()
GUILD_ID = CONFIG["guild_id"]
ADMIN_ROLE_IDS = CONFIG["admin_role_ids"]

def is_admin():
    async def predicate(ctx: discord.ApplicationContext):
        if not ctx.guild:
            return False
        author_roles = [r.id for r in ctx.author.roles]
        return any(rid in author_roles for rid in ADMIN_ROLE_IDS)
    return commands.check(predicate)

# ---------- Persistent Storage with auto-create and corruption handling ----------
class ReactionRoleStore:
    DATA_FILE = "data/reaction_roles.json"

    @classmethod
    def _ensure_dir(cls):
        os.makedirs(os.path.dirname(cls.DATA_FILE), exist_ok=True)

    @classmethod
    def _ensure_file(cls):
        cls._ensure_dir()
        if not os.path.exists(cls.DATA_FILE):
            with open(cls.DATA_FILE, "w") as f:
                json.dump({}, f)

    @classmethod
    def load(cls) -> dict:
        cls._ensure_file()
        try:
            with open(cls.DATA_FILE, "r") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError
                return data
        except (json.JSONDecodeError, ValueError):
            # Backup and reset on corruption
            try:
                os.rename(cls.DATA_FILE, cls.DATA_FILE + ".corrupt")
            except:
                pass
            cls.save({})
            return {}

    @classmethod
    def save(cls, data: dict):
        cls._ensure_dir()
        with open(cls.DATA_FILE, "w") as f:
            json.dump(data, f, indent=4)

    @classmethod
    def get_entry(cls, message_id: int) -> Optional[dict]:
        return cls.load().get(str(message_id))

    @classmethod
    def set_entry(cls, message_id: int, entry: dict):
        data = cls.load()
        data[str(message_id)] = entry
        cls.save(data)

    @classmethod
    def delete_entry(cls, message_id: int):
        data = cls.load()
        data.pop(str(message_id), None)
        cls.save(data)

# ---------- Persistent Button View ----------
class RoleButtonView(discord.ui.View):
    def __init__(self, role_mapping: Dict[str, int], message_id: int):
        super().__init__(timeout=None)
        self.role_mapping = role_mapping
        self.message_id = message_id
        for label, role_id in role_mapping.items():
            button = discord.ui.Button(
                label=label,
                custom_id=f"rolebtn_{message_id}_{label}",
                style=discord.ButtonStyle.primary
            )
            button.callback = self._make_callback(role_id)
            self.add_item(button)

    def _make_callback(self, role_id: int):
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
            await asyncio.sleep(30)
            try:
                await interaction.delete_original_response()
            except:
                pass
        return callback

# ---------- Main Cog ----------
class ReactionRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        data = ReactionRoleStore.load()
        if not data:
            return
        restored_buttons = 0
        restored_emojis = 0
        for msg_id_str, entry in data.items():
            msg_id = int(msg_id_str)
            if entry["type"] == "button":
                view = RoleButtonView(entry["role_mapping"], msg_id)
                self.bot.add_view(view, message_id=msg_id)
                restored_buttons += 1
            elif entry["type"] == "emoji":
                channel = self.bot.get_channel(entry["channel_id"])
                if channel:
                    try:
                        msg = await channel.fetch_message(msg_id)
                        for emoji in entry["emoji_mapping"].keys():
                            await msg.add_reaction(emoji)
                        restored_emojis += 1
                    except:
                        pass
        print(f"[RESTORE] Loaded {restored_buttons} button-based and {restored_emojis} emoji-based reaction roles.")

    # ---------- Slash Commands ----------
    reaction_role = SlashCommandGroup("reactionrole", "Manage reaction roles", guild_ids=[GUILD_ID])

    @reaction_role.command(name="create", description="Create a new reaction role embed")
    @is_admin()
    async def create_reaction_role(self, ctx: discord.ApplicationContext):
        creator = ReactionRoleCreator(ctx, self.bot)
        await creator.start()

    @reaction_role.command(name="edit", description="Edit an existing reaction role embed")
    @is_admin()
    async def edit_reaction_role(self, ctx: discord.ApplicationContext,
                                 message_id: Option(str, "The ID of the reaction role message to edit")):
        entry = ReactionRoleStore.get_entry(int(message_id))
        if not entry:
            await ctx.respond("No reaction role found with that message ID.", ephemeral=True)
            return
        editor = ReactionRoleEditor(ctx, self.bot, int(message_id), entry)
        await editor.start()

    # ---------- Emoji Handlers ----------
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.guild_id != GUILD_ID:
            return
        entry = ReactionRoleStore.get_entry(payload.message_id)
        if not entry or entry["type"] != "emoji":
            return
        emoji_str = str(payload.emoji)
        if emoji_str not in entry["emoji_mapping"]:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return
        role_id = entry["emoji_mapping"][emoji_str]
        role = guild.get_role(role_id)
        if not role:
            return
        await member.add_roles(role)
        try:
            dm = await member.send(f"✅ Gave you {role.mention} (in {guild.name})")
            await asyncio.sleep(30)
            await dm.delete()
        except:
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if payload.guild_id != GUILD_ID:
            return
        entry = ReactionRoleStore.get_entry(payload.message_id)
        if not entry or entry["type"] != "emoji":
            return
        emoji_str = str(payload.emoji)
        if emoji_str not in entry["emoji_mapping"]:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return
        role_id = entry["emoji_mapping"][emoji_str]
        role = guild.get_role(role_id)
        if not role:
            return
        await member.remove_roles(role)
        try:
            dm = await member.send(f"❌ Removed {role.mention} from you (in {guild.name})")
            await asyncio.sleep(30)
            await dm.delete()
        except:
            pass

# ---------- Creation Wizard ----------
class ReactionRoleCreator:
    def __init__(self, ctx: discord.ApplicationContext, bot):
        self.ctx = ctx
        self.bot = bot
        self.data = {
            "title": None,
            "description": None,
            "image_url": None,
            "color": None,
            "type": None,
            "channel": None,
            "roles": []            # list of {"name"/"emoji": str, "role_id": int}
        }
        self.message = None

    async def start(self):
        await self._step_embed_details()

    async def _step_embed_details(self):
        modal = EmbedDetailsModal(self)
        await self.ctx.send_modal(modal)

    async def after_embed_details(self, title, description, image_url, color):
        self.data["title"] = title
        self.data["description"] = description
        self.data["image_url"] = image_url if image_url else None
        self.data["color"] = color
        await self._step_choice_type()

    async def _step_choice_type(self):
        view = TypeChoiceView(self)
        embed = discord.Embed(title="Step 2: Choose reaction type",
                              description="Select whether users will use buttons or emojis to get roles.")
        await self._update_ephemeral(embed=embed, view=view)

    async def after_choice_type(self, choice):
        self.data["type"] = choice
        await self._step_choose_channel()

    async def _step_choose_channel(self):
        view = ChannelSelectView(self)
        embed = discord.Embed(title="Step 3: Choose target channel",
                              description="Select the text channel where the reaction role embed will be sent.")
        await self._update_ephemeral(embed=embed, view=view)

    async def after_channel(self, channel):
        self.data["channel"] = channel
        await self._step_add_roles()

    async def _step_add_roles(self):
        view = RoleManagementView(self)
        embed = discord.Embed(title="Step 4: Add roles",
                              description="Click 'Add Role' to add a role mapping. When finished, click 'Finish'.")
        if self.data["roles"]:
            if self.data["type"] == "button":
                role_list = "\n".join([f"- {r['name']} → <@&{r['role_id']}>" for r in self.data["roles"]])
            else:
                role_list = "\n".join([f"- {r['emoji']} → <@&{r['role_id']}>" for r in self.data["roles"]])
            embed.add_field(name="Current roles", value=role_list, inline=False)
        await self._update_ephemeral(embed=embed, view=view)

    async def add_role(self, identifier, role_id):
        if self.data["type"] == "button":
            self.data["roles"].append({"name": identifier, "role_id": role_id})
        else:
            self.data["roles"].append({"emoji": identifier, "role_id": role_id})
        await self._step_add_roles()

    async def finish_creation(self):
        # Build embed
        embed = discord.Embed(
            title=self.data["title"],
            description=self.data["description"],
            color=int(self.data["color"].lstrip("#"), 16)
        )
        if self.data["image_url"]:
            embed.set_image(url=self.data["image_url"])

        target_channel = self.bot.get_channel(self.data["channel"].id)
        if not target_channel:
            await self.ctx.followup.send("Target channel not found.", ephemeral=True)
            return

        if self.data["type"] == "button":
            role_mapping = {r["name"]: r["role_id"] for r in self.data["roles"]}
            view = RoleButtonView(role_mapping, message_id=0)
            msg = await target_channel.send(embed=embed, view=view)
            entry = {
                "guild_id": self.ctx.guild_id,
                "channel_id": target_channel.id,
                "type": "button",
                "role_mapping": role_mapping,
                "emoji_mapping": None,
                "embed_data": {
                    "title": self.data["title"],
                    "description": self.data["description"],
                    "image_url": self.data["image_url"],
                    "color": self.data["color"]
                }
            }
            ReactionRoleStore.set_entry(msg.id, entry)
            self.bot.add_view(view, message_id=msg.id)
        else:  # emoji
            emoji_mapping = {r["emoji"]: r["role_id"] for r in self.data["roles"]}
            msg = await target_channel.send(embed=embed)
            for emoji in emoji_mapping.keys():
                await msg.add_reaction(emoji)
            entry = {
                "guild_id": self.ctx.guild_id,
                "channel_id": target_channel.id,
                "type": "emoji",
                "role_mapping": None,
                "emoji_mapping": emoji_mapping,
                "embed_data": {
                    "title": self.data["title"],
                    "description": self.data["description"],
                    "image_url": self.data["image_url"],
                    "color": self.data["color"]
                }
            }
            ReactionRoleStore.set_entry(msg.id, entry)

        await self.ctx.followup.send(f"Reaction role embed created in {target_channel.mention}!", ephemeral=True)
        await self._delete_ephemeral()

    async def _update_ephemeral(self, embed=None, view=None):
        if self.message is None:
            self.message = await self.ctx.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await self.message.edit(embed=embed, view=view)

    async def _delete_ephemeral(self):
        if self.message:
            await self.message.delete()

# ---------- Modal for Embed Details ----------
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

# ---------- Helper Views for Wizard ----------
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

class RoleManagementView(discord.ui.View):
    def __init__(self, creator: ReactionRoleCreator):
        super().__init__(timeout=120)
        self.creator = creator

    @discord.ui.button(label="Add Role", style=discord.ButtonStyle.success)
    async def add_role_btn(self, button, interaction):
        if self.creator.data["type"] == "button":
            modal = AddRoleModalButton(self.creator)
        else:
            modal = AddRoleModalEmoji(self.creator)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Finish", style=discord.ButtonStyle.danger)
    async def finish_btn(self, button, interaction):
        await interaction.response.defer(ephemeral=True)
        if not self.creator.data["roles"]:
            await interaction.followup.send("You must add at least one role.", ephemeral=True)
            return
        await self.creator.finish_creation()

class AddRoleModalButton(discord.ui.Modal):
    def __init__(self, creator: ReactionRoleCreator):
        super().__init__(title="Add Button Role Mapping")
        self.creator = creator
        self.add_item(discord.ui.InputText(label="Button Label", placeholder="e.g., Get Member"))
        self.add_item(discord.ui.InputText(label="Role ID", placeholder="Right-click role -> Copy ID"))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        label = self.children[0].value
        try:
            role_id = int(self.children[1].value)
        except ValueError:
            await interaction.followup.send("Invalid Role ID. Must be a number.", ephemeral=True)
            return
        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.followup.send("Invalid role ID.", ephemeral=True)
            return
        await self.creator.add_role(label, role_id)

class AddRoleModalEmoji(discord.ui.Modal):
    def __init__(self, creator: ReactionRoleCreator):
        super().__init__(title="Add Emoji Role Mapping")
        self.creator = creator
        self.add_item(discord.ui.InputText(label="Emoji", placeholder="😀 or :emoji_name:"))
        self.add_item(discord.ui.InputText(label="Role ID", placeholder="Right-click role -> Copy ID"))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        emoji_str = self.children[0].value.strip()
        try:
            role_id = int(self.children[1].value)
        except ValueError:
            await interaction.followup.send("Invalid Role ID. Must be a number.", ephemeral=True)
            return
        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.followup.send("Invalid role ID.", ephemeral=True)
            return
        await self.creator.add_role(emoji_str, role_id)

# ---------- Editor Wizard ----------
class ReactionRoleEditor:
    def __init__(self, ctx, bot, message_id, entry):
        self.ctx = ctx
        self.bot = bot
        self.message_id = message_id
        self.entry = entry
        self.data = entry.copy()
        self.message = None

    async def start(self):
        await self._edit_embed_details()

    async def _edit_embed_details(self):
        modal = EditEmbedModal(self)
        await self.ctx.send_modal(modal)

    async def after_embed_details(self, title, description, image_url, color):
        self.data["embed_data"]["title"] = title
        self.data["embed_data"]["description"] = description
        self.data["embed_data"]["image_url"] = image_url if image_url else None
        self.data["embed_data"]["color"] = color
        await self._edit_role_mappings()

    async def _edit_role_mappings(self):
        view = EditRoleManagementView(self)
        embed = discord.Embed(title="Edit Role Mappings", description="Add or remove role mappings.")
        if self.data["type"] == "button":
            role_list = "\n".join([f"- {label} → <@&{rid}>" for label, rid in self.data["role_mapping"].items()])
        else:
            role_list = "\n".join([f"- {emoji} → <@&{rid}>" for emoji, rid in self.data["emoji_mapping"].items()])
        embed.add_field(name="Current roles", value=role_list or "None", inline=False)
        await self._update_ephemeral(embed=embed, view=view)

    async def add_role(self, identifier, role_id):
        if self.data["type"] == "button":
            self.data["role_mapping"][identifier] = role_id
        else:
            self.data["emoji_mapping"][identifier] = role_id
        await self._edit_role_mappings()

    async def remove_role(self, identifier):
        if self.data["type"] == "button":
            self.data["role_mapping"].pop(identifier, None)
        else:
            self.data["emoji_mapping"].pop(identifier, None)
        await self._edit_role_mappings()

    async def finish_editing(self):
        channel = self.bot.get_channel(self.data["channel_id"])
        if not channel:
            await self.ctx.followup.send("Channel not found.", ephemeral=True)
            return
        try:
            msg = await channel.fetch_message(self.message_id)
        except:
            await self.ctx.followup.send("Original message not found.", ephemeral=True)
            return

        embed = discord.Embed(
            title=self.data["embed_data"]["title"],
            description=self.data["embed_data"]["description"],
            color=int(self.data["embed_data"]["color"].lstrip("#"), 16)
        )
        if self.data["embed_data"]["image_url"]:
            embed.set_image(url=self.data["embed_data"]["image_url"])

        if self.data["type"] == "button":
            view = RoleButtonView(self.data["role_mapping"], self.message_id)
            await msg.edit(embed=embed, view=view)
            self.bot.add_view(view, message_id=self.message_id)
        else:
            await msg.clear_reactions()
            await msg.edit(embed=embed, view=None)
            for emoji in self.data["emoji_mapping"].keys():
                await msg.add_reaction(emoji)

        ReactionRoleStore.set_entry(self.message_id, self.data)
        await self.ctx.followup.send("Reaction role embed updated!", ephemeral=True)
        await self._delete_ephemeral()

    async def _update_ephemeral(self, embed=None, view=None):
        if self.message is None:
            self.message = await self.ctx.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await self.message.edit(embed=embed, view=view)

    async def _delete_ephemeral(self):
        if self.message:
            await self.message.delete()

class EditEmbedModal(discord.ui.Modal):
    def __init__(self, editor: ReactionRoleEditor):
        super().__init__(title="Edit Embed Details")
        self.editor = editor
        data = editor.data["embed_data"]
        self.add_item(discord.ui.InputText(label="Title", value=data["title"]))
        self.add_item(discord.ui.InputText(label="Description", value=data["description"], style=discord.InputTextStyle.long))
        self.add_item(discord.ui.InputText(label="Image URL", value=data.get("image_url") or "", required=False))
        self.add_item(discord.ui.InputText(label="Color", value=data.get("color", "#00ff00"), required=False))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        title = self.children[0].value
        desc = self.children[1].value
        img_url = self.children[2].value or None
        color = self.children[3].value
        if not color.startswith("#"):
            color = "#" + color
        await self.editor.after_embed_details(title, desc, img_url, color)

class EditRoleManagementView(discord.ui.View):
    def __init__(self, editor: ReactionRoleEditor):
        super().__init__(timeout=120)
        self.editor = editor

    @discord.ui.button(label="Add Role", style=discord.ButtonStyle.success)
    async def add_role_btn(self, button, interaction):
        if self.editor.data["type"] == "button":
            modal = EditAddRoleModalButton(self.editor)
        else:
            modal = EditAddRoleModalEmoji(self.editor)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Remove Role", style=discord.ButtonStyle.danger)
    async def remove_role_btn(self, button, interaction):
        view = RemoveRoleSelectView(self.editor)
        embed = discord.Embed(title="Select a role mapping to remove")
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Finish", style=discord.ButtonStyle.primary)
    async def finish_btn(self, button, interaction):
        await interaction.response.defer(ephemeral=True)
        await self.editor.finish_editing()

class EditAddRoleModalButton(discord.ui.Modal):
    def __init__(self, editor: ReactionRoleEditor):
        super().__init__(title="Add Button Role Mapping")
        self.editor = editor
        self.add_item(discord.ui.InputText(label="Button Label", placeholder="e.g., Get Member"))
        self.add_item(discord.ui.InputText(label="Role ID", placeholder="Right-click role -> Copy ID"))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        label = self.children[0].value
        try:
            role_id = int(self.children[1].value)
        except ValueError:
            await interaction.followup.send("Invalid Role ID.", ephemeral=True)
            return
        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.followup.send("Invalid role ID.", ephemeral=True)
            return
        await self.editor.add_role(label, role_id)

class EditAddRoleModalEmoji(discord.ui.Modal):
    def __init__(self, editor: ReactionRoleEditor):
        super().__init__(title="Add Emoji Role Mapping")
        self.editor = editor
        self.add_item(discord.ui.InputText(label="Emoji", placeholder="😀 or :emoji_name:"))
        self.add_item(discord.ui.InputText(label="Role ID", placeholder="Right-click role -> Copy ID"))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        emoji = self.children[0].value.strip()
        try:
            role_id = int(self.children[1].value)
        except ValueError:
            await interaction.followup.send("Invalid Role ID.", ephemeral=True)
            return
        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.followup.send("Invalid role ID.", ephemeral=True)
            return
        await self.editor.add_role(emoji, role_id)

class RemoveRoleSelectView(discord.ui.View):
    def __init__(self, editor: ReactionRoleEditor):
        super().__init__(timeout=60)
        self.editor = editor
        self.add_item(RemoveRoleSelect(editor))

class RemoveRoleSelect(discord.ui.Select):
    def __init__(self, editor: ReactionRoleEditor):
        self.editor = editor
        options = []
        if editor.data["type"] == "button":
            for label in editor.data["role_mapping"].keys():
                options.append(discord.SelectOption(label=label, value=label))
        else:
            for emoji in editor.data["emoji_mapping"].keys():
                options.append(discord.SelectOption(label=emoji, value=emoji))
        super().__init__(placeholder="Select a role mapping to remove", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        identifier = self.values[0]
        await self.editor.remove_role(identifier)
        await interaction.followup.send(f"Removed mapping for `{identifier}`.", ephemeral=True)

def setup(bot):
    bot.add_cog(ReactionRoles(bot))