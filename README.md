# 体重・食事管理 Bot

食事の写真から Gemini がカロリーと PFC を算出し、Google スプレッドシートに記録する。
今日の合計と「目標まであと何 kcal か」を返す。

入力は **iOS ショートカット**（写真 → 共有 → タップ）、振り返りは **スプレッドシートのグラフ**（PC）を想定。
LINE Bot も従来どおり使える。

## 構成

| ファイル | 役割 |
|---|---|
| `main.py` | FastAPI。LINE Webhook と、ショートカット用の API |
| `summary.py` | 解析 → 記録 → 文面組み立て（インターフェース非依存） |
| `line_handlers.py` | LINE 用のメッセージ処理 |
| `spreadsheet.py` | Google スプレッドシートの読み書き |
| `ai.py` | Gemini による画像解析とアドバイス生成 |
| `config.py` | 環境変数の読み込み |

## 環境変数（`.env`）

```
LINE_CHANNEL_ACCESS_TOKEN=...
LINE_CHANNEL_SECRET=...
GEMINI_API_KEY=...
SPREADSHEET_URL_OR_KEY=1kWV2tOxksTpV_QeaePrDcwKLLIdpg8m-6n5d0kz5JU4
GCP_SERVICE_ACCOUNT_JSON=service_account.json
API_TOKEN=<自分で決めた長い文字列>
```

`API_TOKEN` はショートカットから API を叩くときの合言葉。次のコマンドで生成できる。

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

`GCP_SERVICE_ACCOUNT_JSON` は **ファイルパスでも JSON 文字列そのものでも**よい。
ローカルは `service_account.json` を置いてパス指定、Vercel は中身を貼り付ける。

## デプロイ（Vercel）

1. このリポジトリを Vercel にインポートする（Framework Preset は `Other`）
2. Settings → Environment Variables に上記をすべて登録する
   - `GCP_SERVICE_ACCOUNT_JSON` には `service_account.json` の**中身を丸ごと**貼る
3. デプロイすると `https://<プロジェクト名>.vercel.app` が払い出される
4. LINE Developers の Webhook URL を `https://<...>.vercel.app/callback` に変更する

以降は `git push` するたびに自動デプロイされる。
`vercel.json` が全リクエストを `main.py` の FastAPI アプリに流している。

動作確認:

```bash
curl -H "X-API-Token: $API_TOKEN" https://<プロジェクト名>.vercel.app/today
```

## API

いずれも `X-API-Token` ヘッダーに `API_TOKEN` を入れる。

| メソッド | パス | 内容 |
|---|---|---|
| `POST` | `/meal` | ボディに画像の生バイナリ。解析して記録し、結果と今日の合計を返す |
| `GET` | `/today` | 今日の合計と残りカロリーを返す |
| `POST` | `/weight` | `{"weight": 55.2}` を送ると体重を記録 |
| `POST` | `/callback` | LINE の Webhook（従来どおり） |

レスポンスの `message` に、そのまま通知に出せる文面が入っている。

```json
{
  "message": "🍽️ 鮭おにぎり\n⚡ 180 kcal（P 4 / F 1 / C 38）\n\n📊 今日の合計（2食）...",
  "meal": { "meal_name": "鮭おにぎり", "calories": 180, ... },
  "totals": { "calories": 1303.0, "protein": 28.0, ... },
  "target": 2300.0,
  "remaining": 997.0
}
```

## iOS ショートカットの作り方

### 食事を記録する

ショートカット App で新規作成し、以下を並べる。

1. **共有シートに表示** をオンにする（設定 → 受け取る内容を「イメージ」のみにする）
2. `URL の内容を取得`
   - URL: `https://<デプロイ先>/meal`
   - 方法: `POST`
   - ヘッダ: `X-API-Token` → `<API_TOKEN>`
   - 要求の本文: **ファイル** を選び、`ショートカットの入力` を指定
3. `辞書の値を取得` → キー `message`
4. `通知を表示` → さきほどの値

写真 App で写真を開き、共有 → このショートカットをタップすれば記録される。

### 今日の残りを確認する

1. `URL の内容を取得` → `https://<デプロイ先>/today`、`GET`、ヘッダに `X-API-Token`
2. `辞書の値を取得` → キー `message`
3. `通知を表示`

ホーム画面に追加しておくと 1 タップで見られる。

### 体重を記録する（任意）

eufy Life アプリを開くとヘルスケアに同期されるので、そこから拾う。

1. `ヘルスケアのサンプルを検索` → 種類「体重」、並び替え「開始日 / 新しい順」、上限 1
2. `URL の内容を取得` → `https://<デプロイ先>/weight`、`POST`、ヘッダに `X-API-Token`
   - 要求の本文: **JSON**、キー `weight`（数値）にヘルスケアの値を入れる

オートメーションで「毎朝 8:00」に実行すれば自動で入る。

## PC でグラフを見る

スプレッドシートに新しいシート（例: `日別集計`）を追加し、A1 に次を貼る。

```
=QUERY(
  {ARRAYFORMULA(LEFT(食事記録シート!A:A,10)), ARRAYFORMULA(IFERROR(食事記録シート!C:C*1,0))},
  "select Col1, sum(Col2) where Col1 <> '' group by Col1 order by Col1 label Col1 '日付', sum(Col2) '合計kcal'",
  0
)
```

日付ごとの合計カロリーが並ぶので、範囲を選んで「挿入 → グラフ」で折れ線にする。
目標ラインを引きたい場合は C 列に `=2300` を並べて系列に加える。

## シートの構造（注意点）

| シート | ヘッダー | 列 |
|---|---|---|
| 設定シート | あり（**B1 は空欄**） | 項目名 / 設定値 |
| 食事記録シート | **なし。1 行目からデータ** | 日時 / メニュー名 / カロリー / P / F / C |
| 体重記録シート | なし | 日時 / 体重 |
| 筋トレ記録シート | あり | 日付 / プランク / 腹筋 / 腕立て伏せ |

シートごとにヘッダーの有無が違うため、`get_all_records()` は使わず
`get_all_values()` と列位置で読んでいる。

目標カロリーの項目名は `目標カロリー` ではなく **`カロリー`**（設定シート B3）。

## 既知の問題

- 筋トレ機能は保留中。`line_handlers.py` が受け取る「腕立て」と
  `spreadsheet.py` の `col_map` の「腕立て伏せ」が一致せず、腕立てだけ記録されない。
