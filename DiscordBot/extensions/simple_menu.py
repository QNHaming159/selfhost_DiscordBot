import hikari
import lightbulb
from lightbulb.components import Menu, MenuContext

loader = lightbulb.Loader()

class RoleChannelMenu(Menu):
    """A menu with role and channel select menus"""
    
    def __init__(self) -> None:
        super().__init__()
        
        # Add a role select menu
        self.role_select = self.add_role_select(
            self.on_role_select,
            placeholder="Select a role",
            min_values=1,
            max_values=1
        )
        
        # Add a channel select menu
        self.channel_select = self.add_channel_select(
            self.on_channel_select,
            placeholder="Select a channel",
            min_values=1,
            max_values=1
        )
        
        # Add a button to confirm
        self.confirm_button = self.add_interactive_button(
            hikari.ButtonStyle.SUCCESS,
            self.on_confirm,
            label="Confirm Selection"
        )
        
        # Add an exit button
        self.exit_button = self.add_interactive_button(
            hikari.ButtonStyle.DANGER,
            self.on_exit,
            label="Exit"
        )
    
    async def on_role_select(self, ctx: MenuContext) -> None:
        """Handle role selection - acknowledge silently (like defer in Pycord)"""
        # This is the Lightbulb equivalent of await interaction.response.defer()
        # It acknowledges the interaction without sending a visible message
        await ctx.respond(edit=True)
    
    async def on_channel_select(self, ctx: MenuContext) -> None:
        """Handle channel selection - acknowledge silently"""
        await ctx.respond(edit=True)
    
    async def on_confirm(self, ctx: MenuContext) -> None:
        """Handle confirm button press - show final selection"""
        role_values = ctx.selected_values_for(self.role_select)
        channel_values = ctx.selected_values_for(self.channel_select)
        
        role_mention = role_values[0].mention if role_values else "None"
        channel_mention = channel_values[0].mention if channel_values else "None"
        
        embed = hikari.Embed(
            title="✅ Selection Confirmed",
            description=f"**Role:** {role_mention}\n**Channel:** {channel_mention}",
            color=hikari.Color(0x00FF00)
        )
        
        await ctx.respond(embed=embed)
        ctx.stop_interacting()
    
    async def on_exit(self, ctx: MenuContext) -> None:
        """Handle exit button press"""
        await ctx.respond("Menu closed.", flags=hikari.MessageFlag.EPHEMERAL)
        ctx.stop_interacting()

@loader.command
class MenuCommand(
    lightbulb.SlashCommand,
    name="menu",
    description="Display an interactive menu with role and channel selection",
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        """Show an interactive menu"""
        
        if not ctx.guild_id:
            await ctx.respond("This command can only be used in a server!", flags=hikari.MessageFlag.EPHEMERAL)
            return
        
        # Create the menu
        menu = RoleChannelMenu()
        
        # Create an embed to explain the menu
        embed = hikari.Embed(
            title="🔧 Role & Channel Selector",
            description="Use the dropdown menus below to select a role and a channel.\n\n"
                        "• **Role Select** - Choose a role from the server\n"
                        "• **Channel Select** - Choose a text channel\n"
                        "• **Confirm** - Submit your selections\n"
                        "• **Exit** - Close the menu",
            color=hikari.Color(0x00AAFF)
        )
        
        # Send the menu with the embed
        await ctx.respond(embed=embed, components=menu)