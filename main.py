from fastapi import FastAPI, Request, HTTPException, Header
from linebot.v3.webhook import WebhookParser
from linebot.v3.messaging import Configuration, ApiClient
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent, PostbackEvent

from config import LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, API_TOKEN
import line_handlers
import spreadsheet
import summary

# FastAPIのアプリケーション初期化
app = FastAPI()

# LINE Bot SDKの初期化
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
api_client = ApiClient(configuration)
parser = WebhookParser(LINE_CHANNEL_SECRET)

@app.post("/callback")
async def callback(request: Request):
    """LINEからのWebhookを受け取るエンドポイント"""
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    body_decode = body.decode("utf-8")
    
    try:
        # 署名の検証とイベントのパース
        events = parser.parse(body_decode, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # 受け取ったイベントごとに処理を振り分け
    for event in events:
        if isinstance(event, MessageEvent):
            
            # テキストメッセージの場合
            if isinstance(event.message, TextMessageContent):
                line_handlers.handle_text_message(event, api_client)
                
            # 画像メッセージの場合
            elif isinstance(event.message, ImageMessageContent):
                line_handlers.handle_image_message(event, api_client)
                
        # ボタン（Postback）が押された場合
        elif isinstance(event, PostbackEvent):
            line_handlers.handle_postback(event, api_client)

    return {"status": "ok"}


# ここから下は iOSショートカット など、LINE以外から使うためのAPI

def verify_token(token: str):
    """X-API-Tokenヘッダーの合言葉を確認する"""
    if not API_TOKEN:
        raise HTTPException(status_code=500, detail="API_TOKEN is not configured")
    if token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/meal")
async def post_meal(request: Request, x_api_token: str = Header(None)):
    """食事画像（リクエストボディに生バイナリ）を解析して記録する"""
    verify_token(x_api_token)

    image_bytes = await request.body()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Image body is empty")

    meal = summary.analyze_and_record(image_bytes)

    return {"message": summary.build_meal_result(meal), "meal": meal, **summary.get_daily_status()}

@app.get("/today")
async def get_today(x_api_token: str = Header(None)):
    """今日の合計と残りカロリーを返す"""
    verify_token(x_api_token)

    return {"message": summary.build_daily_summary(), **summary.get_daily_status()}

@app.post("/weight")
async def post_weight(request: Request, x_api_token: str = Header(None)):
    """体重を記録する（ヘルスケア連携用。{"weight": 55.2} を送る）"""
    verify_token(x_api_token)

    body = await request.json()
    try:
        weight = float(body["weight"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="weight must be a number")

    spreadsheet.record_weight(weight)

    return {"message": f"体重 {weight}kg を記録しました", "weight": weight}