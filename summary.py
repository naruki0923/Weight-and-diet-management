import spreadsheet
import tdee
import ai

def analyze_and_record(image_bytes: bytes, note: str = "") -> dict:
    """食事画像を解析してシートに記録し、解析結果を返す。

    note は「大盛り」「半分残した」など、写真から読み取れない補足。
    """
    nutrition = ai.analyze_meal_image(image_bytes, note)

    meal = {
        "meal_name": nutrition.get("meal_name", "不明な食事"),
        "calories": nutrition.get("calories", 0),
        "protein": nutrition.get("protein", 0),
        "fat": nutrition.get("fat", 0),
        "carbs": nutrition.get("carbs", 0),
        "data_source": nutrition.get("data_source", "画像からの概算"),
        "memo": nutrition.get("memo", "特になし"),
        # 1品ずつの内訳。通知には出さないがレスポンスには含めておく
        "items": nutrition.get("items", []),
    }

    spreadsheet.record_meal_data(
        meal["meal_name"], meal["calories"], meal["protein"], meal["fat"], meal["carbs"]
    )

    return meal

def get_daily_status() -> dict:
    """今日の合計・目標・残りをまとめて返す"""
    totals = spreadsheet.get_today_meal_totals()
    target = spreadsheet.get_target_calories()

    remaining = target - totals["calories"] if target > 0 else None

    return {
        "totals": totals,
        "target": target,
        "remaining": remaining,
        "headline": build_headline(remaining),
    }

def build_headline(remaining) -> str:
    """一番知りたい数字だけの1行。通知のタイトルにも使える短さにする"""
    if remaining is None:
        return "目標カロリー未設定"
    if remaining >= 0:
        return f"あと{remaining:.0f}kcal"
    return f"{abs(remaining):.0f}kcalオーバー"

def build_daily_summary() -> str:
    """今日の合計カロリーと、目標までの残りをまとめた文面を作る"""
    status = get_daily_status()
    totals = status["totals"]
    target = status["target"]

    # 通知はバナーで下が切れることがあるので、結論を最初に置く
    lines = [
        status["headline"],
        "",
        f"📊 今日の合計（{totals['count']}食）",
        f"⚡ カロリー: {totals['calories']:.0f} kcal",
        f"💪 P {totals['protein']:.0f}g / 💧 F {totals['fat']:.0f}g / 🍚 C {totals['carbs']:.0f}g",
    ]

    if target > 0:
        remaining = status["remaining"]
        if remaining >= 0:
            lines.append(f"\n🎯 目標 {target:.0f} kcal → あと {remaining:.0f} kcal")
        else:
            lines.append(f"\n🎯 目標 {target:.0f} kcal → {abs(remaining):.0f} kcal オーバー⚠️")
    else:
        lines.append("\n🎯 目標カロリー未設定")

    return "\n".join(lines)

def get_tdee_status(weight: float = None) -> dict:
    """身体データからBMR/TDEE/推奨摂取カロリーを計算し、現在の目標も添えて返す。

    weight を渡すとシートの記録より優先する（記録直後に読み直さずに済むように）。
    """
    profile = spreadsheet.get_body_profile()
    if weight:
        profile["weight"] = weight

    result = tdee.calculate(profile)
    result["current_target"] = spreadsheet.get_target_calories()
    return result

def build_tdee_summary() -> str:
    """TDEEの計算結果を通知用の文面にする。データ不足なら設定方法を案内する"""
    try:
        status = get_tdee_status()
    except tdee.MissingProfileError as e:
        lines = ["⚠️ TDEEの計算に必要なデータが足りません。", "",
                 "スプレッドシートの「設定シート」に次の項目を追加してください:"]
        for name in e.missing:
            lines.append(f"・{name}")
        lines.append("\n※体重はショートカットから送れば自動で記録されます")
        return "\n".join(lines)

    sign = "+" if status["adjustment"] >= 0 else "−"
    lines = [
        "🔥 TDEE（1日の総消費カロリー）",
        f"⚡ {status['tdee']} kcal",
        "",
        f"📐 内訳: 基礎代謝 {status['bmr']} kcal × {status['activity_factor']}",
        f"🏃 活動レベル{status['activity_level']}: {status['activity_label']}",
        f"📊 {status['sex']} / {status['age']:.0f}歳 / {status['height']:.0f}cm / {status['weight']:.1f}kg",
        "",
        f"🎯 目標「{status['goal']}」→ 推奨 {status['recommended_calories']:.0f} kcal"
        f"（TDEE {sign}{abs(status['adjustment']):.0f}）",
    ]

    if status["current_target"] > 0:
        lines.append(f"📝 現在の設定は {status['current_target']:.0f} kcal")

    return "\n".join(lines)

def apply_tdee_as_target(weight: float = None) -> dict:
    """推奨摂取カロリーを目標カロリーとして設定シートに書き込む"""
    status = get_tdee_status(weight)
    spreadsheet.set_target_calories(int(status["recommended_calories"]))
    status["current_target"] = status["recommended_calories"]
    return status

def record_weight_and_update(weight: float) -> dict:
    """体重を記録し、その体重でTDEEを計算し直して目標カロリーまで更新する。

    体重は測るたびに送られてくる前提なので、記録のたびに自動で再計算する。
    年齢・身長がまだ設定されていない場合は記録だけして計算はスキップする。
    """
    spreadsheet.record_weight(weight)

    result = {"weight": weight, "recalculated": False}
    try:
        status = apply_tdee_as_target(weight)
    except tdee.MissingProfileError as e:
        result["message"] = (
            f"体重 {weight}kg を記録しました！順調ですね💪\n\n"
            f"⚠️ {'・'.join(e.missing)}が未設定のため、TDEEは計算できませんでした。\n"
            f"「年齢 20」「身長 168」のように送ると設定できます"
        )
        result["missing"] = e.missing
        return result

    result["recalculated"] = True
    result["status"] = status
    result["message"] = (
        f"体重 {weight}kg を記録しました！順調ですね💪\n\n"
        f"🔄 この体重でカロリーを再計算しました\n"
        f"🔥 TDEE: {status['tdee']} kcal\n"
        f"🎯 目標カロリー: {status['recommended_calories']:.0f} kcal（目標「{status['goal']}」）"
    )
    return result

def build_pushup_headline(status: dict) -> str:
    """通知のタイトルにする1行。バナーで切れても分かるよう結論だけ"""
    if status["done_today"]:
        return f"今日のノルマ達成🎉 {status['sets']}/{status['target_sets']}セット"
    return f"腕立て {status['sets']}/{status['target_sets']}セット"

def build_pushup_summary(status: dict) -> str:
    """腕立ての進捗を通知用の文面にする"""
    remaining_sets = max(status["target_sets"] - status["sets"], 0)
    week_remaining = max(status["week_target_days"] - status["week_done_days"], 0)

    lines = [
        build_pushup_headline(status),
        "",
        f"💪 今日 {status['reps']}/{status['target_reps']}回"
        f"（{status['reps_per_set']}回 × {status['target_sets']}セット）",
    ]

    if remaining_sets > 0:
        lines.append(f"➡️ あと{remaining_sets}セット（{remaining_sets * status['reps_per_set']}回）")

    lines.append("")
    lines.append(f"📅 今週 {status['week_done_days']}/{status['week_target_days']}日")

    if week_remaining == 0:
        lines.append("🏆 今週のノルマ達成！")
    elif status["week_days_left"] < week_remaining:
        # 残り日数より必要な日数が多い＝もう週5には届かない
        lines.append(f"⚠️ 残り{status['week_days_left']}日なので今週の5日は届きません")
    else:
        lines.append(f"➡️ 残り{status['week_days_left']}日であと{week_remaining}日")

    return "\n".join(lines)

def add_pushup_set(sets: int = 1) -> dict:
    """1セット記録して、通知用の文面つきで状況を返す"""
    status = spreadsheet.add_pushup_set(sets)
    return {"message": build_pushup_summary(status), **status}

def get_pushup_status() -> dict:
    """今の進捗を通知用の文面つきで返す"""
    status = spreadsheet.get_pushup_status()
    return {"message": build_pushup_summary(status), **status}

def build_meal_result(meal: dict) -> str:
    """1食ぶんの解析結果＋今日の合計を、通知1枚に収まる文面にする"""
    return (
        f"🍽️ {meal['meal_name']}\n"
        f"⚡ {meal['calories']} kcal（P {meal['protein']} / F {meal['fat']} / C {meal['carbs']}）\n\n"
        f"{build_daily_summary()}"
    )
