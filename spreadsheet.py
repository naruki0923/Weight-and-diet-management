import gspread
from datetime import datetime, timedelta
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

def get_today_training_status():
    """今日の筋トレ状況を取得（なければ行を作成）"""
    sheet = get_sheet_client().worksheet("筋トレ記録シート")
    today_str = datetime.now().strftime("%Y/%m/%d")
    records = sheet.get_all_records()
    
    today_row_index = None
    today_data = None
    for i, row in enumerate(records):
        if str(row.get("日付", "")) == today_str:
            today_row_index = i + 2 # ヘッダーと0始まりのズレを調整
            today_data = row
            break
            
    if today_row_index is None:
        sheet.append_row([today_str, "", "", ""])
        today_row_index = len(records) + 2
        today_data = {"日付": today_str, "プランク": "", "腹筋": "", "腕立て伏せ": ""}
        
    return today_data, today_row_index

def update_training_task(task_name: str):
    """指定された種目を「済」にする"""
    sheet = get_sheet_client().worksheet("筋トレ記録シート")
    today_data, row_index = get_today_training_status()
    
    col_map = {"プランク": 2, "腹筋": 3, "腕立て伏せ": 4}
    if task_name in col_map:
        sheet.update_cell(row_index, col_map[task_name], "済")

def get_training_streak():
    """何日連続で3種目すべて達成しているかを計算"""
    sheet = get_sheet_client().worksheet("筋トレ記録シート")
    records = sheet.get_all_records()
    records.sort(key=lambda x: str(x.get("日付", "")), reverse=True)
    
    streak = 0
    check_date = datetime.now().date()
    
    # 今日の状況を確認
    today_record = next((r for r in records if r.get("日付") == check_date.strftime("%Y/%m/%d")), None)
    if today_record and today_record.get("プランク") == "済" and today_record.get("腹筋") == "済" and today_record.get("腕立て伏せ") == "済":
        streak += 1
        check_date -= timedelta(days=1)
    else:
        check_date -= timedelta(days=1)
        
    # 昨日から遡って連続達成をカウント
    for _ in range(365):
        record = next((r for r in records if r.get("日付") == check_date.strftime("%Y/%m/%d")), None)
        if record and record.get("プランク") == "済" and record.get("腹筋") == "済" and record.get("腕立て伏せ") == "済":
            streak += 1
            check_date -= timedelta(days=1)
        else:
            break
            
    return streak