from fastapi import FastAPI, Request, HTTPException
from linebot.v3.webhook import WebhookParser
from linebot.v3.messaging import Configuration, ApiClient
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent, PostbackEvent

from config import LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET
import line_handlers

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