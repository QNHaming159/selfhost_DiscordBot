import hikari
import lightbulb
from lightbulb.components import Menu, MenuContext

loader = lightbulb.Loader()

class RoleChannelMenu(Menu):
    """A menu with role and channel select menus"""

    def __init__(self) -> None:
        super().__init__()
        
        # Add a role select menu
        self.role_values = None
        self.role_select = self.add_role_select(
            self.on_role_select,
            placeholder="Select a role",
            min_values=1,
            max_values=1
        )

        # Add a channel select menu
        self.channel_values = None
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

    async def on_role_select(self, ctx: MenuContext) -> None:
        self.role_values = ctx.selected_values_for(self.role_select)
        await ctx.respond(edit=True)
    
    async def on_channel_select(self, ctx: MenuContext) -> None:
        self.channel_values = ctx.selected_values_for(self.channel_select)
        await ctx.respond(edit=True)
    
    async def on_confirm(self, ctx: MenuContext) -> None:
        role_mention =  self.role_values[0].mention
        channel_mention = self.channel_values[0].mention
        
        embed = hikari.Embed(
            title="✅ Selection Confirmed",
            description=f"**Role:** {role_mention}\n**Channel:** {channel_mention}",
            color=hikari.Color(0x00FF00)
        )
        
        await ctx.respond(embed=embed)
        ctx.stop_interacting()
    
@loader.command
class MenuCommand(
    lightbulb.SlashCommand,
    name="menu2",
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
                        "• **Confirm** - Submit your selections\n",
            color=hikari.Color(0x00AAFF)
        )
        
        # Send the menu with the embed
        await ctx.respond(embed=embed, components=menu)

        # Attach menu then listen
        try:
            await menu.attach(ctx.client, timeout=120) 
        except TimeoutError:
            pass