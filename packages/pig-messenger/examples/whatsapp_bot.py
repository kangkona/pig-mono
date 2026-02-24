"""WhatsApp bot example with webhook server."""

import os
from fastapi import FastAPI, Request
from pig_messenger import MessengerBot
from pig_messenger.adapters import WhatsAppAdapter
from pig_agent_core import Agent, tool
from pig_llm import LLM
import uvicorn


# Create agent
@tool(description="Get current time")
def get_time() -> str:
    from datetime import datetime
    return datetime.now().strftime("%H:%M:%S")


def create_whatsapp_bot():
    """Create WhatsApp bot with webhook."""
    
    # Get credentials
    phone_id = os.getenv("WHATSAPP_PHONE_ID")
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN")
    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "my_verify_token")
    
    if not phone_id or not access_token:
        print("❌ Missing WhatsApp credentials")
        print("Set: WHATSAPP_PHONE_ID and WHATSAPP_ACCESS_TOKEN")
        return None, None
    
    # Create agent
    agent = Agent(
        llm=LLM(provider="openai"),
        tools=[get_time],
        system_prompt="You are a helpful WhatsApp assistant."
    )
    
    # Create bot
    bot = MessengerBot(agent)
    
    # Add WhatsApp
    whatsapp = WhatsAppAdapter(
        phone_number_id=phone_id,
        access_token=access_token,
        verify_token=verify_token,
        webhook_url="https://your-server.com/webhook"
    )
    bot.add_platform(whatsapp)
    
    # Create FastAPI webhook server
    app = FastAPI()
    
    @app.get("/webhook")
    async def verify(request: Request):
        """Webhook verification."""
        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge")
        
        if mode == "subscribe" and token == verify_token:
            return int(challenge)
        
        return {"error": "Invalid verification token"}, 403
    
    @app.post("/webhook")
    async def webhook(request: Request):
        """Receive WhatsApp messages."""
        payload = await request.json()
        
        # Handle webhook
        whatsapp.handle_webhook(payload)
        
        return {"status": "ok"}
    
    return bot, app


def main():
    """Run WhatsApp bot with webhook server."""
    
    print("=" * 60)
    print("WhatsApp Bot with Webhook Server")
    print("=" * 60)
    print()
    
    bot, app = create_whatsapp_bot()
    
    if not bot:
        return
    
    print("✓ WhatsApp adapter configured")
    print()
    print("Webhook server starting on http://0.0.0.0:8000")
    print("Configure webhook URL in Meta Developer Portal:")
    print("  https://developers.facebook.com/apps")
    print()
    print("Webhook URL: https://your-server.com/webhook")
    print(f"Verify token: {os.getenv('WHATSAPP_VERIFY_TOKEN', 'my_verify_token')}")
    print()
    print("Press Ctrl+C to stop")
    print()
    
    # Start webhook server
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
