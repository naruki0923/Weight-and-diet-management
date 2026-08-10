import re
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse

from config import API_TOKEN
import summary
import tdee

# iOSショートカットから叩くためのAPI。認証は X-API-Token ヘッダーの合言葉だけ。
app = FastAPI()

@app.exception_handler(Exception)
async def json_error(request: Request, exc: Exception):
    """想定外の例外でもJSONで返す。

    素通しするとVercelがHTMLの500ページを返し、ショートカット側は
    「テキストを辞書に変換できなかった」としか言えず原因が分からなくなる。
    """
    return JSONResponse(status_code=500,
                        content={"message": f"エラー: {type(exc).__name__}: {exc}",
                                 "error": f"{type(exc).__name__}: {exc}"})

@app.exception_handler(HTTPException)
async def json_http_error(request: Request, exc: HTTPException):
    """HTTPExceptionも message つきで返し、通知にそのまま出せるようにする"""
    return JSONResponse(status_code=exc.status_code,
                        content={"message": f"エラー: {exc.detail}", "error": str(exc.detail)})

def verify_token(token: str):
    """X-API-Tokenヘッダーの合言葉を確認する"""
    if not API_TOKEN:
        raise HTTPException(status_code=500, detail="API_TOKEN is not configured")
    if token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/meal")
async def post_meal(request: Request, x_api_token: str = Header(None)):
    """食事画像を解析して記録する。

    送り方は2通り。どちらでも受け付ける。
    - multipart/form-data: image=画像, note=補足（「大盛り」など。省略可）
    - リクエストボディに画像の生バイナリ（補足なし）
    """
    verify_token(x_api_token)

    note = ""
    if "multipart/form-data" in (request.headers.get("content-type") or ""):
        form = await request.form()
        upload = form.get("image")
        image_bytes = await upload.read() if hasattr(upload, "read") else b""
        note = str(form.get("note") or "")
    else:
        image_bytes = await request.body()

    if not image_bytes:
        raise HTTPException(status_code=400, detail="Image body is empty")

    meal = summary.analyze_and_record(image_bytes, note)

    return {"message": summary.build_meal_result(meal), "meal": meal,
            "note": note, **summary.get_daily_status()}

@app.get("/today")
async def get_today(x_api_token: str = Header(None)):
    """今日の合計と残りカロリーを返す"""
    verify_token(x_api_token)

    return {"message": summary.build_daily_summary(), **summary.get_daily_status()}

@app.post("/weight")
async def post_weight(request: Request, x_api_token: str = Header(None)):
    """体重を記録し、その体重でTDEEと目標カロリーを再計算する（ヘルスケア連携用。{"weight": 55.2} を送る）"""
    verify_token(x_api_token)

    # ショートカット側の設定に詰まりにくいよう、JSONでもフォームでも受け付ける
    if "application/json" in (request.headers.get("content-type") or ""):
        body = await request.json()
    else:
        body = await request.form()

    # ヘルスケアのサンプルは「49.2 kg」のような単位つき文字列で届くことがあるので、
    # 最初に現れる数値を拾う
    raw = str(body.get("weight", ""))
    match = re.search(r"\d+(?:\.\d+)?", raw)
    if not match:
        raise HTTPException(status_code=400, detail=f"weight must contain a number (got {raw!r})")

    return summary.record_weight_and_update(float(match.group()))

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