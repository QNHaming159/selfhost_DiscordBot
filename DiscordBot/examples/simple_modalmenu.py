from urllib import response
import hikari
import lightbulb
from lightbulb.components import Menu, MenuContext, Modal, ModalContext

loader = lightbulb.Loader()

class RR_Modal(Modal):
    def __init__(self) -> None:
        super().__init__()

        self.title_input = self.add_short_text_input(
            label="Embed Title",
            placeholder="Enter the title for the embed",
            required=True,
            max_length=100
        )
        
        self.description_input = self.add_paragraph_text_input(
            label="Description",
            placeholder="Enter the description for the embed",
            required=False,
            max_length=1000
        )
        
        self.color_input = self.add_short_text_input(
            label="Embed Color",
            placeholder="Enter a hex color code [#FFFFFF]",
            required=False,
            max_length=7
        )

        self.imageURL_input = self.add_short_text_input(
            label="Embed Image",
            placeholder="Enter the image URL for the embed",
            required=False,
            max_length=100
        )

    async def on_submit(self, ctx: ModalContext) -> None:
        try:
            self.title_value = ctx.value_for(self.title_input)
            self.description_value = ctx.value_for(self.description_input)
            self.color_value = ctx.value_for(self.color_input) or 0x00FF00
            self.imageURL_value = ctx.value_for(self.imageURL_input)

            await ctx.delete_response(await ctx.respond("Loading...", ephemeral=True)) # Have to send a repsonse, idk how to empty this but oh well.
        except Exception as e:
            await ctx.respond(f"An error occurred: {e}", ephemeral=True)


class RR_Menu(Menu):
    def __init__(self) -> None:
        super().__init__()

        self.button1_select = self.add_interactive_button(
            style=1,
            on_press=self.on_button1_select,
            label="Buttons"
        )

        self.button2_select = self.add_interactive_button(
            style=1,
            on_press=self.on_button2_select,
            label="Emojis"
        )

    async def on_button1_select(self, ctx: MenuContext) -> None:
        self.button_value = "Buttons"
        await ctx.respond(edit=True)
        ctx.stop_interacting()

    async def on_button2_select(self, ctx: MenuContext) -> None:
        self.button_value = "Emojis"
        await ctx.respond(edit=True)
        ctx.stop_interacting()

@loader.command
class Maincommand(
    lightbulb.SlashCommand,
    name="modalmenu", # Upper case sensitive.
    description="Give feedback using both Modal and Menu",
):    

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:

        # Check if the command is used in a guild
        if not ctx.guild_id:
            await ctx.respond("This command can only be used in a server!", ephemeral=True)
            return

        # Create the modal and Menu
        modal = RR_Modal()
        menu = RR_Menu()
        
        response_id = None
        # Attach then listen
        try:
            await ctx.respond_with_modal(
                title="Role Reaction Creation Form",
                custom_id="modalmenu",
                components = modal
            )
            await modal.attach(ctx.client, "modalmenu", timeout=120)

            response_id = await ctx.respond(components=menu,ephemeral=True)
            await menu.attach(ctx.client, timeout=120)
            await ctx.delete_response(response_id)

        except TimeoutError:
            pass

        # Get value from modal
        title_value = modal.title_value
        description_value = modal.description_value
        color_value = modal.color_value
        imageURL_value = modal.imageURL_value

        # Get value from menu
        type_value = menu.button_value

        testembed = hikari.Embed(
            title="✅ Role Selection Confirmed",
            description=f"**Title:** {title_value}\n**Description:** {description_value}\n**Color:** {color_value}\n**ImageURL:** {imageURL_value}\n**Type:** {type_value}",
            color=hikari.Color(0x00FF00)
        )

        await ctx.respond(embed=testembed, ephemeral=False)
