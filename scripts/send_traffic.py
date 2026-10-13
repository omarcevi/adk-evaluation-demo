"""Sends demo traffic to the DEPLOYED ShopHelper agent, so Cloud Trace has data.

Usage: uv run python scripts/send_traffic.py   (or: make traffic)
"""

import asyncio
import os

import vertexai
from dotenv import load_dotenv

load_dotenv("shop_helper/.env")
PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]
REGION = os.environ["AGENT_RUNTIME_REGION"]
AGENT_ENGINE_ID = os.environ["AGENT_ENGINE_ID"]
USER_ID = "demo_user"

# Each inner list is one conversation (one session).
CONVERSATIONS = [
    ["Hi! What's the status of order ORD-1001?", "And when will ORD-1002 arrive?"],
    ["When will my order ORD-1007 be delivered?"],  # slow get_shipping_eta span
    ["I'd like to return ORD-1006, the yoga mat is the wrong color."],
    ["Can I return order ORD-1004? The jacket doesn't fit.", "Ok. What about ORD-1005?"],
    ["Where is my order #1001?"],  # bug: "#1001" format -> tool error
    ["Merhaba, ORD-1003 siparişim ne zaman gelir?"],  # Turkish, slow ETA span
    ["Hello, I want to know the status of order 1008."],  # bug: "1008" format
    ["Hi, can you help me?", "Is ORD-1003 shipped yet?", "When will it arrive?"],
    ["Hey, has #1005 been delivered?"],  # bug: "#1005" format
    ["What did I buy in order ORD-1008?"],
    ["Do you sell pizza?"],
]


async def main() -> None:
    client = vertexai.Client(project=PROJECT, location=REGION)
    name = f"projects/{PROJECT}/locations/{REGION}/reasoningEngines/{AGENT_ENGINE_ID}"
    agent = client.agent_engines.get(name=name)

    for messages in CONVERSATIONS:
        session = await agent.async_create_session(user_id=USER_ID)
        print(f"\n=== session {session['id']}")
        for message in messages:
            print(f"user : {message}")
            async for event in agent.async_stream_query(
                user_id=USER_ID, session_id=session["id"], message=message
            ):
                if "error_message" in event:
                    print(f"error: {event['error_code']}")
                for part in event.get("content", {}).get("parts", []):
                    if "function_call" in part:
                        call = part["function_call"]
                        print(f"  tool: {call['name']}({call['args']})")
                    elif part.get("text"):
                        print(f"agent: {part['text'].strip()}")


if __name__ == "__main__":
    asyncio.run(main())
