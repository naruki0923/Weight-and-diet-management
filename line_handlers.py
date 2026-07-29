from linebot.v3.messaging import (
    ApiClient, MessagingApi, MessagingApiBlob, ReplyMessageRequest, TextMessage,
    QuickReply, QuickReplyItem, PostbackAction
)
import spreadsheet
import summary
import tdee
import ai
import re

# 文面の組み立ては summary.py に集約（ショートカット用APIと共通）
build_daily_summary = summary.build_daily_summary

# 「身長 168」のように送って設定シートを更新できる項目（体重は数字だけ送って記録する）
PROFILE_COMMANDS = {
    "性別": ("性別", ""),
    "年齢": ("年齢", "歳"),
    "身長": ("身長", "cm"),
    "目標区分": ("目標区分", ""),
    "カロリー調整": ("カロリー調整", "kcal"),
}

def handle_text_message(event, api_client: ApiClient):
    """テキストメッセージの処理"""
    messaging_api = MessagingApi(api_client)
    user_text = event.message.text.strip()
    reply_token = event.reply_token

    # 目標カロリーの設定（例: 「目標 2000」「目標2000kcal」）
    target_match = re.match(r'^目標\s*(\d+)\s*(?:kcal|キロカロリー)?$', user_text)
    if target_match:
        calories = int(target_match.group(1))
        spreadsheet.set_target_calories(calories)
        reply_msg = TextMessage(text=f"目標カロリーを {calories} kcal に設定しました🎯\n\n{build_daily_summary()}")
        request = ReplyMessageRequest(reply_token=reply_token, messages=[reply_msg])
        messaging_api.reply_message(request)
        return

    # TDEEの計算結果を表示
    if user_text in ["TDEE", "tdee", "消費カロリー", "代謝"]:
        reply_msg = TextMessage(text=summary.build_tdee_summary())
        request = ReplyMessageRequest(reply_token=reply_token, messages=[reply_msg])
        messaging_api.reply_message(request)
        return

    # 推奨摂取カロリーを目標カロリーに反映
    if user_text in ["TDEEを目標に", "TDEE反映", "目標をTDEEに"]:
        try:
            status = summary.apply_tdee_as_target()
            text = (
                f"目標カロリーを {status['recommended_calories']:.0f} kcal に設定しました🎯\n"
                f"（TDEE {status['tdee']} kcal / 目標「{status['goal']}」）\n\n"
                f"{build_daily_summary()}"
            )
        except tdee.MissingProfileError:
            text = summary.build_tdee_summary()
        reply_msg = TextMessage(text=text)
        request = ReplyMessageRequest(reply_token=reply_token, messages=[reply_msg])
        messaging_api.reply_message(request)
        return

    # 活動レベルの一覧を表示（値なしで送られた場合）
    if user_text == "活動レベル":
        reply_msg = TextMessage(text=tdee.build_activity_level_guide())
        request = ReplyMessageRequest(reply_token=reply_token, messages=[reply_msg])
        messaging_api.reply_message(request)
        return

    # 活動レベルの設定（例:「活動レベル 2」）→ 係数が変わるのでカロリーも再計算
    activity_match = re.match(r'^活動レベル\s*(.+)$', user_text)
    if activity_match:
        level = tdee.normalize_activity_level(activity_match.group(1))
        spreadsheet.set_setting("活動レベル", level)
        reply_msg = TextMessage(
            text=f"活動レベルを {level}（{tdee.activity_label(level)}）に設定しました🏃\n\n{summary.build_tdee_summary()}"
        )
        request = ReplyMessageRequest(reply_token=reply_token, messages=[reply_msg])
        messaging_api.reply_message(request)
        return

    # 身体データの設定（例:「身長 168」「年齢 20」「目標区分 増量」）
    profile_match = re.match(r'^(性別|年齢|身長|目標区分|カロリー調整)\s*(.+)$', user_text)
    if profile_match:
        key, unit = PROFILE_COMMANDS[profile_match.group(1)]
        value = profile_match.group(2).strip()
        spreadsheet.set_setting(key, value, unit)
        reply_msg = TextMessage(text=f"{key}を「{value}」に設定しました✅\n\n{summary.build_tdee_summary()}")
        request = ReplyMessageRequest(reply_token=reply_token, messages=[reply_msg])
        messaging_api.reply_message(request)
        return

    if user_text in ["今日の合計", "残り", "あと何カロリー", "カロリー"]:
        reply_msg = TextMessage(text=build_daily_summary())
        request = ReplyMessageRequest(reply_token=reply_token, messages=[reply_msg])
        messaging_api.reply_message(request)
        return

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
    if user_text in ["プランク完了", "腹筋完了", "腕立て完了"]:
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
        # 体重が変わればBMR/TDEEも変わるので、記録のたびに目標カロリーまで更新する
        result = summary.record_weight_and_update(weight)
        reply_msg = TextMessage(text=result["message"])
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
        tasks = ["プランク", "腹筋", "腕立て"]
        unfinished_tasks = [t for t in tasks if status.get(t) != "済"]
        
        if not unfinished_tasks:
            streak = spreadsheet.get_training_streak()
            # 7日単位のスタンプカード風テキストを作成
            stamp_text = "🟩" * (streak % 7 if streak % 7 != 0 else 7) + "⬜" * (7 - (streak % 7) if streak % 7 != 0 else 0)
                
            reply_msg = TextMessage(text=f"『{task_name}』を記録しました！\n\n本日分すべてコンプリートです！\n\n【現在 {streak} 日連続達成中！】\n今週のスタンプ: {stamp_text}")
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

            # 記録後の「今日の累計」で判定・アドバイスさせる
            today_totals = spreadsheet.get_today_meal_totals()
            target_totals = spreadsheet.get_target_nutrition()
            advice = ai.generate_advice(today_totals, target_totals)

            reply_text = (
                f"🍽️ メニュー名: {meal_name}\n"
                f"🔍 データソース: {data_source}\n\n"
                f"【この食事】\n"
                f"⚡ カロリー: {calories} kcal\n"
                f"💪 タンパク質 (P): {protein}g\n"
                f"💧 脂質 (F): {fat}g\n"
                f"🍚 炭水化物 (C): {carbs}g\n\n"
                f"💡 解析メモ:\n{memo}\n\n"
                f"{build_daily_summary()}\n\n"
                f"🏋️‍♂️ AIアドバイス:\n{advice}"
            )
        except Exception as e:
            reply_text = f"解析エラー: {str(e)}"
        
        reply_msg = TextMessage(text=reply_text)
        request = ReplyMessageRequest(reply_token=reply_token, messages=[reply_msg])
        messaging_api.reply_message(request)