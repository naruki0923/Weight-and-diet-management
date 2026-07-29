"""身体データからBMR（基礎代謝）とTDEE（1日の総消費カロリー）を計算する。

シートやWeb層には依存しない純粋な計算だけを置く。
計算式は Harris-Benedict 改訂版（1984年版）。
"""

# 活動レベル: 番号 -> (表示名, 係数)
ACTIVITY_LEVELS = {
    1: ("ほぼ運動しない（デスクワーク中心）", 1.2),
    2: ("軽い運動（週1〜3日）", 1.375),
    3: ("中程度の運動（週3〜5日）", 1.55),
    4: ("激しい運動（週6〜7日）", 1.725),
    5: ("非常に激しい運動（毎日＋肉体労働）", 1.9),
}

DEFAULT_ACTIVITY_LEVEL = 1

# 目標区分 -> TDEEに足し引きするカロリー（「カロリー調整」を設定すればそちらが優先）
GOAL_ADJUSTMENTS = {
    "増量": 300,
    "維持": 0,
    "減量": -300,
}

DEFAULT_GOAL = "維持"


class MissingProfileError(Exception):
    """TDEEの計算に必要な項目が足りないときに投げる"""

    def __init__(self, missing):
        self.missing = missing
        super().__init__("身体データが足りません: " + "、".join(missing))


def normalize_sex(value) -> str:
    """「女」「女性」「female」などを "女性" に、それ以外を "男性" に揃える"""
    text = str(value).strip().lower()
    if text.startswith(("女", "f", "w")):
        return "女性"
    return "男性"


def normalize_activity_level(value) -> int:
    """活動レベルを1〜5の番号に揃える。番号でも表示名の一部でも受け付ける"""
    text = str(value).strip()

    try:
        level = int(float(text))
        if level in ACTIVITY_LEVELS:
            return level
    except (TypeError, ValueError):
        pass

    for level, (label, _) in ACTIVITY_LEVELS.items():
        # 「ほぼ運動しない」「激しい運動」など、表示名の頭の部分でも当てられるようにする
        if text and (text in label or label.split("（")[0] in text):
            return level

    return DEFAULT_ACTIVITY_LEVEL


def normalize_goal(value) -> str:
    """目標区分を 増量 / 維持 / 減量 のいずれかに揃える"""
    text = str(value).strip()
    for goal in GOAL_ADJUSTMENTS:
        if goal in text:
            return goal
    return DEFAULT_GOAL


def activity_label(level: int) -> str:
    return ACTIVITY_LEVELS[level][0]


def activity_factor(level: int) -> float:
    return ACTIVITY_LEVELS[level][1]


def calc_bmr(sex, age: float, height_cm: float, weight_kg: float) -> float:
    """基礎代謝量（Harris-Benedict改訂版）"""
    if normalize_sex(sex) == "女性":
        return 447.593 + 9.247 * weight_kg + 3.098 * height_cm - 4.330 * age
    return 88.362 + 13.397 * weight_kg + 4.799 * height_cm - 5.677 * age


def calc_tdee(bmr: float, activity_level) -> float:
    """BMRに活動係数を掛けた1日の総消費カロリー"""
    return bmr * activity_factor(normalize_activity_level(activity_level))


def calc_target_calories(tdee_value: float, goal, adjustment=None) -> float:
    """TDEEに目標区分ぶんの増減を足した推奨摂取カロリー（10kcal単位に丸める）"""
    if adjustment is None:
        adjustment = GOAL_ADJUSTMENTS[normalize_goal(goal)]
    return round((tdee_value + adjustment) / 10) * 10


def calculate(profile: dict) -> dict:
    """身体データ一式からBMR / TDEE / 推奨摂取カロリーをまとめて返す。

    profile に期待するキー: sex, age, height, weight, activity_level, goal, adjustment
    年齢・身長・体重が欠けている場合は MissingProfileError を投げる。
    """
    required = {"age": "年齢", "height": "身長", "weight": "体重"}
    missing = [label for key, label in required.items() if not _to_float(profile.get(key))]
    if missing:
        raise MissingProfileError(missing)

    sex = normalize_sex(profile.get("sex", "男性"))
    age = _to_float(profile.get("age"))
    height = _to_float(profile.get("height"))
    weight = _to_float(profile.get("weight"))
    level = normalize_activity_level(profile.get("activity_level", DEFAULT_ACTIVITY_LEVEL))
    goal = normalize_goal(profile.get("goal", DEFAULT_GOAL))

    # 「カロリー調整」が入っていれば目標区分の既定値より優先する
    raw_adjustment = str(profile.get("adjustment", "")).strip()
    adjustment = _to_float(raw_adjustment) if raw_adjustment else None

    bmr = calc_bmr(sex, age, height, weight)
    tdee_value = calc_tdee(bmr, level)

    return {
        "sex": sex,
        "age": age,
        "height": height,
        "weight": weight,
        "activity_level": level,
        "activity_label": activity_label(level),
        "activity_factor": activity_factor(level),
        "goal": goal,
        "adjustment": adjustment if adjustment is not None else GOAL_ADJUSTMENTS[goal],
        "bmr": round(bmr),
        "tdee": round(tdee_value),
        "recommended_calories": calc_target_calories(tdee_value, goal, adjustment),
    }


def _to_float(value) -> float:
    """シート由来の値を数値にする（空欄・桁区切り・単位つきでも落ちないように）"""
    try:
        return float(str(value).replace(",", "").replace("kg", "").replace("cm", "").strip())
    except (TypeError, ValueError):
        return 0.0


def build_activity_level_guide() -> str:
    """活動レベルの一覧（設定を促すときに見せる）"""
    lines = ["📋 活動レベル一覧"]
    for level, (label, factor) in ACTIVITY_LEVELS.items():
        lines.append(f"{level}. {label}（×{factor}）")
    lines.append("\n例:「活動レベル 2」と送ると設定できます")
    return "\n".join(lines)
