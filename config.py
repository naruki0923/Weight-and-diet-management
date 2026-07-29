import os
from dotenv import load_dotenv

# .envファイルがあれば読み込む
load_dotenv()

# Gemini API設定
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ショートカット等からAPIを叩くときの合言葉（X-API-Tokenヘッダーで送る）
API_TOKEN = os.getenv("API_TOKEN")

# Google スプレッドシート設定
GCP_SERVICE_ACCOUNT_JSON = os.getenv("GCP_SERVICE_ACCOUNT_JSON", "service_account.json")
SPREADSHEET_URL_OR_KEY = os.getenv("SPREADSHEET_URL_OR_KEY")