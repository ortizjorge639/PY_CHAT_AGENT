"""Interactive terminal chat — test the agent without Bot Framework / Emulator."""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(__file__))

from config.settings import Settings
from data.loader import DataLoader
from agent.kernel import AgentKernel

CONV_ID = "terminal-test"

async def main():
    settings = Settings()
    loader = DataLoader(settings)
    agent = AgentKernel(settings, loader)

    print("=" * 60)
    print("  Chat-Over-Data Agent  —  Terminal Test")
    print("  Type 'quit' to exit")
    print("=" * 60)
    print()

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input or user_input.lower() in ("quit", "exit"):
            break

        print("Bot: (thinking...)", end="\r")
        try:
            result = await agent.ask(CONV_ID, user_input)
            # Clear the "thinking" line
            print(" " * 40, end="\r")
            # Print data chunks directly (bypasses LLM)
            for chunk in result.get("data_chunks", []):
                print(chunk)
                print()
            # Print download links for generated files
            for f in result.get("files", []):
                print(f"📥 Download: {f['name']} -> {f['path']}")
                print()
            # Print LLM commentary
            print(f"Bot: {result['text']}")
        except Exception as e:
            print(f"Bot: [ERROR] {e}")
        print()

if __name__ == "__main__":
    asyncio.run(main())
