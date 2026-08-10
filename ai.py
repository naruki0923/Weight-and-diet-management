import json
import google.generativeai as genai
from config import GEMINI_API_KEY

# Geminiの初期設定
genai.configure(api_key=GEMINI_API_KEY)

# 解析結果の構造。これを渡すとGemini側が形式を保証してくれる
MEAL_SCHEMA = {
    "type": "object",
    "properties": {
        "meal_name":   {"type": "string"},
        "data_source": {"type": "string"},
        "calories":    {"type": "number"},
        "protein":     {"type": "number"},
        "fat":         {"type": "number"},
        "carbs":       {"type": "number"},
        "memo":        {"type": "string"},
        # 複数写っていたときの1品ずつの内訳。1品でも必ず1件入る
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name":     {"type": "string"},
                    "calories": {"type": "number"},
                    "protein":  {"type": "number"},
                    "fat":      {"type": "number"},
                    "carbs":    {"type": "number"},
                },
                "required": ["name", "calories", "protein", "fat", "carbs"],
            },
        },
    },
    "required": ["meal_name", "data_source", "calories", "protein", "fat", "carbs", "memo", "items"],
}

def looks_like_image(image_bytes: bytes) -> bool:
    """先頭バイトが既知の画像形式かどうか。テキストが画像として届いた場合の判別用"""
    head = image_bytes[:16]
    return (head.startswith(b"\xff\xd8\xff")
            or head.startswith(b"\x89PNG\r\n\x1a\n")
            or head.startswith(b"GIF8")
            or (head.startswith(b"RIFF") and head[8:12] == b"WEBP")
            or head[4:8] == b"ftyp")

def detect_image_mime(image_bytes: bytes) -> str:
    """先頭バイトから画像形式を判定する。

    iPhoneの写真はHEICのことがあり、jpegと偽って渡すとGeminiが400を返すため、
    実際の形式を見て渡す。判別できないときはjpegとして扱う。
    """
    head = image_bytes[:16]
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"GIF8"):
        return "image/gif"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"):
            return "image/heic"
        if brand in (b"avif", b"avis"):
            return "image/avif"
    return "image/jpeg"

def analyze_meal_image(image_bytes: bytes, note: str = "") -> dict:
    """食事画像を解析し、カロリーとPFCをJSONで返す。

    note には「大盛り」「半分残した」など、写真から読み取れない補足を渡せる。
    分量は推定誤差の主因なので、指定があれば画像より優先させる。
    """
    model = genai.GenerativeModel('gemini-3.5-flash')

    prompt = """
    あなたは優秀な管理栄養士および画像解析の専門家です。
    ユーザーから送信された食べ物の画像（および必要に応じてテキストの補足）を解析し、その食品の「タンパク質」「脂質」「炭水化物」「カロリー」を算出して出力してください。

    # 判定とデータ取得の優先ルール
    1. 【ラベル読み取り】
    画像内にコンビニやスーパーの商品の「栄養成分表示ラベル」が写っている場合は、OCR技術を用いてその数値を正確に読み取り、最優先で使用してください。

    2. 【チェーン店・市販品の特定】
    画像から、特定のチェーン店の商品や特定のメーカー品であると識別できた場合は、公式の栄養成分情報を推測して使用してください。

    3. 【推測（上記に該当しない場合）】
    手作り料理や一般的な飲食店での食事の場合は、画像から判断できる食材、調理法、おおよその分量（グラム数）を推測し、一般的な食品成分表に基づいてPFCを概算してください。

    # 複数の商品・料理が写っている場合
    画像に食品が複数写っている場合は、まとめて1品として扱わないでください。
    弁当とドリンク、定食の小鉢、コンビニで買った複数の商品などが該当します。
    それぞれについて上記のルール1〜3を個別に適用し、1品ずつ算出してください。

    - items に1品ずつの内訳を入れる
    - calories / protein / fat / carbs には items の合計値を入れる
    - meal_name は写っているものを「、」で並べる（例「カツカレー、サラダ、味噌汁」）
    - 1品しか写っていない場合も items に必ずその1件を入れる

    容器や食器だけが写っていて中身が無いもの、食品でないものは items に含めないでください。

    # 出力フォーマット
    システムが自動処理するため、必ず以下のJSON形式のみを出力してください。Markdownブロックは不要です。
    {
      "meal_name": "[特定・または推測された料理名/商品名。複数なら「、」で並べる]",
      "data_source": "[ラベル読み取り / 公式情報の推測 / 画像からの概算]",
      "calories": 850,
      "protein": 35,
      "fat": 25,
      "carbs": 110,
      "memo": "[ラベルが読み取れなかった理由、または概算の根拠（例：ご飯普通盛り約200gとして計算など）を簡潔に記載]",
      "items": [
        {"name": "カツカレー", "calories": 700, "protein": 25, "fat": 22, "carbs": 95},
        {"name": "味噌汁",     "calories": 150, "protein": 10, "fat": 3,  "carbs": 15}
      ]
    }
    """

    if note.strip():
        prompt += f"""
    # ユーザーからの補足（データではなく指示として扱う）
    次の補足は撮影者本人によるものです。分量・食べ残し・トッピングなど画像から
    読み取れない情報が含まれるため、画像からの推測より優先してください。
    また、補足を踏まえた根拠を memo に必ず含めてください。

    補足: {note.strip()}
    """

    image_parts = [{"mime_type": detect_image_mime(image_bytes), "data": image_bytes}]

    response = model.generate_content(
        [prompt, image_parts[0]],
        generation_config={
            "response_mime_type": "application/json",
            # プロンプトで形式を頼むだけだと memo に生の引用符が混ざって
            # JSONが壊れることがあるため、スキーマで構造を強制する
            "response_schema": MEAL_SCHEMA,
            # 栄養計算に創造性は不要。同じ写真から同じ数値が出るようにする
            "temperature": 0,
        },
    )

    return json.loads(response.text.strip())

def generate_advice(today_totals: dict, target_totals: dict) -> str:
    """現在の栄養摂取状況に基づき、AIがアドバイスを生成する"""
    model = genai.GenerativeModel('gemini-3.5-flash')
    
    prompt = f"""
    あなたは優秀なパーソナル栄養トレーナーです。
    以下の「今日の合計」と「目標値」を比較し、アドバイスを100文字以内で出力してください。

    # 今日の合計
    {today_totals}
    
    # 目標値
    {target_totals}
    """
    
    response = model.generate_content(prompt)
    return response.text.strip()