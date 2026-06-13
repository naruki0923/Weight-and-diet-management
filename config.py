import os
from dotenv import load_dotenv

# .envファイルがあれば読み込む
load_dotenv()

# LINE API設定
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

# Gemini API設定
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Google スプレッドシート設定
GCP_SERVICE_ACCOUNT_JSON = os.getenv("GCP_SERVICE_ACCOUNT_JSON", "service_account.json")
SPREADSHEET_URL_OR_KEY = os.getenv("SPREADSHEET_URL_OR_KEY")