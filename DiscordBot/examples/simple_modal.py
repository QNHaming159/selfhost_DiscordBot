import hikari
import lightbulb
from lightbulb.components import Modal, ModalContext

loader = lightbulb.Loader()

class FeedbackModal(Modal):
    """Modal for collecting user feedback"""
    
    def __init__(self) -> None:
        super().__init__()
        self.name_input = self.add_short_text_input(
            label="Your Name",
            placeholder="Enter your name!",
            required=False,
            max_length=100
        )
        
        self.rating_input = self.add_short_text_input(
            label="Rating (1-5)",
            placeholder="Enter a number between 1 and 5",
            required=False,
            max_length=1
        )
        
        self.feedback_input = self.add_paragraph_text_input(
            label="Your Feedback",
            placeholder="Share your thoughts...",
            required=False,
            max_length=1000
        )
    
    async def on_submit(self, ctx: ModalContext) -> None:
        try:
            name_value = ctx.value_for(self.name_input) or "Anonymous"
            rating_value = ctx.value_for(self.rating_input) or "N/A"
            feedback_value = ctx.value_for(self.feedback_input) or "No feedback provided"
        
            embed = hikari.Embed(
                title="📝 New Feedback Submitted!",
                description=f"**From:** {name_value}\n**Rating:** {rating_value}/5",
                color=hikari.Color(0x00FF00)
            )
            embed.add_field("Feedback", feedback_value, inline=False)
            embed.set_footer(text=f"User ID: {ctx.user.id}")
        
            await ctx.respond(embed=embed)
        except Exception as e:
            await ctx.respond(f"An error occurred: {e}", flags=hikari.MessageFlag.EPHEMERAL)

@loader.command
class FeedbackCommand(
    lightbulb.SlashCommand,
    name="modal",
    description="Give feedback using a modal",
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        
        # Create the modal
        modal = FeedbackModal()
        
        await ctx.respond_with_modal(
            title="Feedback Form",
            custom_id="feedback_modal",
            components=modal
        )
        
        # Attach modal then listen
        try:
            await modal.attach(ctx.client, "feedback_modal", timeout=120)
        except TimeoutError:
            pass