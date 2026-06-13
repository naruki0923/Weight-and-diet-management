from linebot.v3.messaging import (
    ApiClient, MessagingApi, MessagingApiBlob, ReplyMessageRequest, TextMessage,
    QuickReply, QuickReplyItem, PostbackAction
)
import spreadsheet
import ai
import re

def handle_text_message(event, api_client: ApiClient):
    """テキストメッセージの処理（体重記録・データ照会など）"""
    messaging_api = MessagingApi(api_client)
    user_text = event.message.text.strip()
    reply_token = event.reply_token
    
    # 数値のみ（小数点含む）の場合は「体重」とみなす
    if re.match(r'^\d+(\.\d+)?$', user_text):
        weight = float(user_text)
        spreadsheet.record_weight(weight)
        
        reply_msg = TextMessage(text=f"体重 {weight}kg を記録しました！順調ですね💪")
        request = ReplyMessageRequest(reply_token=reply_token, messages=[reply_msg])
        messaging_api.reply_message(request)
        return

    # その他のテキスト（データ照会など）の簡易実装
    if "カロリー" in user_text:
        reply_msg = TextMessage(text="データ照会機能は現在準備中です🙇‍♂️")
        request = ReplyMessageRequest(reply_token=reply_token, messages=[reply_msg])
        messaging_api.reply_message(request)

def handle_image_message(event, api_client: ApiClient):
    """画像メッセージ受信時：クイックリプライで意図を確認する"""
    messaging_api = MessagingApi(api_client)
    reply_token = event.reply_token
    message_id = event.message.id
    
    # クイックリプライのボタンを作成
    btn_record = QuickReplyItem(
        action=PostbackAction(label="🍽️ 食事を記録", data=f"action=meal&msg_id={message_id}")
    )
    btn_memo = QuickReplyItem(
        action=PostbackAction(label="📝 単なるメモ", data="action=memo")
    )
    btn_cancel = QuickReplyItem(
        action=PostbackAction(label="❌ キャンセル", data="action=cancel")
    )
    
    quick_reply = QuickReply(items=[btn_record, btn_memo, btn_cancel])
    reply_msg = TextMessage(text="この画像は何の記録ですか？", quick_reply=quick_reply)
    
    request = ReplyMessageRequest(reply_token=reply_token, messages=[reply_msg])
    messaging_api.reply_message(request)

def handle_postback(event, api_client: ApiClient):
    """ボタン（Postback）が押された時の処理"""
    messaging_api = MessagingApi(api_client)
    blob_api = MessagingApiBlob(api_client)
    reply_token = event.reply_token
    postback_data = event.postback.data
    
    # リッチメニューからの筋トレ記録
    if postback_data == "action=training_done":
        spreadsheet.record_training()
        reply_msg = TextMessage(text="ナイスバルク！💪 筋トレを記録しました！")
        request = ReplyMessageRequest(reply_token=reply_token, messages=[reply_msg])
        messaging_api.reply_message(request)
        return

    # クイックリプライからの食事記録
    if postback_data.startswith("action=meal"):
        # URLパラメータのように渡したメッセージIDを取り出す
        params = dict(item.split("=") for item in postback_data.split("&"))
        msg_id = params.get("msg_id")
        
        # 処理中メッセージを返す（オプション・LINE APIの仕様上非同期処理が必要な場合あり）
        # ここでは同期処理として簡略化して記述します
        
        # 1. LINEサーバーから画像データを取得
        image_bytes = blob_api.get_message_content(msg_id)
        
        # 2. Geminiで解析
        try:
            nutrition_data = ai.analyze_meal_image(image_bytes)
            meal_name = nutrition_data.get("meal_name", "不明な食事")
            calories = nutrition_data.get("calories", 0)
            protein = nutrition_data.get("protein", 0)
            fat = nutrition_data.get("fat", 0)
            carbs = nutrition_data.get("carbs", 0)
            
            # 新しく追加されたデータを受け取る
            data_source = nutrition_data.get("data_source", "画像からの概算")
            memo = nutrition_data.get("memo", "特になし")
            
            # 3. スプレッドシートへ記録（ここはそのまま）
            spreadsheet.record_meal_data(meal_name, calories, protein, fat, carbs)
            
            # 4. アドバイスの生成
            target_totals = spreadsheet.get_target_nutrition()
            today_totals = {"calories": calories, "protein": protein, "fat": fat, "carbs": carbs}
            advice = ai.generate_advice(today_totals, target_totals)
            
            # 5. 結果の返信（いただいたプロンプトのフォーマットをここで再現！）
            reply_text = (
                f"🍽️ メニュー名: {meal_name}\n"
                f"🔍 データソース: {data_source}\n\n"
                f"【栄養成分】\n"
                f"⚡ カロリー: {calories} kcal\n"
                f"💪 タンパク質 (P): {protein}g\n"
                f"💧 脂質 (F): {fat}g\n"
                f"🍚 炭水化物 (C): {carbs}g\n\n"
                f"💡 解析メモ:\n{memo}\n\n"
                f"🏋️‍♂️ AIアドバイス:\n{advice}"
            )
            
        except Exception as e:
            # 🌟 ここでエラーの詳細をターミナルに表示させる
            import traceback
            traceback.print_exc()
            # 🌟 LINEにもエラーが出たことを知らせる
            reply_text = f"解析エラー: {str(e)}"
        
        reply_msg = TextMessage(text=reply_text)
        request = ReplyMessageRequest(reply_token=reply_token, messages=[reply_msg])
        messaging_api.reply_message(request)