import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import uuid
import shutil
import asyncio
from typing import Dict, Any, Optional

# ============ DATABASE CLASS ============

class Database:
    """Async database handler with memory caching"""
    def __init__(self, filepath: str = 'config.json'):
        self.filepath = filepath
        self.data: Dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._load_sync()
    
    def _load_sync(self):
        """Synchronous load (called once at startup)"""
        if not os.path.exists(self.filepath):
            self.data = {}
            return
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    self.data = {}
                else:
                    self.data = json.loads(content)
        except:
            self.data = {}
    
    async def save(self):
        """Asynchronous save using thread pool"""
        async with self._lock:
            await asyncio.to_thread(self._save_sync)
    
    def _save_sync(self):
        """Synchronous save (runs in thread pool)"""
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving: {e}")
    
    def get(self, key: str, default=None):
        """Get value from cache"""
        return self.data.get(key, default)
    
    def set(self, key: str, value: Any):
        """Set value in cache and save async"""
        self.data[key] = value
        asyncio.create_task(self.save())
    
    def delete(self, key: str):
        """Delete from cache and save async"""
        if key in self.data:
            del self.data[key]
            asyncio.create_task(self.save())
    
    def items(self):
        """Return cached items"""
        return self.data.items()
    
    def guild_messages(self, guild_id: int):
        """Get messages for a specific guild from cache"""
        return {k: v for k, v in self.data.items() if v.get('guild_id') == guild_id}

# ============ DATABASE INSTANCE ============
db = Database()

# ============ BUTTON COMPONENTS ============

class PersistentRoleButton(discord.ui.Button):
    """Persistent button that survives bot restarts"""
    def __init__(self, role_id: int, label: str, emoji: str, style: str, custom_id: str):
        super().__init__(
            label=label,
            emoji=emoji,
            style=getattr(discord.ButtonStyle, style),
            custom_id=custom_id
        )
        self.role_id = role_id
    
    async def callback(self, interaction: discord.Interaction):
        # Fast acknowledgment - immediately defer
        await interaction.response.defer(ephemeral=True)
        
        # Get role from cache (using guild.get_role is cached by Discord)
        role = interaction.guild.get_role(self.role_id)
        
        if not role:
            await interaction.followup.send("❌ Role not found!", ephemeral=True)
            return
        
        # Toggle role
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            action = "removed"
            emoji = "❌"
            color = 0xff0000
        else:
            await interaction.user.add_roles(role)
            action = "added"
            emoji = "✅"
            color = 0x00ff00
        
        # Send response
        embed = discord.Embed(
            title=f"{emoji} Role {action.capitalize()}!",
            description=f"You have been {action} the **{role.name}** role.",
            color=color
        )
        embed.set_footer(text=f"In {interaction.guild.name}")
        
        await interaction.followup.send(embed=embed, ephemeral=True)


class PersistentRoleView(discord.ui.View):
    """Persistent view that survives bot restarts"""
    def __init__(self, roles_data: Dict):
        super().__init__(timeout=None)
        for role_name, data in roles_data.items():
            custom_id = f"rr_{data['role_id']}_{uuid.uuid4().hex[:8]}"
            button = PersistentRoleButton(
                role_id=data['role_id'],
                label=data.get('label', role_name),
                emoji=data.get('emoji', '🎭'),
                style=data.get('style', 'primary'),
                custom_id=custom_id
            )
            self.add_item(button)


# ============ MODAL ============

class CreateRRModal(discord.ui.Modal, title='Create Reaction Role Message'):
    def __init__(self, bot, target_channel: discord.TextChannel):
        super().__init__()
        self.bot = bot
        self.target_channel = target_channel
    
    type_select = discord.ui.TextInput(
        label='Type (buttons or emojis)',
        placeholder='Enter "buttons" or "emojis"',
        required=True,
        max_length=10
    )
    
    title = discord.ui.TextInput(
        label='Embed Title',
        placeholder='Enter title (or "none" for no title)',
        required=False,
        max_length=256
    )
    
    description = discord.ui.TextInput(
        label='Embed Description',
        placeholder='Describe what roles users can get',
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=2000
    )
    
    color = discord.ui.TextInput(
        label='Embed Color',
        placeholder='red, green, blue, purple, gold, or hex like #FF5733',
        required=False,
        default='blue'
    )
    
    image = discord.ui.TextInput(
        label='Image (optional)',
        placeholder='URL only - or "none"',
        required=False,
        max_length=500
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        reaction_type = self.type_select.value.lower()
        if reaction_type not in ['buttons', 'emojis']:
            await interaction.response.send_message("❌ Type must be 'buttons' or 'emojis'", ephemeral=True)
            return
        
        color_map = {
            'red': 0xff0000, 'green': 0x00ff00, 'blue': 0x0000ff,
            'purple': 0x9b59b6, 'gold': 0xf1c40f
        }
        color_input = self.color.value.lower()
        if color_input in color_map:
            color = color_map[color_input]
        elif color_input.startswith('#'):
            try:
                color = int(color_input[1:], 16)
            except:
                color = 0x0000ff
        else:
            color = 0x0000ff
        
        image_url = None
        image_type = None
        image_value = self.image.value.strip() if self.image.value else ""
        
        if image_value and image_value.lower() != 'none':
            parts = image_value.split()
            if len(parts) >= 2 and parts[1].lower() in ['thumbnail', 'image']:
                image_url = parts[0]
                image_type = parts[1].lower()
            else:
                image_url = parts[0]
                image_type = 'image'
        
        temp_data = {
            'type': reaction_type,
            'title': None if self.title.value.lower() == 'none' else self.title.value,
            'description': self.description.value,
            'color': color,
            'image_url': image_url,
            'image_type': image_type,
            'target_channel': self.target_channel,
        }
        
        await interaction.response.send_message(
            f"✅ Basic info collected! Now send me the **roles** for this {reaction_type}-based message.\n\n"
            f"**Format for {reaction_type}:**\n"
            + ("`RoleName :emoji: @Role style`\nStyles: primary, secondary, success, danger\nExample: `Gamer 🎮 @Gamer primary`\nType `done` when finished."
               if reaction_type == 'buttons' else
               "`:emoji: @Role`\nExample: `🎮 @GamerRole`\nType `done` when finished."),
            ephemeral=True
        )
        
        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel
        
        roles_data = {}
        while True:
            try:
                msg = await self.bot.wait_for('message', check=check, timeout=120)
                
                if msg.content.lower() == 'done':
                    break
                
                if reaction_type == 'buttons':
                    parts = msg.content.split()
                    if len(parts) >= 4:
                        role_name = parts[0]
                        emoji = parts[1]
                        role_mention = parts[2]
                        style = parts[3].lower()
                        
                        if style not in ['primary', 'secondary', 'success', 'danger']:
                            style = 'primary'
                        
                        try:
                            role_id = int(role_mention.strip('<@&>'))
                            role = interaction.guild.get_role(role_id)
                            
                            if role:
                                roles_data[role_name] = {
                                    'role_id': role_id,
                                    'emoji': emoji,
                                    'label': role_name,
                                    'style': style
                                }
                                await interaction.followup.send(f"✅ Added: {emoji} {role_name} -> {role.name}", ephemeral=True)
                            else:
                                await interaction.followup.send("❌ Role not found.", ephemeral=True)
                        except:
                            await interaction.followup.send("❌ Invalid role mention. Use @Role", ephemeral=True)
                    else:
                        await interaction.followup.send("❌ Invalid format. Use: `RoleName :emoji: @Role style`", ephemeral=True)
                
                else:
                    parts = msg.content.split()
                    if len(parts) >= 2:
                        emoji = parts[0]
                        role_mention = parts[1]
                        try:
                            role_id = int(role_mention.strip('<@&>'))
                            role = interaction.guild.get_role(role_id)
                            
                            if role:
                                roles_data[emoji] = {
                                    'role_id': role_id,
                                    'emoji': emoji
                                }
                                await interaction.followup.send(f"✅ Added: {emoji} -> {role.name}", ephemeral=True)
                            else:
                                await interaction.followup.send("❌ Role not found.", ephemeral=True)
                        except:
                            await interaction.followup.send("❌ Invalid role mention.", ephemeral=True)
                    else:
                        await interaction.followup.send("❌ Invalid format. Use: `:emoji: @Role`", ephemeral=True)
                        
            except TimeoutError:
                await interaction.followup.send("⏰ Timed out collecting roles. Please start over.", ephemeral=True)
                return
        
        if not roles_data:
            await interaction.followup.send("❌ No roles added. Cancelled.", ephemeral=True)
            return
        
        # Create and send the embed
        embed = discord.Embed(
            title=temp_data['title'],
            description=temp_data['description'],
            color=temp_data['color']
        )
        
        if temp_data['image_url'] and temp_data['image_type'] == 'image':
            embed.set_image(url=temp_data['image_url'])
        elif temp_data['image_url'] and temp_data['image_type'] == 'thumbnail':
            embed.set_thumbnail(url=temp_data['image_url'])
        
        if reaction_type == 'buttons':
            for role_name, data in roles_data.items():
                role = interaction.guild.get_role(data['role_id'])
                embed.add_field(
                    name=f"{data['emoji']} {role_name}",
                    value=role.mention,
                    inline=True
                )
            embed.set_footer(text="Click the buttons to get roles!")
            view = PersistentRoleView(roles_data)
            message = await temp_data['target_channel'].send(embed=embed, view=view)
        else:
            for emoji, data in roles_data.items():
                role = interaction.guild.get_role(data['role_id'])
                embed.add_field(name=emoji, value=role.mention, inline=True)
            embed.set_footer(text="React to get roles!")
            message = await temp_data['target_channel'].send(embed=embed)
            for emoji in roles_data.keys():
                await message.add_reaction(emoji)
        
        # Save to database (async)
        db.set(str(message.id), {
            'message_id': message.id,
            'channel_id': message.channel.id,
            'guild_id': message.guild.id,
            'type': reaction_type,
            'image_url': temp_data['image_url'],
            'image_type': temp_data['image_type'],
            'title': temp_data['title'],
            'description': temp_data['description'],
            'color': temp_data['color'],
            'roles': roles_data
        })
        
        await interaction.followup.send(f"✅ Reaction role created in {temp_data['target_channel'].mention}! ID: `{message.id}`", ephemeral=True)


# ============ MAIN COG ============

class ReactionRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._restore_task = None

    async def cog_load(self):
        """Auto-restore when cog is loaded"""
        self._restore_task = asyncio.create_task(self._auto_restore())

    async def _auto_restore(self):
        """Wait for bot to be ready, then restore buttons"""
        await self.bot.wait_until_ready()
        await asyncio.sleep(3)
        restored = await self.restore_buttons()
        if restored > 0:
            print(f"✅ Restored {restored} reaction role button(s)")

    @app_commands.command(name="rr_create", description="Create a new reaction role message")
    @app_commands.default_permissions(administrator=True)
    async def rr_create(self, interaction: discord.Interaction):
        # Create a channel select component (much faster than manual loop)
        select = discord.ui.ChannelSelect(
            placeholder="Select a channel",
            channel_types=[discord.ChannelType.text]
        )
        
        view = discord.ui.View(timeout=60)
        
        async def select_callback(select_interaction: discord.Interaction):
            if select_interaction.user != interaction.user:
                await select_interaction.response.send_message("This isn't for you!", ephemeral=True)
                return
            
            selected_channel = select_interaction.data['values'][0]
            target_channel = interaction.guild.get_channel(int(selected_channel))
            
            # Send modal as the response (fast acknowledgment)
            modal = CreateRRModal(self.bot, target_channel)
            await select_interaction.response.send_modal(modal)
        
        select.callback = select_callback
        view.add_item(select)
        
        # Add current channel button as alternative
        current_btn = discord.ui.Button(label="📌 Use Current Channel", style=discord.ButtonStyle.primary)
        
        async def current_callback(button_interaction: discord.Interaction):
            if button_interaction.user != interaction.user:
                await button_interaction.response.send_message("This isn't for you!", ephemeral=True)
                return
            
            modal = CreateRRModal(self.bot, interaction.channel)
            await button_interaction.response.send_modal(modal)
        
        current_btn.callback = current_callback
        view.add_item(current_btn)
        
        await interaction.response.send_message(
            "**📝 Create Reaction Role Message**\n\nSelect a channel:",
            view=view,
            ephemeral=True
        )

    @app_commands.command(name="rr_delete", description="Delete a reaction role message")
    @app_commands.default_permissions(administrator=True)
    async def rr_delete(self, interaction: discord.Interaction, message_id: str):
        await interaction.response.defer(ephemeral=True)
        
        data = db.get(str(message_id))
        
        if data:
            channel = self.bot.get_channel(data['channel_id'])
            
            try:
                if channel:
                    msg = await channel.fetch_message(int(message_id))
                    await msg.delete()
                await interaction.followup.send(f"✅ Deleted reaction role message `{message_id}`", ephemeral=True)
            except:
                await interaction.followup.send(f"⚠️ Could not delete message, but removing from database.", ephemeral=True)
            
            db.delete(str(message_id))
        else:
            await interaction.followup.send(f"❌ No reaction role found with ID `{message_id}`.", ephemeral=True)

    @app_commands.command(name="rr_list", description="List all reaction role messages")
    async def rr_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        guild_messages = db.guild_messages(interaction.guild.id)
        
        if not guild_messages:
            await interaction.followup.send("No reaction role messages found.", ephemeral=True)
            return
        
        embed = discord.Embed(title="📋 Reaction Role Messages", color=discord.Color.blue())
        for msg_id, data in guild_messages.items():
            channel = self.bot.get_channel(data['channel_id'])
            role_count = len(data.get('roles', {}))
            msg_type = "🔘 Buttons" if data.get('type') == 'buttons' else "😊 Emojis"
            embed.add_field(
                name=f"ID: {msg_id}",
                value=f"Channel: {channel.mention if channel else 'Unknown'}\nType: {msg_type}\nRoles: {role_count}",
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="rr_restore", description="Manually restore all reaction role buttons")
    @app_commands.default_permissions(administrator=True)
    async def rr_restore(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        restored = await self.restore_buttons()
        await interaction.followup.send(f"✅ Restored {restored} reaction role button messages!", ephemeral=True)

    async def restore_buttons(self) -> int:
        """Restore all button views from the database using parallel execution"""
        tasks = []
        
        for msg_id, data in db.items():
            if data.get('type') == 'buttons':
                channel = self.bot.get_channel(data['channel_id'])
                if channel:
                    tasks.append(self._restore_single_button(msg_id, data, channel))
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            restored_count = sum(1 for r in results if r is True)
            return restored_count
        return 0
    
    async def _restore_single_button(self, msg_id: str, data: Dict, channel: discord.TextChannel) -> bool:
        """Restore a single button view"""
        try:
            message = await channel.fetch_message(int(msg_id))
            view = PersistentRoleView(data['roles'])
            await message.edit(view=view)
            return True
        except:
            return False

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        
        data = db.get(str(payload.message_id))
        
        if data and data.get('type') == 'emojis':
            emoji_str = str(payload.emoji)
            
            if emoji_str in data.get('roles', {}):
                guild = self.bot.get_guild(payload.guild_id)
                if not guild:
                    return
                
                # Use get_member (cached) instead of fetch_member (API call)
                member = guild.get_member(payload.user_id)
                if not member:
                    return
                
                role_id = data['roles'][emoji_str]['role_id']
                role = guild.get_role(role_id)
                
                if role and member and role not in member.roles:
                    await member.add_roles(role)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        
        data = db.get(str(payload.message_id))
        
        if data and data.get('type') == 'emojis':
            emoji_str = str(payload.emoji)
            
            if emoji_str in data.get('roles', {}):
                guild = self.bot.get_guild(payload.guild_id)
                if not guild:
                    return
                
                # Use get_member (cached) instead of fetch_member (API call)
                member = guild.get_member(payload.user_id)
                if not member:
                    return
                
                role_id = data['roles'][emoji_str]['role_id']
                role = guild.get_role(role_id)
                
                if role and member and role in member.roles:
                    await member.remove_roles(role)


async def setup(bot):
    await bot.add_cog(ReactionRoles(bot))