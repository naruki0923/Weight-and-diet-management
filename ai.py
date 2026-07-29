import json
import google.generativeai as genai
from config import GEMINI_API_KEY

# Geminiの初期設定
genai.configure(api_key=GEMINI_API_KEY)

def analyze_meal_image(image_bytes: bytes) -> dict:
    """食事画像を解析し、カロリーとPFCをJSONで返す"""
    model = genai.GenerativeModel('gemini-3.5-flash')
    
    # いただいたプロンプトをベースに、JSON出力ルールを追加
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

    # 出力フォーマット
    システムが自動処理するため、必ず以下のJSON形式のみを出力してください。Markdownブロックは不要です。
    {
      "meal_name": "[特定・または推測された料理名/商品名]",
      "data_source": "[ラベル読み取り / 公式情報の推測 / 画像からの概算]",
      "calories": 850,
      "protein": 35,
      "fat": 25,
      "carbs": 110,
      "memo": "[ラベルが読み取れなかった理由、または概算の根拠（例：ご飯普通盛り約200gとして計算など）を簡潔に記載]"
    }
    """
    
    image_parts = [{"mime_type": "image/jpeg", "data": image_bytes}]
    
    response = model.generate_content(
        [prompt, image_parts[0]],
        generation_config={"response_mime_type": "application/json"}
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