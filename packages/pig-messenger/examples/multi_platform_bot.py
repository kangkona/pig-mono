"""Multi-platform bot example."""

import os
from pig_messenger import MessengerBot
from pig_messenger.adapters import SlackAdapter, DiscordAdapter, TelegramAdapter
from pig_agent_core import Agent, tool
from pig_llm import LLM


# Define custom tools
@tool(description="Get current time")
def get_time() -> str:
    """Get current time."""
    from datetime import datetime
    return datetime.now().strftime("%H:%M:%S")


@tool(description="Calculate expression")
def calculate(expression: str) -> str:
    """Calculate mathematical expression."""
    try:
        result = eval(expression, {"__builtins__": {}}, {})
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error: {e}"


def main():
    """Run multi-platform bot."""
    
    print("=" * 60)
    print("py-messenger Multi-Platform Bot")
    print("=" * 60)
    print()
    
    # Create agent
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not set")
        return
    
    agent = Agent(
        name="MultiBot",
        llm=LLM(provider="openai", api_key=api_key),
        tools=[get_time, calculate],
        system_prompt="""You are a helpful assistant available on multiple platforms.
        
You have access to:
- get_time() - Get current time
- calculate() - Calculate math expressions

Be helpful and friendly!""",
    )
    
    # Create bot
    bot = MessengerBot(agent, enable_sessions=True)
    
    # Add platforms
    platforms_added = 0
    
    # Slack
    slack_app = os.getenv("SLACK_APP_TOKEN")
    slack_bot = os.getenv("SLACK_BOT_TOKEN")
    if slack_app and slack_bot:
        bot.add_platform(SlackAdapter(
            app_token=slack_app,
            bot_token=slack_bot
        ))
        platforms_added += 1
    else:
        print("⚠️  Slack tokens not set (SLACK_APP_TOKEN, SLACK_BOT_TOKEN)")
    
    # Discord
    discord_token = os.getenv("DISCORD_BOT_TOKEN")
    if discord_token:
        bot.add_platform(DiscordAdapter(bot_token=discord_token))
        platforms_added += 1
    else:
        print("⚠️  Discord token not set (DISCORD_BOT_TOKEN)")
    
    # Telegram
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if telegram_token:
        bot.add_platform(TelegramAdapter(bot_token=telegram_token))
        platforms_added += 1
    else:
        print("⚠️  Telegram token not set (TELEGRAM_BOT_TOKEN)")
    
    if platforms_added == 0:
        print("\n❌ No platforms configured!")
        print("\nSet at least one:")
        print("  export SLACK_APP_TOKEN=xapp-...")
        print("  export SLACK_BOT_TOKEN=xoxb-...")
        print("  export DISCORD_BOT_TOKEN=...")
        print("  export TELEGRAM_BOT_TOKEN=...")
        return
    
    print(f"\n✓ Configured {platforms_added} platform(s)")
    print("\nStarting bot...")
    print("Press Ctrl+C to stop\n")
    
    # Start!
    bot.start()


if __name__ == "__main__":
    main()
