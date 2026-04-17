import hikari
import lightbulb
from lightbulb.components import Menu, MenuContext

loader = lightbulb.Loader()

class RoleChannelMenu(Menu):    
    def __init__(self) -> None:
        super().__init__()
        
        # Add a role select menu
        self.role_select = self.add_role_select(
            self.on_select,
            placeholder="Select a role",
            min_values=1,
            max_values=1
        )
    
    async def on_select(self, ctx: MenuContext) -> None:
        role_values = ctx.selected_values_for(self.role_select)
        
        role_mention = role_values[0].mention if role_values else "None"
        
        embed = hikari.Embed(
            title="✅ Selection Confirmed",
            description=f"**Role:** {role_mention}",
            color=hikari.Color(0x00FF00)
        )
        
        await ctx.respond(embed=embed)
        ctx.stop_interacting()
    
@loader.command
class MenuCommand(
    lightbulb.SlashCommand,
    name="menu1",
    description="Display an interactive menu with role selection",
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
                        "• **Role Select** - Choose a role from the server\n",
            color=hikari.Color(0x00AAFF)
        )
        
        # Send the menu with the embed
        await ctx.respond(embed=embed, components=menu)

        # Attach menu then listen
        try:
            await menu.attach(ctx.client, timeout=120) 
        except TimeoutError:
            pass