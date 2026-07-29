import json
import gspread
from datetime import datetime, timedelta
from config import GCP_SERVICE_ACCOUNT_JSON, SPREADSHEET_URL_OR_KEY

_spreadsheet = None

def _authorize():
    """認証情報を受け取る。Vercelなど書き込み不可な環境ではJSON文字列を直接渡せる"""
    raw = (GCP_SERVICE_ACCOUNT_JSON or "").strip()
    if raw.startswith("{"):
        return gspread.service_account_from_dict(json.loads(raw))
    return gspread.service_account(filename=raw)

def get_sheet_client():
    """スプレッドシートのクライアントを返す（認証は初回だけ。プロセス内で使い回す）"""
    global _spreadsheet
    if _spreadsheet is None:
        _spreadsheet = _authorize().open_by_key(SPREADSHEET_URL_OR_KEY)
    return _spreadsheet

TARGET_CALORIE_KEY = "目標カロリー"

def _to_float(value) -> float:
    """シートの値を数値に変換する（空欄や文字列は0扱い）"""
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0

def get_target_nutrition():
    """設定シートから目標PFCとカロリーを取得する"""
    sheet = get_sheet_client().worksheet("設定シート")

    # B1（設定値）のヘッダーが空なので get_all_records だと値を拾えない。
    # A列=項目名 / B列=設定値 という位置で読む。
    targets = {}
    for row in sheet.get_all_values():
        if len(row) < 2:
            continue
        key = str(row[0]).strip()
        if not key or key == "項目名":
            continue
        targets[key] = row[1]

    return targets

def record_meal_data(meal_name: str, calories: int, protein: int, fat: int, carbs: int):
    """食事記録シートにデータを追加する"""
    sheet = get_sheet_client().worksheet("食事記録シート")
    now_str = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    
    row_data = [now_str, meal_name, calories, protein, fat, carbs]
    sheet.append_row(row_data)

def get_today_meal_totals():
    """食事記録シートから今日ぶんのカロリーとPFCを合計する"""
    sheet = get_sheet_client().worksheet("食事記録シート")
    today_str = datetime.now().strftime("%Y/%m/%d")

    totals = {"calories": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0, "count": 0}

    # このシートはヘッダー行を持たず1行目からデータ。
    # record_meal_data が [日時, メニュー名, カロリー, P, F, C] の順で書き込む前提で、
    # 日付が一致する行だけ拾う（ヘッダーを足しても日付と一致しないので無視される）
    for row in sheet.get_all_values():
        if len(row) < 6 or not str(row[0]).startswith(today_str):
            continue
        totals["calories"] += _to_float(row[2])
        totals["protein"] += _to_float(row[3])
        totals["fat"] += _to_float(row[4])
        totals["carbs"] += _to_float(row[5])
        totals["count"] += 1

    return totals

def get_target_calories() -> float:
    """設定シートから目標カロリーを取得する（未設定なら0）"""
    for key, val in get_target_nutrition().items():
        if "カロリー" in str(key):
            return _to_float(val)
    return 0.0

def set_target_calories(calories: int):
    """設定シートの目標カロリーを更新する（行がなければ追加）"""
    sheet = get_sheet_client().worksheet("設定シート")

    for i, row in enumerate(sheet.get_all_values()):
        if row and "カロリー" in str(row[0]):
            sheet.update_cell(i + 1, 2, calories)
            return

    sheet.append_row([TARGET_CALORIE_KEY, calories])

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