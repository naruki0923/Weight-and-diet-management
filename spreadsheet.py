import json
import gspread
from datetime import datetime, timedelta, timezone
from config import (
    GCP_SERVICE_ACCOUNT_JSON,
    SPREADSHEET_URL_OR_KEY,
    DAY_START_HOUR,
    PUSHUP_REPS_PER_SET,
    PUSHUP_SETS_PER_DAY,
    PUSHUP_DAYS_PER_WEEK,
)

# Vercelの実行環境はUTCなので、日付・時刻は必ずJSTで扱う。
# そうしないと朝9時までに食べたぶんが前日の記録として集計されてしまう。
JST = timezone(timedelta(hours=9))

def now() -> datetime:
    """日本時間の現在時刻"""
    return datetime.now(JST)

def logical_date(at: datetime = None):
    """記録上の「今日」の日付。DAY_START_HOUR より前はまだ前日として扱う。

    深夜1時に食べたぶんは前日の食事、というのが体感に合うため。
    筋トレのセット数もこの日付でリセットされる。
    """
    return ((at or now()) - timedelta(hours=DAY_START_HOUR)).date()

def today_str() -> str:
    """シートに書く日付文字列（区切りは DAY_START_HOUR）"""
    return logical_date().strftime("%Y/%m/%d")

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

def _row_logical_date(value):
    """シートの「日時」セルから記録上の日付を求める。読めなければ None"""
    text = str(value).strip()
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        # 日付だけの行は時刻0時とみなされるが、それは書いた時点で
        # すでに区切り済みの日付なのでそのまま使う
        if fmt == "%Y/%m/%d":
            return parsed.date()
        return logical_date(parsed)
    return None

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
    today = logical_date()

    totals = {"calories": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0, "count": 0}

    # このシートはヘッダー行を持たず1行目からデータ。
    # record_meal_data が [日時, メニュー名, カロリー, P, F, C] の順で書き込む前提で、
    # 日付が一致する行だけ拾う（ヘッダーを足しても日付として読めないので無視される）。
    # 前方一致ではなく日時を解釈するのは、深夜3時前の記録を前日ぶんに寄せるため。
    for row in sheet.get_all_values():
        if len(row) < 6 or _row_logical_date(row[0]) != today:
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
    today = logical_date()
    now_str = now().strftime("%Y/%m/%d %H:%M:%S")

    # このシートもヘッダーなしで [日時, 体重]。今日の行を後ろから探す
    for i, row in enumerate(sheet.get_all_values(), start=1):
        if row and _row_logical_date(row[0]) == today:
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

PUSHUP_SHEET_NAME = "腕立て記録シート"
PUSHUP_HEADER = ["日付", "セット数", "回数", "更新時刻"]

def _pushup_sheet():
    """腕立て記録シートを返す。なければヘッダーつきで作る"""
    book = get_sheet_client()
    try:
        return book.worksheet(PUSHUP_SHEET_NAME)
    except gspread.WorksheetNotFound:
        sheet = book.add_worksheet(title=PUSHUP_SHEET_NAME, rows=400, cols=len(PUSHUP_HEADER))
        sheet.append_row(PUSHUP_HEADER)
        return sheet

def _read_pushup_rows(sheet):
    """腕立て記録シートを {日付: (行番号, セット数)} で読む"""
    rows = {}
    for i, row in enumerate(sheet.get_all_values(), start=1):
        if len(row) < 2:
            continue
        try:
            date = datetime.strptime(str(row[0]).strip(), "%Y/%m/%d").date()
        except ValueError:
            continue  # ヘッダー行や空行
        rows[date] = (i, int(_to_float(row[1])))
    return rows

def _week_start(date):
    """その日が属する週（月曜はじまり）の月曜日"""
    return date - timedelta(days=date.weekday())

def _build_pushup_status(rows, today) -> dict:
    """セット数の記録から、今日と今週の達成状況をまとめる"""
    sets = rows.get(today, (None, 0))[1]
    week_start = _week_start(today)

    # 週5日の「達成した日」は、その日のノルマ（5セット）を満たした日だけ数える
    done_days = sorted(
        date for date, (_, count) in rows.items()
        if week_start <= date <= today and count >= PUSHUP_SETS_PER_DAY
    )

    return {
        "date": today.strftime("%Y/%m/%d"),
        "sets": sets,
        "target_sets": PUSHUP_SETS_PER_DAY,
        "reps": sets * PUSHUP_REPS_PER_SET,
        "target_reps": PUSHUP_SETS_PER_DAY * PUSHUP_REPS_PER_SET,
        "reps_per_set": PUSHUP_REPS_PER_SET,
        "done_today": sets >= PUSHUP_SETS_PER_DAY,
        "week_start": week_start.strftime("%Y/%m/%d"),
        "week_done_days": len(done_days),
        "week_target_days": PUSHUP_DAYS_PER_WEEK,
        # 今日を含めて週末（日曜）まであと何日あるか。ノルマが間に合うかの判断に使う
        "week_days_left": 7 - today.weekday(),
    }

def get_pushup_status() -> dict:
    """今日のセット数と今週の達成日数を返す（記録は増やさない）"""
    sheet = _pushup_sheet()
    return _build_pushup_status(_read_pushup_rows(sheet), logical_date())

def add_pushup_set(sets: int = 1) -> dict:
    """腕立てを1セット（指定があればその数だけ）記録して、最新の状況を返す"""
    sheet = _pushup_sheet()
    rows = _read_pushup_rows(sheet)
    today = logical_date()
    now_str = now().strftime("%Y/%m/%d %H:%M:%S")

    row_index, current = rows.get(today, (None, 0))
    updated = current + sets
    values = [[today.strftime("%Y/%m/%d"), updated, updated * PUSHUP_REPS_PER_SET, now_str]]

    if row_index is None:
        sheet.append_row(values[0])
        row_index = len(sheet.get_all_values())
    else:
        sheet.update(values=values, range_name=f"A{row_index}:D{row_index}")

    rows[today] = (row_index, updated)
    status = _build_pushup_status(rows, today)
    status["added_sets"] = sets
    return status