import json
import gspread
from datetime import datetime, timedelta, timezone
from config import GCP_SERVICE_ACCOUNT_JSON, SPREADSHEET_URL_OR_KEY

# Vercelの実行環境はUTCなので、日付・時刻は必ずJSTで扱う。
# そうしないと朝9時までに食べたぶんが前日の記録として集計されてしまう。
JST = timezone(timedelta(hours=9))

def now() -> datetime:
    """日本時間の現在時刻"""
    return datetime.now(JST)

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

def get_settings():
    """設定シートを A列=項目名 -> B列=設定値 の辞書として読む"""
    sheet = get_sheet_client().worksheet("設定シート")

    # シートによってヘッダーの有無がバラバラなので get_all_records は使わず、
    # A列=項目名 / B列=設定値 という位置で読む。
    settings = {}
    for row in sheet.get_all_values():
        if len(row) < 2:
            continue
        key = str(row[0]).strip()
        if not key or key == "項目名":
            continue
        settings[key] = row[1]

    return settings

def get_target_nutrition():
    """設定シートから目標PFCとカロリーを取得する"""
    return get_settings()

def set_setting(key: str, value, unit: str = ""):
    """設定シートの1項目を更新する（項目名の完全一致。行がなければ追加）"""
    sheet = get_sheet_client().worksheet("設定シート")

    for i, row in enumerate(sheet.get_all_values()):
        if row and str(row[0]).strip() == key:
            sheet.update_cell(i + 1, 2, value)
            if unit:
                sheet.update_cell(i + 1, 3, unit)
            return

    sheet.append_row([key, value, unit])

def record_meal_data(meal_name: str, calories: int, protein: int, fat: int, carbs: int):
    """食事記録シートにデータを追加する"""
    sheet = get_sheet_client().worksheet("食事記録シート")
    now_str = now().strftime("%Y/%m/%d %H:%M:%S")
    
    row_data = [now_str, meal_name, calories, protein, fat, carbs]
    sheet.append_row(row_data)

def get_today_meal_totals():
    """食事記録シートから今日ぶんのカロリーとPFCを合計する"""
    sheet = get_sheet_client().worksheet("食事記録シート")
    today_str = now().strftime("%Y/%m/%d")

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
    settings = get_settings()

    # 「カロリー調整」も部分一致してしまうので、完全一致を先に見る
    for key in (TARGET_CALORIE_KEY, "カロリー"):
        if key in settings:
            return _to_float(settings[key])

    return 0.0

def set_target_calories(calories: int):
    """設定シートの目標カロリーを更新する（行がなければ追加）"""
    sheet = get_sheet_client().worksheet("設定シート")

    # 「カロリー調整」を書き換えないよう、こちらも完全一致で探す
    for i, row in enumerate(sheet.get_all_values()):
        if row and str(row[0]).strip() in (TARGET_CALORIE_KEY, "カロリー"):
            sheet.update_cell(i + 1, 2, calories)
            return

    sheet.append_row([TARGET_CALORIE_KEY, calories, "kcal"])

def record_weight(weight: float):
    """体重記録シートに記録する。同じ日の行があれば上書きして1日1行に保つ。

    オートメーションで日に何度も送られてくる前提なので、追記し続けると
    同じ値の行が溜まってグラフが見にくくなる。その日の最新値だけ残す。
    """
    sheet = get_sheet_client().worksheet("体重記録シート")
    today = now().strftime("%Y/%m/%d")
    now_str = now().strftime("%Y/%m/%d %H:%M:%S")

    # このシートもヘッダーなしで [日時, 体重]。今日の行を後ろから探す
    for i, row in enumerate(sheet.get_all_values(), start=1):
        if row and str(row[0]).startswith(today):
            sheet.update(values=[[now_str, weight]], range_name=f"A{i}:B{i}")
            return

    sheet.append_row([now_str, weight])

def get_latest_weight() -> float:
    """体重記録シートの最新の体重を返す（1件もなければ0）"""
    sheet = get_sheet_client().worksheet("体重記録シート")

    # このシートも [日時, 体重] で1行目からデータ。後ろから見て最初に数値が入っている行を採用する。
    for row in reversed(sheet.get_all_values()):
        if len(row) < 2:
            continue
        weight = _to_float(row[1])
        if weight > 0:
            return weight

    return 0.0

# TDEEの計算に使う設定シートの項目名
BODY_PROFILE_KEYS = {
    "sex": "性別",
    "age": "年齢",
    "height": "身長",
    "weight": "体重",
    "activity_level": "活動レベル",
    "goal": "目標区分",
    "adjustment": "カロリー調整",
}

def get_body_profile() -> dict:
    """TDEE計算に使う身体データを設定シート＋体重記録シートから集める"""
    settings = get_settings()
    profile = {key: settings.get(name, "") for key, name in BODY_PROFILE_KEYS.items()}

    # 体重は記録シートの最新値を優先し、記録がなければ設定シートの「体重」を使う
    latest_weight = get_latest_weight()
    if latest_weight > 0:
        profile["weight"] = latest_weight

    return profile

def record_training():
    """筋トレ記録シートに完了フラグを追加する"""
    sheet = get_sheet_client().worksheet("筋トレ記録シート")
    date_str = now().strftime("%Y/%m/%d")
    
    row_data = [date_str, "完了"]
    sheet.append_row(row_data)

def get_today_training_status():
    """今日の筋トレ状況を取得（なければ行を作成）"""
    sheet = get_sheet_client().worksheet("筋トレ記録シート")
    today_str = now().strftime("%Y/%m/%d")
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
    check_date = now().date()
    
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