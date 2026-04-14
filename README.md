# 早押しボタンシステム

Raspberry Pi Pico 2 W を使用したイベント用早押しボタンシステム。
8人対応、ランプ内蔵ボタン、ブラウザベースの管理画面・表示画面を備える。

## システム構成図

```
                        ┌─────────────────────────┐
 [プレイヤーボタン×8] ──→│                         │←── [正解/不正解/リセット/ARM/STOP
 [プレイヤーランプ×8] ←──│     Raspberry Pi         │     /ジングル/カウントダウン ボタン]
                        │     Pico 2 W             │
                        │                         │
                        │     Wi-Fi (STA or AP)    │
                        └────────┬────────────────┘
                                 │
                        ┌────────┴────────┐
                   [管理画面]         [表示画面]
                   /admin              /
                  (司会者PC/タブレット)  (プロジェクター等)
```

## 機能一覧

### ハードウェア
- 8人分の早押しボタン入力 + ランプ出力
- 司会者用物理ボタン7個（正解/不正解/リセット/ARM/STOP/ジングル/カウントダウン）
- ランプ制御 (PWM輝度): 回答権者=100%点灯、待ち=20%点灯、未押下=消灯

### ソフトウェア
- Wi-Fi: 既存ネットワーク接続(STA) / 自前アクセスポイント(AP) 自動切替
- WebSocketによるリアルタイム通信
- ブラウザベースの管理画面・表示画面
- Discord Webhook による起動通知
- プレイヤー名登録、スコア管理
- 着順記録 + 1位からの時間差表示(マイクロ秒精度)
- 回答権の自動移動（不正解時に次の押下者へ）
- 出題ジングル再生
- 10秒カウントダウンタイマー
- Wi-Fi設定画面 (`/setup`)

## ディレクトリ構成

```
hayaoshi_button/
├── boot.py              # MicroPython起動設定 (150MHz)
├── main.py              # エントリーポイント (Wi-Fi接続、Webサーバー、全体統合)
├── wifi.py              # Wi-Fi接続管理 (STA/AP自動切替)
├── buttons.py           # GPIO制御 (ボタン入力、ランプ出力、点滅制御)
├── game.py              # ゲームステートマシン (状態管理、回答権管理)
├── protocol.py          # WebSocketメッセージプロトコル定義
├── ws_manager.py        # WebSocket接続管理、ブロードキャスト
├── server.py            # (未使用: main.pyに統合済み)
├── config.json          # 設定ファイル (Wi-Fi、ゲーム設定)
├── lib/
│   └── microdot/        # microdot Webフレームワーク
│       ├── __init__.py
│       ├── microdot.py
│       ├── websocket.py
│       └── helpers.py
└── www/
    ├── admin.html       # 管理画面
    ├── admin.js         # 管理画面ロジック
    ├── display.html     # プレイヤー表示画面
    ├── display.js       # 表示画面ロジック (効果音、カウントダウン)
    ├── setup.html       # Wi-Fi設定画面
    ├── style.css        # 共通CSS変数
    └── sounds/          # 効果音ファイル (要配置)
        ├── p1.mp3 ~ p8.mp3   # プレイヤー別押下音
        ├── correct.mp3        # 正解音
        ├── incorrect.mp3      # 不正解音
        ├── jingle.mp3         # 出題ジングル
        └── countdown.mp3      # カウントダウンBGM
```

## GPIO割り当て

```
Pico 2W ピン配置:
                    USB
              ┌─────┴─────┐
  P1ボタン GP0  [1] │●          │ [40] VBUS (5V)
  P2ボタン GP1  [2] │●          │ [39] VSYS
           GND  [3] │●          │ [38] GND
  P3ボタン GP2  [4] │●          │ [37] 3V3 EN
  P4ボタン GP3  [5] │●          │ [36] 3V3 OUT
  P5ボタン GP4  [6] │●          │ [35] ADC VREF
  P6ボタン GP5  [7] │●          │ [34] GP28
           GND  [8] │●          │ [33] GND
  P7ボタン GP6  [9] │●          │ [32] GP27
  P8ボタン GP7 [10] │●          │ [31] GP26
  P1ランプ GP8 [11] │●          │ [30] RUN
  P2ランプ GP9 [12] │●          │ [29] GP22 ← カウントダウンボタン
           GND [13] │●          │ [28] GND
  P3ランプ GP10 [14] │●          │ [27] GP21 ← ジングルボタン
  P4ランプ GP11 [15] │●          │ [26] GP20 ← STOPボタン
  P5ランプ GP12 [16] │●          │ [25] GP19 ← ARMボタン
  P6ランプ GP13 [17] │●          │ [24] GP18 ← リセットボタン
           GND [18] │●          │ [23] GND
  P7ランプ GP14 [19] │●          │ [22] GP17 ← 不正解ボタン
  P8ランプ GP15 [20] │●          │ [21] GP16 ← 正解ボタン
              └───────────┘
```

| GP | ピン番号 | 用途 | 方向 |
|----|---------|------|------|
| GP0-GP7 | 1,2,4,5,6,7,9,10 | プレイヤー1-8 ボタン | INPUT (PULL_UP) |
| GP8-GP15 | 11,12,14,15,16,17,19,20 | プレイヤー1-8 ランプ | PWM OUTPUT |
| GP16 | 21 | 正解ボタン | INPUT (PULL_UP) |
| GP17 | 22 | 不正解ボタン | INPUT (PULL_UP) |
| GP18 | 24 | リセットボタン | INPUT (PULL_UP) |
| GP19 | 25 | ARMボタン | INPUT (PULL_UP) |
| GP20 | 26 | STOPボタン | INPUT (PULL_UP) |
| GP21 | 27 | ジングルボタン | INPUT (PULL_UP) |
| GP22 | 29 | カウントダウンボタン | INPUT (PULL_UP) |

**ボタン配線**: 各ボタンは GPピン と GND の2本を接続（内部プルアップ使用、外付け抵抗不要）

**ランプ配線**: PWM輝度制御対応（回答権者=100%、待ち=20%、消灯=0%）。ランプが20mA超の場合は ULN2803 ダーリントンドライバ経由で駆動

## ゲームステートマシン

```
        ARM           ボタン押下        正解
IDLE ────────→ ARMED ────────→ JUDGING ────────→ SHOWING_RESULT
 ↑                                  │                    │
 │              STOP/RESET          │ 不正解             │
 ←──────────────────────────────────┘   │                │
 ←──────────────────────────────────────┘ (全員不正解時)  │
 ←──────────────────────────────────────────────────────┘ RESET
```

| 状態 | 説明 | ボタン受付 |
|------|------|-----------|
| IDLE | 待機中 | 不可 |
| ARMED | 受付中 | 可 |
| JUDGING | 回答権者が回答中 | 可 (後続の押下を記録) |
| SHOWING_RESULT | 結果表示中 | 不可 |

### 回答権の移動

1. 最初に押したプレイヤーに回答権（ランプ点滅）
2. 不正解 → 回答権が次の押下者に移動（ランプ点滅が移る）
3. 全員不正解 → SHOWING_RESULT（全ランプ消灯）
4. 正解 → SHOWING_RESULT（正解者ランプフラッシュ）

## WebSocketプロトコル

### Server → Client (S2C)

| type | 説明 | 主要フィールド |
|------|------|---------------|
| `state` | 全状態同期 | game_state, players, press_order, answerer_id |
| `press` | ボタン押下 | player_id, order, timestamp_us, is_first |
| `judgment` | 正誤判定結果 | result, player_id, new_score, points_delta |
| `next_answerer` | 回答権移動 | player_id, answerer_idx |
| `no_answerer` | 全員不正解 | - |
| `reset` | リセット通知 | game_state |
| `player_update` | プレイヤー情報更新 | player_id, name, score |
| `jingle` | ジングル再生 | - |
| `countdown` | カウントダウン開始 | - |

### Client → Server (C2S)

| type | 説明 | 主要フィールド |
|------|------|---------------|
| `register` | クライアント種別登録 | client_type ("admin"/"display") |
| `set_name` | プレイヤー名変更 | player_id, name |
| `set_score` | スコア変更 | player_id, score |
| `arm` | 受付開始 | - |
| `stop` | 受付停止 | - |
| `judge` | 正誤判定 | result ("correct"/"incorrect") |
| `reset` | リセット | - |
| `settings` | ゲーム設定変更 | points_correct, points_incorrect |
| `jingle` | ジングル再生指示 | - |
| `countdown` | カウントダウン開始指示 | - |

## Wi-Fi動作モード

### STA モード（既存ネットワーク接続）
- `config.json` の `wifi_ssid` / `wifi_password` で接続
- 10秒以内に接続できなければAPモードにフォールバック
- 接続成功時にDiscord Webhookで起動通知

### AP モード（アクセスポイント）
- Pico自体がWi-Fiアクセスポイントになる
- デフォルト: SSID=`HayaoshiButton` / Password=`hayaoshi1234`
- IPアドレス: `192.168.4.1`
- インターネット接続不要で動作

## 設定ファイル (config.json)

```json
{
    "wifi_ssid": "YOUR_SSID",
    "wifi_password": "YOUR_PASSWORD",
    "num_players": 8,
    "points_correct": 10,
    "points_incorrect": -5,
    "ap_ssid": "HayaoshiButton",
    "ap_password": "hayaoshi1234",
    "discord_webhook": "https://discord.com/api/webhooks/..."
}
```

## 画面一覧

| URL | 用途 | 対象 |
|-----|------|------|
| `/` | プレイヤー表示画面 | プロジェクター/大型ディスプレイ |
| `/admin` | 管理画面 | 司会者 (PC/タブレット) |
| `/setup` | Wi-Fi設定画面 | 管理者 |

### 管理画面 (`/admin`)
- ARM/STOP/RESET/正解/不正解ボタン
- JINGLE (出題ジングル) / COUNTDOWN (10秒タイマー) ボタン
- プレイヤー名編集
- スコア加減算
- 押下順序・回答権表示
- ポイント設定

### 表示画面 (`/`)
- 回答権者の大型表示（名前 + 番号）
- 押下順序バー（時間差表示）
- スコアボード
- 正解/不正解アニメーション
- カウントダウン表示（残り3秒で赤色）
- 効果音再生 (ブラウザ側)

## セットアップ手順

### 1. MicroPythonファームウェア書き込み
1. BOOTSELボタンを押しながらUSB接続
2. `RPI-RP2` ドライブに Pico 2 W 用 MicroPython `.uf2` をコピー

### 2. mpremote インストール (PC側)
```
pip install mpremote
```

### 3. microdot ライブラリ配置
```
curl -sL https://raw.githubusercontent.com/miguelgrinberg/microdot/main/src/microdot/microdot.py -o lib/microdot/microdot.py
curl -sL https://raw.githubusercontent.com/miguelgrinberg/microdot/main/src/microdot/websocket.py -o lib/microdot/websocket.py
curl -sL https://raw.githubusercontent.com/miguelgrinberg/microdot/main/src/microdot/helpers.py -o lib/microdot/helpers.py
```

### 4. ファイル転送
```bash
# ディレクトリ作成
mpremote mkdir :lib
mpremote mkdir :lib/microdot
mpremote mkdir :www
mpremote mkdir :www/sounds

# ライブラリ
mpremote cp lib/microdot/__init__.py :lib/microdot/__init__.py
mpremote cp lib/microdot/microdot.py :lib/microdot/microdot.py
mpremote cp lib/microdot/websocket.py :lib/microdot/websocket.py
mpremote cp lib/microdot/helpers.py :lib/microdot/helpers.py

# アプリケーション
mpremote cp config.json :config.json
mpremote cp boot.py :boot.py
mpremote cp main.py :main.py
mpremote cp wifi.py :wifi.py
mpremote cp buttons.py :buttons.py
mpremote cp game.py :game.py
mpremote cp protocol.py :protocol.py
mpremote cp ws_manager.py :ws_manager.py

# Web UI
mpremote cp www/admin.html :www/admin.html
mpremote cp www/admin.js :www/admin.js
mpremote cp www/display.html :www/display.html
mpremote cp www/display.js :www/display.js
mpremote cp www/setup.html :www/setup.html
mpremote cp www/style.css :www/style.css

# 効果音 (各自用意)
mpremote cp www/sounds/p1.mp3 :www/sounds/p1.mp3
# ... (各ファイル)
```

### 5. config.json 編集
Wi-Fi SSIDとパスワードを設定

### 6. 起動
USB電源を接続すると自動起動。IPアドレスはDiscordまたは `/setup` 画面で確認。

### 一括転送（更新時）
コード変更後は以下のワンライナーで全ファイルを転送＋再起動:
```bash
mpremote cp main.py :main.py && mpremote cp game.py :game.py && mpremote cp buttons.py :buttons.py && mpremote cp wifi.py :wifi.py && mpremote cp protocol.py :protocol.py && mpremote cp ws_manager.py :ws_manager.py && mpremote cp www/admin.html :www/admin.html && mpremote cp www/admin.js :www/admin.js && mpremote cp www/display.html :www/display.html && mpremote cp www/display.js :www/display.js && mpremote cp www/setup.html :www/setup.html && mpremote cp www/style.css :www/style.css && mpremote reset
```

## 運用フロー

```
1. 電源ON → Wi-Fi接続 → Discord通知
2. /admin にアクセス
3. プレイヤー名を登録
4. [JINGLE] → 出題ジングル
5. [ARM]    → 受付開始
6. プレイヤーがボタン押下 → ランプ点灯(100%/20%) + 音
7. 回答 → [正解] or [不正解]
   - 正解: スコア加算、ランプフラッシュ、全待ちランプ消灯
   - 不正解: スコア減算、3秒待ち後に回答権が次の人へ
8. [RESET]  → 次の問題へ
9. 必要に応じて [COUNTDOWN] で10秒タイマー
```

## 今後の予定

- [ ] 効果音ファイルの作成・配置

## 技術的な注意点

- **asyncio.sleep_ms() は使用不可**: MicroPython 1.28 + Pico 2 W 環境では `asyncio.sleep(0.001)` を使用
- **microdot は mip 非対応**: GitHub から手動ダウンロードが必要
- **mpremote run vs ファイル転送**: `mpremote run` はデバッグ用、本番は `main.py` をPicoに転送してスタンドアロン実行
- **ルート定義順序**: microdot では `/ws` を `/<path:path>` より先に定義する必要がある
- **app.run() vs asyncio.run()**: ボタンポーリングとWebサーバーを並行実行するため `asyncio.run()` + `app.start_server()` を使用
- **ランプはPWM制御**: `machine.PWM` で輝度制御。duty_u16(0)=消灯、duty_u16(13000)=20%、duty_u16(65535)=100%
