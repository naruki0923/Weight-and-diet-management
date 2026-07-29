from fastapi import FastAPI, Request, HTTPException, Header

from config import API_TOKEN
import summary
import tdee

# iOSショートカットから叩くためのAPI。認証は X-API-Token ヘッダーの合言葉だけ。
app = FastAPI()

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
    """体重を記録し、その体重でTDEEと目標カロリーを再計算する（ヘルスケア連携用。{"weight": 55.2} を送る）"""
    verify_token(x_api_token)

    body = await request.json()
    try:
        weight = float(body["weight"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="weight must be a number")

    return summary.record_weight_and_update(weight)

@app.get("/tdee")
async def get_tdee(x_api_token: str = Header(None)):
    """今の身体データからBMR / TDEE / 推奨摂取カロリーを返す"""
    verify_token(x_api_token)

    try:
        return {"message": summary.build_tdee_summary(), **summary.get_tdee_status()}
    except tdee.MissingProfileError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/tdee/apply")
async def post_tdee_apply(x_api_token: str = Header(None)):
    """推奨摂取カロリーを目標カロリーとして設定する"""
    verify_token(x_api_token)

    try:
        status = summary.apply_tdee_as_target()
    except tdee.MissingProfileError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"message": f"目標カロリーを {status['recommended_calories']:.0f} kcal に設定しました", **status}