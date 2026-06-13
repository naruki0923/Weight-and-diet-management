import gspread
from datetime import datetime
from config import GCP_SERVICE_ACCOUNT_JSON, SPREADSHEET_URL_OR_KEY

def get_sheet_client():
    """スプレッドシートのクライアントを初期化して返す"""
    client = gspread.service_account(filename=GCP_SERVICE_ACCOUNT_JSON)
    spreadsheet = client.open_by_key(SPREADSHEET_URL_OR_KEY)
    return spreadsheet

def get_target_nutrition():
    """設定シートから目標PFCとカロリーを取得する"""
    sheet = get_sheet_client().worksheet("設定シート")
    # A列が項目名、B列が値という前提で取得
    data = sheet.get_all_records()
    targets = {}
    for row in data:
        key = row.get("項目名")
        val = row.get("設定値")
        if key:
            targets[key] = val
    return targets

def record_meal_data(meal_name: str, calories: int, protein: int, fat: int, carbs: int):
    """食事記録シートにデータを追加する"""
    sheet = get_sheet_client().worksheet("食事記録シート")
    now_str = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    
    row_data = [now_str, meal_name, calories, protein, fat, carbs]
    sheet.append_row(row_data)

def record_weight(weight: float):
    """体重記録シートにデータを追加する"""
    sheet = get_sheet_client().worksheet("体重記録シート")
    now_str = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    
    row_data = [now_str, weight]
    sheet.append_row(row_data)

def record_training():
    """筋トレ記録シートに完了フラグを追加する"""
    sheet = get_sheet_client().worksheet("筋トレ記録シート")
    date_str = datetime.now().strftime("%Y/%m/%d")
    
    row_data = [date_str, "完了"]
    sheet.append_row(row_data)