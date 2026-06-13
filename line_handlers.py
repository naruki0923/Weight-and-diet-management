from linebot.v3.messaging import (
    ApiClient, MessagingApi, MessagingApiBlob, ReplyMessageRequest, TextMessage,
    QuickReply, QuickReplyItem, PostbackAction
)
import spreadsheet
import ai
import re

def handle_text_message(event, api_client: ApiClient):
    """テキストメッセージの処理"""
    messaging_api = MessagingApi(api_client)
    user_text = event.message.text.strip()
    reply_token = event.reply_token
    
    if user_text == "体重入力":
        reply_msg = TextMessage(text="今日の体重を数字のみ（例: 65.5）で送信してください！⚖️")
        request = ReplyMessageRequest(reply_token=reply_token, messages=[reply_msg])
        messaging_api.reply_message(request)
        return

    if user_text == "食事入力":
        reply_msg = TextMessage(text="食べたものの写真を送信してください！AIがカロリーとPFCを計算します🍽️")
        request = ReplyMessageRequest(reply_token=reply_token, messages=[reply_msg])
        messaging_api.reply_message(request)
        return

    # ▼ ここが筋トレの呼び出しフロー ▼
    # 2. 筋トレ記録（LINE側から送られてくる文字をそのままキャッチ）
    if user_text in ["プランク完了", "腹筋完了", "腕立て伏せ完了"]:
        task_name = user_text.replace("完了", "") 
        
        spreadsheet.update_training_task(task_name)
        status, _ = spreadsheet.get_today_training_status()
        tasks = ["プランク", "腹筋", "腕立て伏せ"]
        unfinished_tasks = [t for t in tasks if status.get(t) != "済"]
        
        if not unfinished_tasks:
            streak = spreadsheet.get_training_streak()
            reply_msg = TextMessage(text=f"『{task_name}』を記録しました！\n現在{streak}日連続達成中！】")
        else:
            remaining = "、".join(unfinished_tasks)
            reply_msg = TextMessage(text=f"『{task_name}』を記録しました！\n残りのタスクは【 {remaining} 】です！")
            
        request = ReplyMessageRequest(reply_token=reply_token, messages=[reply_msg])
        messaging_api.reply_message(request)
        return

    if user_text == "過去の記録":
        reply_msg = TextMessage(text=f"「{user_text}」機能は現在準備中です。アップデートをお楽しみに！🙇‍♂️")
        request = ReplyMessageRequest(reply_token=reply_token, messages=[reply_msg])
        messaging_api.reply_message(request)
        return

    if re.match(r'^\d+(\.\d+)?$', user_text):
        weight = float(user_text)
        spreadsheet.record_weight(weight)
        reply_msg = TextMessage(text=f"体重 {weight}kg を記録しました！順調ですね💪")
        request = ReplyMessageRequest(reply_token=reply_token, messages=[reply_msg])
        messaging_api.reply_message(request)
        return

def handle_image_message(event, api_client: ApiClient):
    """画像メッセージ受信時の処理（変更なし）"""
    messaging_api = MessagingApi(api_client)
    reply_token = event.reply_token
    message_id = event.message.id
    
    btn_record = QuickReplyItem(action=PostbackAction(label="🍽️ 食事を記録", data=f"action=meal&msg_id={message_id}"))
    btn_memo = QuickReplyItem(action=PostbackAction(label="📝 単なるメモ", data="action=memo"))
    btn_cancel = QuickReplyItem(action=PostbackAction(label="❌ キャンセル", data="action=cancel"))
    
    quick_reply = QuickReply(items=[btn_record, btn_memo, btn_cancel])
    reply_msg = TextMessage(text="この画像は何の記録ですか？", quick_reply=quick_reply)
    request = ReplyMessageRequest(reply_token=reply_token, messages=[reply_msg])
    messaging_api.reply_message(request)

def handle_postback(event, api_client: ApiClient):
    """ボタンが押された時の処理"""
    messaging_api = MessagingApi(api_client)
    blob_api = MessagingApiBlob(api_client)
    reply_token = event.reply_token
    postback_data = event.postback.data
    
    # ▼ 筋トレの個別ボタンが押された時の処理 ▼
    if postback_data.startswith("action=training_done"):
        params = dict(item.split("=") for item in postback_data.split("&"))
        task_name = params.get("task")
        
        # スプレッドシートに記録
        spreadsheet.update_training_task(task_name)
        
        # 残りのタスクを確認
        status, _ = spreadsheet.get_today_training_status()
        tasks = ["プランク", "腹筋", "腕立て伏せ"]
        unfinished_tasks = [t for t in tasks if status.get(t) != "済"]
        
        if not unfinished_tasks:
            streak = spreadsheet.get_training_streak()
            # 7日単位のスタンプカード風テキストを作成
            stamp_text = "🟩" * (streak % 7 if streak % 7 != 0 else 7) + "⬜" * (7 - (streak % 7) if streak % 7 != 0 else 0)
                
            reply_msg = TextMessage(text=f"『{task_name}』を記録しました！\n\n本日分すべてコンプリートです！素晴らしい！🔥\n\n【現在 {streak} 日連続達成中！】\n今週のスタンプ: {stamp_text}")
        else:
            quick_reply_items = []
            for task in unfinished_tasks:
                quick_reply_items.append(
                    QuickReplyItem(action=PostbackAction(label=f"{task}完了", data=f"action=training_done&task={task}"))
                )
            quick_reply = QuickReply(items=quick_reply_items)
            reply_msg = TextMessage(text=f"『{task_name}』を記録しました！ナイス！👍\n残りのタスクも頑張りましょう！", quick_reply=quick_reply)
            
        request = ReplyMessageRequest(reply_token=reply_token, messages=[reply_msg])
        messaging_api.reply_message(request)
        return

    # （食事画像の処理などは元のまま）
    if postback_data.startswith("action=meal"):
        params = dict(item.split("=") for item in postback_data.split("&"))
        msg_id = params.get("msg_id")
        image_bytes = blob_api.get_message_content(msg_id)
        
        try:
            nutrition_data = ai.analyze_meal_image(image_bytes)
            meal_name = nutrition_data.get("meal_name", "不明な食事")
            calories = nutrition_data.get("calories", 0)
            protein = nutrition_data.get("protein", 0)
            fat = nutrition_data.get("fat", 0)
            carbs = nutrition_data.get("carbs", 0)
            data_source = nutrition_data.get("data_source", "画像からの概算")
            memo = nutrition_data.get("memo", "特になし")
            
            spreadsheet.record_meal_data(meal_name, calories, protein, fat, carbs)
            
            target_totals = spreadsheet.get_target_nutrition()
            today_totals = {"calories": calories, "protein": protein, "fat": fat, "carbs": carbs}
            advice = ai.generate_advice(today_totals, target_totals)
            
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
            reply_text = f"解析エラー: {str(e)}"
        
        reply_msg = TextMessage(text=reply_text)
        request = ReplyMessageRequest(reply_token=reply_token, messages=[reply_msg])
        messaging_api.reply_message(request)