"""
Reaction Roles Cog – Handles creation, editing, and management of reaction role messages.
Supports both button-based and emoji-based role assignment.
"""

import asyncio
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

import discord
from discord import Option
from discord.ext import commands
from discord.ui import Button, Modal, Select, View, ChannelSelect, RoleSelect

# -----------------------------------------------------------------------------
# Configuration & Data Handling
# -----------------------------------------------------------------------------

DATA_DIR = Path("data")
DATA_FILE = DATA_DIR / "reaction_roles.json"
LOCK = asyncio.Lock()

logger = logging.getLogger("ReactionRoleBot.cogs.ReactionRoles")

def ensure_data_dir():
    DATA_DIR.mkdir(exist_ok=True)

def backup_corrupted_file(file_path: Path, suffix: str = "corrupt"):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = file_path.with_name(f"{file_path.stem}.{suffix}.{timestamp}{file_path.suffix}")
    shutil.copy(file_path, backup_path)
    logger.warning(f"Corrupted file backed up to {backup_path}")

async def load_storage() -> Dict[int, dict]:
    ensure_data_dir()
    if not DATA_FILE.exists():
        return {}
    try:
        loop = asyncio.get_running_loop()
        with open(DATA_FILE, "r") as f:
            data = await loop.run_in_executor(None, json.load, f)
        return {int(k): v for k, v in data.items()}
    except json.JSONDecodeError as e:
        logger.error(f"Corrupted reaction_roles.json: {e}")
        backup_corrupted_file(DATA_FILE)
        return {}
    except Exception as e:
        logger.exception(f"Unexpected error loading storage: {e}")
        return {}

async def save_storage(data: Dict[int, dict]):
    ensure_data_dir()
    to_save = {str(k): v for k, v in data.items()}
    try:
        loop = asyncio.get_running_loop()
        async with LOCK:
            await loop.run_in_executor(
                None,
                lambda: DATA_FILE.write_text(json.dumps(to_save, indent=2), encoding="utf-8")
            )
    except Exception as e:
        logger.exception(f"Failed to save reaction role data: {e}")

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def parse_color(color_input: Optional[str]) -> discord.Color:
    if not color_input:
        return discord.Color.from_rgb(43, 45, 49)
    if color_input.startswith("#"):
        try:
            return discord.Color.from_str(color_input)
        except ValueError:
            pass
    colour_map = {
        "default": discord.Color.default(),
        "red": discord.Color.red(),
        "green": discord.Color.green(),
        "blue": discord.Color.blue(),
        "yellow": discord.Color.yellow(),
        "purple": discord.Color.purple(),
        "orange": discord.Color.orange(),
        "blurple": discord.Color.blurple(),
        "teal": 0x1abc9c,
        "dark_teal": 0x11806a,
        "green_old": 0x2ecc71,
        "dark_green": 0x1f8b4c,
        "blue_old": 0x3498db,
        "dark_blue": 0x206694,
        "purple_old": 0x9b59b6,
        "dark_purple": 0x71368a,
        "gold": 0xf1c40f,
        "dark_gold": 0xc27c0e,
        "orange_old": 0xe67e22,
        "dark_orange": 0xa84300,
        "red_old": 0xe74c3c,
        "dark_red": 0x992d22,
        "grey": 0x95a5a6,
        "dark_grey": 0x979c9f,
        "darker_grey": 0x7f8c8d,
        "light_grey": 0xbcc0c0,
        "dark_theme": 0x36393F,
        "lighter_theme": 0x42464d,
        "aqua": 0x1abc9c,
    }
    if color_input.lower() in colour_map:
        val = colour_map[color_input.lower()]
        if isinstance(val, discord.Color):
            return val
        return discord.Color(val)
    return discord.Color.from_rgb(43, 45, 49)

def emoji_to_string(emoji: Union[str, discord.Emoji, discord.PartialEmoji]) -> str:
    if isinstance(emoji, str):
        return emoji
    return str(emoji)

def string_to_emoji(emoji_str: str) -> Union[str, discord.PartialEmoji]:
    if emoji_str.startswith("<") and emoji_str.endswith(">"):
        animated = emoji_str.startswith("<a:")
        parts = emoji_str.split(":")
        if len(parts) >= 3:
            emoji_id = int(parts[-1].rstrip(">"))
            name = parts[1] if not animated else parts[1][1:]
            return discord.PartialEmoji(name=name, id=emoji_id, animated=animated)
    return emoji_str

def is_admin(interaction: discord.Interaction, admin_role_ids: List[int]) -> bool:
    if not interaction.guild:
        return False
    member = interaction.guild.get_member(interaction.user.id)
    if not member:
        return False
    return any(role.id in admin_role_ids for role in member.roles)

# -----------------------------------------------------------------------------
# Modals (only InputText components) – Embed only
# -----------------------------------------------------------------------------

class EmbedDetailsModal(Modal):
    def __init__(self, current_data: Optional[dict] = None):
        super().__init__(title="Create Reaction Role Embed", custom_id="embed_modal")
        self.current_data = current_data or {}

        # Title – always required, no special handling
        self.title_input = discord.ui.InputText(
            label="Embed Title (required)",
            style=discord.InputTextStyle.short,
            required=True,
            value=self.current_data.get("title", "")
        )

        # Description – required, but user can type "skip" to leave empty
        default_desc = self.current_data.get("description", "")
        self.description_input = discord.ui.InputText(
            label="Embed Description (type 'skip' for none)",
            style=discord.InputTextStyle.long,
            required=True,
            value=default_desc if default_desc else "skip"
        )

        # Colour – required, type "skip" to use default
        default_colour = self.current_data.get("colour", "")
        self.colour_input = discord.ui.InputText(
            label="Colour (type 'skip' for default)",
            style=discord.InputTextStyle.short,
            required=True,
            value=default_colour if default_colour else "skip"
        )

        # Image URL – required, type "skip" for no image
        default_image = self.current_data.get("image_url", "")
        self.image_url_input = discord.ui.InputText(
            label="Image URL (type 'skip' for none)",
            style=discord.InputTextStyle.short,
            required=True,
            value=default_image if default_image else "skip"
        )

        self.add_item(self.title_input)
        self.add_item(self.description_input)
        self.add_item(self.colour_input)
        self.add_item(self.image_url_input)

    async def callback(self, interaction: discord.Interaction):
        # Convert "skip" (case‑insensitive) to None / empty string
        description = self.description_input.value
        if description.strip().lower() == "skip":
            description = None

        colour = self.colour_input.value
        if colour.strip().lower() == "skip":
            colour = ""

        image_url = self.image_url_input.value
        if image_url.strip().lower() == "skip":
            image_url = None

        view: CreationWizard = self.view
        view.embed_data = {
            "title": self.title_input.value,
            "description": description,
            "colour": colour,
            "image_url": image_url,
        }
        await view.show_type_selection(interaction)

# -----------------------------------------------------------------------------
# Selection Views (for role and style) – used after chat input
# -----------------------------------------------------------------------------

class RoleAndStyleSelectView(View):
    """View for selecting role and button style."""
    def __init__(self, temp_mapping: dict, wizard_view):
        super().__init__(timeout=120)
        self.temp_mapping = temp_mapping
        self.wizard_view = wizard_view

        self.role_select = RoleSelect(
            placeholder="Select a role",
            min_values=1,
            max_values=1,
            custom_id="role_select"
        )
        self.role_select.callback = self.role_select_callback   # ADD THIS
        self.add_item(self.role_select)

        style_options = [
            discord.SelectOption(label="Primary", value="primary", emoji="🔵"),
            discord.SelectOption(label="Secondary", value="secondary", emoji="⚪"),
            discord.SelectOption(label="Success", value="success", emoji="🟢"),
            discord.SelectOption(label="Danger", value="danger", emoji="🔴"),
        ]
        self.style_select = Select(
            placeholder="Select button style",
            options=style_options,
            custom_id="style_select"
        )
        self.style_select.callback = self.style_select_callback   # ADD THIS
        self.add_item(self.style_select)

        confirm = Button(label="Confirm", style=discord.ButtonStyle.success, custom_id="confirm")
        confirm.callback = self.confirm_callback
        self.add_item(confirm)

    async def role_select_callback(self, interaction: discord.Interaction):
        """Acknowledge the role selection without doing anything."""
        await interaction.response.defer()

    async def style_select_callback(self, interaction: discord.Interaction):
        """Acknowledge the style selection without doing anything."""
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        role = self.role_select.values[0]
        style_name = self.style_select.values[0]
        style_map = {
            "primary": discord.ButtonStyle.primary,
            "secondary": discord.ButtonStyle.secondary,
            "success": discord.ButtonStyle.success,
            "danger": discord.ButtonStyle.danger,
        }
        self.temp_mapping["role_id"] = role.id
        self.temp_mapping["style"] = style_name.capitalize()
        self.temp_mapping["style_value"] = style_map[style_name]
        self.wizard_view.mappings.append(self.temp_mapping)
        await interaction.edit_original_response(content="✅ Mapping added!", view=None, delete_after=2)
        await self.wizard_view.refresh_main_wizard_message()


class RoleSelectView(View):
    """View for selecting a role (for emoji-based mappings)."""
    def __init__(self, temp_mapping: dict, wizard_view):
        super().__init__(timeout=120)
        self.temp_mapping = temp_mapping
        self.wizard_view = wizard_view

        self.role_select = RoleSelect(
            placeholder="Select a role",
            min_values=1,
            max_values=1,
            custom_id="role_select"
        )
        self.role_select.callback = self.role_select_callback   # ADD THIS
        self.add_item(self.role_select)

        confirm = Button(label="Confirm", style=discord.ButtonStyle.success, custom_id="confirm")
        confirm.callback = self.confirm_callback
        self.add_item(confirm)

    async def role_select_callback(self, interaction: discord.Interaction):
        """Acknowledge the role selection without doing anything."""
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        role = self.role_select.values[0]
        self.temp_mapping["role_id"] = role.id
        self.wizard_view.mappings.append(self.temp_mapping)
        await interaction.edit_original_response(content="✅ Mapping added!", view=None, delete_after=2)
        await self.wizard_view.refresh_main_wizard_message()

# -----------------------------------------------------------------------------
# Wizard Views
# -----------------------------------------------------------------------------

class CreationWizard(View):
    """Interactive view for creating a reaction role message."""
    def __init__(self, cog, interaction: discord.Interaction, embed_data: dict):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_interaction = interaction
        self.embed_data = embed_data
        self.wizard_type = None          # "buttons" or "emojis"
        self.channel_id = None
        self.mappings = []               # list of mapping dicts
        self.current_message = None      # the ephemeral message being edited

    async def show_type_selection(self, interaction: discord.Interaction):
        """Step 2: Choose button or emoji type."""
        self.clear_items()
        buttons_btn = Button(label="Buttons", style=discord.ButtonStyle.primary, emoji="🔘", custom_id="type_buttons")
        emojis_btn = Button(label="Emojis", style=discord.ButtonStyle.secondary, emoji="😊", custom_id="type_emojis")
        buttons_btn.callback = self.type_callback("buttons")
        emojis_btn.callback = self.type_callback("emojis")
        self.add_item(buttons_btn)
        self.add_item(emojis_btn)

        if self.current_message:
            await interaction.response.edit_message(content="Select reaction type:", view=self)
        else:
            await interaction.response.send_message("Select reaction type:", view=self, ephemeral=True)
            self.current_message = await interaction.original_response()

    def type_callback(self, wizard_type: str):
        async def callback(interaction: discord.Interaction):
            self.wizard_type = wizard_type
            await self.show_channel_selection(interaction)
        return callback

    async def show_channel_selection(self, interaction: discord.Interaction):
        """Step 3: Select target text channel."""
        self.clear_items()
        channel_select = ChannelSelect(
            channel_types=[discord.ChannelType.text],
            placeholder="Select a text channel",
            min_values=1,
            max_values=1,
            custom_id="channel_select"
        )
        channel_select.callback = self.channel_selected
        self.add_item(channel_select)
        await interaction.response.edit_message(content="Select the target text channel:", view=self)

    async def channel_selected(self, interaction: discord.Interaction):
        channel = interaction.data["values"][0]
        self.channel_id = int(channel)
        await self.show_mapping_controls(interaction)

    async def show_mapping_controls(self, interaction: discord.Interaction):
        """Step 4: Show current mappings + Add/Finish buttons."""
        self.clear_items()
        add_btn = Button(label="Add role mapping", style=discord.ButtonStyle.success, emoji="➕", custom_id="add_mapping")
        finish_btn = Button(label="Finish", style=discord.ButtonStyle.primary, emoji="✅", custom_id="finish")
        add_btn.callback = self.add_mapping_callback
        finish_btn.callback = self.finish_callback
        self.add_item(add_btn)
        self.add_item(finish_btn)

        content = "**Current role mappings:**\n"
        if not self.mappings:
            content += "*No mappings added yet.*\n"
        else:
            for idx, m in enumerate(self.mappings, 1):
                if self.wizard_type == "buttons":
                    content += f"{idx}. `{m['label']}` → <@&{m['role_id']}> (style: {m.get('style', 'Primary')})\n"
                else:
                    content += f"{idx}. {m['emoji']} → <@&{m['role_id']}>\n"
        content += "\nPress **Add role mapping** to add another, or **Finish** to create the message."

        await interaction.response.edit_message(content=content, view=self)

    async def add_mapping_callback(self, interaction: discord.Interaction):
        """Ask for button label or emoji via chat message (no modal)."""
        prompt = "Please type the button label (for button type) or emoji (for emoji type) in the chat. You have 60 seconds."
        await interaction.response.send_message(prompt, ephemeral=True, delete_after=60)
        prompt_msg = await interaction.original_response()

        def check(msg: discord.Message):
            return msg.author.id == interaction.user.id and msg.channel.id == interaction.channel.id

        try:
            msg = await self.cog.bot.wait_for('message', timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await prompt_msg.delete()
            await interaction.followup.send("Timed out. Please start over.", ephemeral=True, delete_after=10)
            return

        await msg.delete()
        await prompt_msg.delete()
        user_input = msg.content.strip()
        if not user_input:
            await interaction.followup.send("Empty input. Please try again.", ephemeral=True, delete_after=10)
            return

        if self.wizard_type == "buttons":
            temp_mapping = {"label": user_input}
            await self.present_role_and_style_selection(interaction, temp_mapping)
        else:
            temp_mapping = {"emoji": user_input}
            await self.present_role_selection(interaction, temp_mapping)

    async def present_role_and_style_selection(self, interaction: discord.Interaction, temp_mapping: dict):
        view = RoleAndStyleSelectView(temp_mapping, self)
        await interaction.followup.send("Select the role and button style:", ephemeral=True, view=view, delete_after=120)

    async def present_role_selection(self, interaction: discord.Interaction, temp_mapping: dict):
        view = RoleSelectView(temp_mapping, self)
        await interaction.followup.send("Select the role:", ephemeral=True, view=view, delete_after=120)

    async def refresh_main_wizard_message(self):
        """Update the main wizard message (the one showing current mappings)."""
        if not self.current_message:
            return
        self.clear_items()
        add_btn = Button(label="Add role mapping", style=discord.ButtonStyle.success, emoji="➕", custom_id="add_mapping")
        finish_btn = Button(label="Finish", style=discord.ButtonStyle.primary, emoji="✅", custom_id="finish")
        add_btn.callback = self.add_mapping_callback
        finish_btn.callback = self.finish_callback
        self.add_item(add_btn)
        self.add_item(finish_btn)

        content = "**Current role mappings:**\n"
        if not self.mappings:
            content += "*No mappings added yet.*\n"
        else:
            for idx, m in enumerate(self.mappings, 1):
                if self.wizard_type == "buttons":
                    content += f"{idx}. `{m['label']}` → <@&{m['role_id']}> (style: {m.get('style', 'Primary')})\n"
                else:
                    content += f"{idx}. {m['emoji']} → <@&{m['role_id']}>\n"
        content += "\nPress **Add role mapping** to add another, or **Finish** to create the message."

        await self.current_message.edit(content=content, view=self)

    async def finish_callback(self, interaction: discord.Interaction):
        """Step 5: Create the final embed message in the selected channel."""
        if not self.mappings:
            await interaction.response.send_message("You must add at least one role mapping.", ephemeral=True, delete_after=10)
            return

        await interaction.response.defer(ephemeral=True)

        channel = self.original_interaction.guild.get_channel(self.channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("Invalid channel selected.", ephemeral=True, delete_after=10)
            return

        embed = discord.Embed(
            title=self.embed_data.get("title"),
            description=self.embed_data.get("description"),
            color=parse_color(self.embed_data.get("colour"))
        )
        if self.embed_data.get("image_url"):
            embed.set_image(url=self.embed_data["image_url"])

        try:
            if self.wizard_type == "buttons":
                view = RoleButtonsView(self.cog, self.mappings, self.original_interaction.guild_id)
                message = await channel.send(embed=embed, view=view)
            else:
                message = await channel.send(embed=embed)
                for mapping in self.mappings:
                    emoji = string_to_emoji(mapping["emoji"])
                    try:
                        await message.add_reaction(emoji)
                    except Exception as e:
                        logger.warning(f"Failed to add reaction {emoji}: {e}")
        except discord.Forbidden:
            await interaction.followup.send(f"Missing permissions to send or manage messages in {channel.mention}.", ephemeral=True)
            return
        except Exception as e:
            logger.exception(f"Failed to send reaction role message: {e}")
            await interaction.followup.send("An unexpected error occurred while sending the message.", ephemeral=True)
            return

        config = {
            "type": self.wizard_type,
            "channel_id": channel.id,
            "embed": self.embed_data,
            "mappings": self.mappings,
        }
        self.cog.configs[message.id] = config
        await save_storage(self.cog.configs)

        await interaction.followup.send(
            f"✅ Reaction role message created in {channel.mention} (ID: {message.id})",
            ephemeral=True, delete_after=30
        )
        self.stop()

class RoleButtonsView(View):
    """Persistent view for button-based reaction roles."""
    def __init__(self, cog, mappings: List[dict], guild_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        for mapping in mappings:
            label = mapping["label"]
            role_id = mapping["role_id"]
            style_name = mapping.get("style", "Primary")
            style = getattr(discord.ButtonStyle, style_name.lower(), discord.ButtonStyle.primary)
            button = Button(label=label, style=style, custom_id=f"rr_{role_id}")
            button.callback = self.create_callback(role_id)
            self.add_item(button)

    def create_callback(self, role_id: int):
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            guild = interaction.guild
            if not guild:
                await interaction.followup.send("Error: guild not found.", ephemeral=True, delete_after=10)
                return
            member = guild.get_member(interaction.user.id)
            if not member:
                await interaction.followup.send("Error: member not found.", ephemeral=True, delete_after=10)
                return
            role = guild.get_role(role_id)
            if not role:
                await interaction.followup.send("Role no longer exists.", ephemeral=True, delete_after=10)
                return
            if role in member.roles:
                await member.remove_roles(role, reason="Reaction role button")
                action = "removed from"
            else:
                await member.add_roles(role, reason="Reaction role button")
                action = "added to"
            await interaction.followup.send(f"✅ {action} {role.mention}", ephemeral=True, delete_after=30)
        return callback

class EditWizard(View):
    """View for editing an existing reaction role message."""
    def __init__(self, cog, interaction: discord.Interaction, message_id: int, config: dict):
        super().__init__(timeout=120)
        self.cog = cog
        self.original_interaction = interaction
        self.message_id = message_id
        self.config = config

        self.add_item(Button(label="Edit Embed", style=discord.ButtonStyle.primary, custom_id="edit_embed", emoji="📝"))
        self.add_item(Button(label="Edit Mappings", style=discord.ButtonStyle.secondary, custom_id="edit_mappings", emoji="🔧"))
        self.add_item(Button(label="Delete Message", style=discord.ButtonStyle.danger, custom_id="delete_msg", emoji="🗑️"))

        for item in self.children:
            item.callback = self.handle_button

    async def handle_button(self, interaction: discord.Interaction):
        custom_id = interaction.custom_id
        if custom_id == "edit_embed":
            await self.edit_embed(interaction)
        elif custom_id == "edit_mappings":
            await self.edit_mappings(interaction)
        elif custom_id == "delete_msg":
            await self.delete_message(interaction)

    async def edit_embed(self, interaction: discord.Interaction):
        modal = EmbedDetailsModal(current_data=self.config.get("embed", {}))
        modal.view = self
        await interaction.response.send_modal(modal)

    async def edit_mappings(self, interaction: discord.Interaction):
        view = MappingManageView(self.cog, self.message_id, self.config, self.original_interaction)
        await interaction.response.send_message("Manage role mappings:", view=view, ephemeral=True)

    async def delete_message(self, interaction: discord.Interaction):
        confirm_view = ConfirmDeleteView(self)
        await interaction.response.send_message(
            f"⚠️ Are you sure you want to delete reaction role message {self.message_id}?",
            view=confirm_view, ephemeral=True
        )

    async def apply_embed_edit(self, interaction: discord.Interaction, embed_data: dict):
        self.config["embed"] = embed_data
        channel = self.original_interaction.guild.get_channel(self.config["channel_id"])
        if channel:
            try:
                msg = await channel.fetch_message(self.message_id)
                embed = discord.Embed(
                    title=embed_data.get("title"),
                    description=embed_data.get("description") or discord.Embed.Empty,
                    color=parse_color(embed_data.get("colour"))
                )
                if embed_data.get("image_url"):
                    embed.set_image(url=embed_data["image_url"])
                await msg.edit(embed=embed)
            except Exception as e:
                logger.warning(f"Failed to edit embed message: {e}")
        self.cog.configs[self.message_id] = self.config
        await save_storage(self.cog.configs)
        await interaction.response.edit_message(content="✅ Embed updated.", view=None, delete_after=5)

    async def finalize_deletion(self, interaction: discord.Interaction):
        channel = self.original_interaction.guild.get_channel(self.config["channel_id"])
        if channel:
            try:
                msg = await channel.fetch_message(self.message_id)
                await msg.delete()
            except Exception as e:
                logger.warning(f"Failed to delete message {self.message_id}: {e}")
        self.cog.configs.pop(self.message_id, None)
        await save_storage(self.cog.configs)
        await interaction.response.edit_message(content="✅ Message deleted and configuration removed.", view=None, delete_after=10)
        self.stop()

class ConfirmDeleteView(View):
    def __init__(self, parent_wizard: EditWizard):
        super().__init__(timeout=30)
        self.parent = parent_wizard
        confirm = Button(label="Yes, delete", style=discord.ButtonStyle.danger, custom_id="confirm")
        cancel = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel")
        confirm.callback = self.confirm_callback
        cancel.callback = self.cancel_callback
        self.add_item(confirm)
        self.add_item(cancel)

    async def confirm_callback(self, interaction: discord.Interaction):
        await self.parent.finalize_deletion(interaction)

    async def cancel_callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="Deletion cancelled.", view=None, delete_after=5)

class MappingManageView(View):
    """View to add, remove, or edit mappings (for editing existing messages)."""
    def __init__(self, cog, message_id: int, config: dict, original_interaction: discord.Interaction):
        super().__init__(timeout=120)
        self.cog = cog
        self.message_id = message_id
        self.config = config
        self.original_interaction = original_interaction
        self.refresh_display()

    def refresh_display(self):
        self.clear_items()
        add_btn = Button(label="Add Mapping", style=discord.ButtonStyle.success, custom_id="add_mapping")
        add_btn.callback = self.add_mapping
        self.add_item(add_btn)

        for idx, mapping in enumerate(self.config["mappings"]):
            label = mapping.get("label") or mapping.get("emoji", "?")
            edit_btn = Button(label=f"Edit {label}", style=discord.ButtonStyle.secondary, custom_id=f"edit_{idx}")
            remove_btn = Button(label="❌", style=discord.ButtonStyle.danger, custom_id=f"remove_{idx}")
            edit_btn.callback = self.create_edit_callback(idx)
            remove_btn.callback = self.create_remove_callback(idx)
            self.add_item(edit_btn)
            self.add_item(remove_btn)

        done_btn = Button(label="Done", style=discord.ButtonStyle.primary, custom_id="done")
        done_btn.callback = self.done
        self.add_item(done_btn)

    def create_edit_callback(self, idx: int):
        async def callback(interaction: discord.Interaction):
            wizard_type = self.config["type"]
            prompt = "Please type the new button label or emoji in the chat. You have 60 seconds."
            await interaction.response.send_message(prompt, ephemeral=True, delete_after=60)
            prompt_msg = await interaction.original_response()

            def check(msg: discord.Message):
                return msg.author.id == interaction.user.id and msg.channel.id == interaction.channel.id

            try:
                msg = await self.cog.bot.wait_for('message', timeout=60.0, check=check)
            except asyncio.TimeoutError:
                await prompt_msg.delete()
                await interaction.followup.send("Timed out.", ephemeral=True, delete_after=10)
                return
            await msg.delete()
            await prompt_msg.delete()
            user_input = msg.content.strip()
            if not user_input:
                await interaction.followup.send("Empty input.", ephemeral=True, delete_after=10)
                return

            if wizard_type == "buttons":
                temp_mapping = {"label": user_input}
                view = RoleAndStyleSelectView(temp_mapping, self)
                await interaction.followup.send("Select the role and button style:", ephemeral=True, view=view, delete_after=120)
            else:
                temp_mapping = {"emoji": user_input}
                view = RoleSelectView(temp_mapping, self)
                await interaction.followup.send("Select the role:", ephemeral=True, view=view, delete_after=120)

            self.editing_index = idx
        return callback

    def create_remove_callback(self, idx: int):
        async def callback(interaction: discord.Interaction):
            del self.config["mappings"][idx]
            await self.save_and_refresh(interaction)
        return callback

    async def add_mapping(self, interaction: discord.Interaction):
        wizard_type = self.config["type"]
        prompt = "Please type the button label or emoji in the chat. You have 60 seconds."
        await interaction.response.send_message(prompt, ephemeral=True, delete_after=60)
        prompt_msg = await interaction.original_response()

        def check(msg: discord.Message):
            return msg.author.id == interaction.user.id and msg.channel.id == interaction.channel.id

        try:
            msg = await self.cog.bot.wait_for('message', timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await prompt_msg.delete()
            await interaction.followup.send("Timed out.", ephemeral=True, delete_after=10)
            return
        await msg.delete()
        await prompt_msg.delete()
        user_input = msg.content.strip()
        if not user_input:
            await interaction.followup.send("Empty input.", ephemeral=True, delete_after=10)
            return

        if wizard_type == "buttons":
            temp_mapping = {"label": user_input}
            view = RoleAndStyleSelectView(temp_mapping, self)
            await interaction.followup.send("Select the role and button style:", ephemeral=True, view=view, delete_after=120)
        else:
            temp_mapping = {"emoji": user_input}
            view = RoleSelectView(temp_mapping, self)
            await interaction.followup.send("Select the role:", ephemeral=True, view=view, delete_after=120)

    async def save_and_refresh(self, interaction: discord.Interaction):
        await self.update_actual_message()
        self.cog.configs[self.message_id] = self.config
        await save_storage(self.cog.configs)
        self.refresh_display()
        await interaction.response.edit_message(content="Mappings updated.", view=self)

    async def update_actual_message(self):
        channel = self.original_interaction.guild.get_channel(self.config["channel_id"])
        if not channel:
            return
        try:
            msg = await channel.fetch_message(self.message_id)
            if self.config["type"] == "buttons":
                new_view = RoleButtonsView(self.cog, self.config["mappings"], self.original_interaction.guild_id)
                await msg.edit(view=new_view)
            else:
                await msg.clear_reactions()
                for mapping in self.config["mappings"]:
                    emoji = string_to_emoji(mapping["emoji"])
                    await msg.add_reaction(emoji)
        except Exception as e:
            logger.warning(f"Failed to update message {self.message_id}: {e}")

    async def done(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="✅ Mappings saved.", view=None, delete_after=5)
        self.stop()

# -----------------------------------------------------------------------------
# Main Cog
# -----------------------------------------------------------------------------

class ReactionRoles(commands.Cog):
    """Reaction Role management cog."""
    def __init__(self, bot: discord.Bot, config: dict):
        self.bot = bot
        self.guild_id = config["guild_id"]
        self.admin_role_ids = config["admin_role_ids"]
        self.configs: Dict[int, dict] = {}
        self.bot.loop.create_task(self._initialize())

    async def _initialize(self):
        await self.bot.wait_until_ready()
        self.configs = await load_storage()
        await self.restore_button_messages()
        logger.info(f"Restored {len([c for c in self.configs.values() if c['type'] == 'buttons'])} button-based reaction messages")

    async def restore_button_messages(self):
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            logger.error(f"Guild {self.guild_id} not found. Cannot restore button messages.")
            return
        tasks = []
        for msg_id, config in self.configs.items():
            if config["type"] == "buttons":
                tasks.append(self.restore_single_button_message(guild, msg_id, config))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def restore_single_button_message(self, guild: discord.Guild, msg_id: int, config: dict):
        channel = guild.get_channel(config["channel_id"])
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.warning(f"Channel {config['channel_id']} for message {msg_id} not found or invalid.")
            return
        try:
            msg = await channel.fetch_message(msg_id)
            view = RoleButtonsView(self, config["mappings"], guild.id)
            await msg.edit(view=view)
        except discord.NotFound:
            logger.warning(f"Message {msg_id} not found. Removing from config.")
            del self.configs[msg_id]
            await save_storage(self.configs)
        except discord.Forbidden:
            logger.warning(f"No permission to edit message {msg_id} in channel {channel.id}")
        except Exception as e:
            logger.warning(f"Failed to restore button message {msg_id}: {e}")

    @discord.slash_command(name="create_reaction_role", description="Create a new reaction role embed (admin only)")
    async def create_reaction_role(self, ctx: discord.ApplicationContext):
        if not is_admin(ctx, self.admin_role_ids):
            await ctx.respond("You don't have permission to use this command.", ephemeral=True, delete_after=10)
            return
        modal = EmbedDetailsModal()
        view = CreationWizard(self, ctx, {})
        modal.view = view
        await ctx.send_modal(modal)

    @discord.slash_command(name="edit_reaction_role", description="Edit an existing reaction role embed (admin only)")
    async def edit_reaction_role(self, ctx: discord.ApplicationContext,
                                 message_id: Option(str, "The message ID of the reaction role embed", required=True)):
        if not is_admin(ctx, self.admin_role_ids):
            await ctx.respond("You don't have permission to use this command.", ephemeral=True, delete_after=10)
            return
        try:
            msg_id = int(message_id)
        except ValueError:
            await ctx.respond("Invalid message ID. Please enter a numeric ID.", ephemeral=True, delete_after=10)
            return
        config = self.configs.get(msg_id)
        if not config:
            await ctx.respond(f"No reaction role configuration found for message ID {msg_id}.", ephemeral=True, delete_after=10)
            return
        view = EditWizard(self, ctx, msg_id, config)
        await ctx.respond(f"Editing reaction role message {msg_id}. Choose an option:", view=view, ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await self.handle_reaction(payload, add=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await self.handle_reaction(payload, add=False)

    async def handle_reaction(self, payload: discord.RawReactionActionEvent, add: bool):
        if payload.user_id == self.bot.user.id:
            return
        config = self.configs.get(payload.message_id)
        if not config or config["type"] != "emojis":
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        if not member:
            return
        reaction_emoji = str(payload.emoji)
        matching_mapping = None
        for mapping in config["mappings"]:
            if mapping["emoji"] == reaction_emoji:
                matching_mapping = mapping
                break
        if not matching_mapping:
            return
        role = guild.get_role(matching_mapping["role_id"])
        if not role:
            return
        try:
            if add:
                if role not in member.roles:
                    await member.add_roles(role, reason="Reaction role (emoji)")
                    action_text = f"✅ {member.display_name} got role {role.name}"
                else:
                    return
            else:
                if role in member.roles:
                    await member.remove_roles(role, reason="Reaction role (emoji)")
                    action_text = f"❌ {member.display_name} lost role {role.name}"
                else:
                    return
            channel = self.bot.get_channel(payload.channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                await channel.send(action_text, delete_after=5)
        except Exception as e:
            logger.warning(f"Failed to {'add' if add else 'remove'} role via reaction: {e}")