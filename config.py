import os
from dotenv import load_dotenv

# .envファイルがあれば読み込む
load_dotenv()

# Gemini API設定
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ショートカット等からAPIを叩くときの合言葉（X-API-Tokenヘッダーで送る）
API_TOKEN = os.getenv("API_TOKEN")

# 1日の区切り（この時刻を過ぎたら新しい1日）。深夜の食事を前日ぶんに入れたいので0時ではない。
# 食事・体重・筋トレの「今日」はすべてこの時刻を基準にそろえる。
DAY_START_HOUR = 3

# 腕立て伏せのノルマ。ショートカットを1回叩いたら1セット。
PUSHUP_REPS_PER_SET = 20
PUSHUP_SETS_PER_DAY = 5
PUSHUP_DAYS_PER_WEEK = 5

# Google スプレッドシート設定
GCP_SERVICE_ACCOUNT_JSON = os.getenv("GCP_SERVICE_ACCOUNT_JSON", "service_account.json")
SPREADSHEET_URL_OR_KEY = os.getenv("SPREADSHEET_URL_OR_KEY")