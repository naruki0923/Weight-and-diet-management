import spreadsheet
import ai

def analyze_and_record(image_bytes: bytes) -> dict:
    """食事画像を解析してシートに記録し、解析結果を返す"""
    nutrition = ai.analyze_meal_image(image_bytes)

    meal = {
        "meal_name": nutrition.get("meal_name", "不明な食事"),
        "calories": nutrition.get("calories", 0),
        "protein": nutrition.get("protein", 0),
        "fat": nutrition.get("fat", 0),
        "carbs": nutrition.get("carbs", 0),
        "data_source": nutrition.get("data_source", "画像からの概算"),
        "memo": nutrition.get("memo", "特になし"),
    }

    spreadsheet.record_meal_data(
        meal["meal_name"], meal["calories"], meal["protein"], meal["fat"], meal["carbs"]
    )

    return meal

def get_daily_status() -> dict:
    """今日の合計・目標・残りをまとめて返す"""
    totals = spreadsheet.get_today_meal_totals()
    target = spreadsheet.get_target_calories()

    return {
        "totals": totals,
        "target": target,
        "remaining": target - totals["calories"] if target > 0 else None,
    }

def build_daily_summary() -> str:
    """今日の合計カロリーと、目標までの残りをまとめた文面を作る"""
    status = get_daily_status()
    totals = status["totals"]
    target = status["target"]

    lines = [
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

def build_meal_result(meal: dict) -> str:
    """1食ぶんの解析結果＋今日の合計を、通知1枚に収まる文面にする"""
    return (
        f"🍽️ {meal['meal_name']}\n"
        f"⚡ {meal['calories']} kcal（P {meal['protein']} / F {meal['fat']} / C {meal['carbs']}）\n\n"
        f"{build_daily_summary()}"
    )
