import os
import sys
import uvicorn
from app.config import get_gemini_api_key, set_gemini_api_key, HOST, PORT

def setup_environment():
    current_key = get_gemini_api_key()
    if not current_key and sys.stdin.isatty():
        print("=" * 50)
        print("CleanMail Setup")
        print("=" * 50)
        print("Optional: Enter your Gemini API key for AI reviews.")
        print("Press Enter to skip and use basic offline checks.")
        try:
            user_input = input("Gemini API Key: ").strip()
            if user_input:
                set_gemini_api_key(user_input)
                os.environ["GEMINI_API_KEY"] = user_input
                print("Gemini API key saved successfully.")
            else:
                print("Skipped. Running with offline rules.")
        except (KeyboardInterrupt, EOFError):
            print("\nSetup skipped.")
        print("=" * 50)
    elif current_key:
        os.environ["GEMINI_API_KEY"] = current_key

if __name__ == "__main__":
    setup_environment()
    print(f"Starting CleanMail on http://{HOST}:{PORT} ...")
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
