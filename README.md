# 早押しボタンシステム

Raspberry Pi Pico 2 W を使用したイベント用早押しボタンシステム。
最大8人対応、ランプ内蔵ボタン、ブラウザベースの管理画面・表示画面を備える。

**司会者・利用者向けの操作マニュアル**: [ADMIN_MANUAL.md](ADMIN_MANUAL.md)

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
- 最大8人分の早押しボタン入力 + ランプ出力（人数は管理画面から変更可能）
- 司会者用物理ボタン7個（正解/不正解/リセット/ARM/STOP/ジングル/カウントダウン）
- ランプ制御 (PWM輝度):
  - 回答中=100%点灯
  - 回答待ち=約10%点滅
  - 受付中（押下可能）=約10%点灯
  - ペナルティ中/判定済み/IDLE=消灯
- ボタン入力は **GPIO割り込み駆動**（ポーリング取りこぼしを排除）
  - ハードチャタリング対策: 押下受理は「80ms 以上 HIGH 安定」後のみ（長押し中の擬似押下を防止）
  - 定期的なピン再初期化 + スタックLow自動復帰（環境耐性）
- DFPlayer Mini による SDカード音源再生（UART1経由、物理スピーカー接続用）

### ソフトウェア
- Wi-Fi: 既存ネットワーク接続(STA) / 自前アクセスポイント(AP) 自動切替
- WebSocketによるリアルタイム通信（クライアントごとに送信ワーカー + 5秒タイムアウト、半死クライアントで全体停止しない）
- ブラウザベースの管理画面・表示画面
- Discord Webhook による起動通知（STAモード時）
- プレイヤー名登録、カラー変更、スコア管理
- 着順記録 + 1位からの時間差表示（0.001秒単位）
- 回答権の自動移動（不正解時に次の押下者へ、3秒待ち後。複数正解モードでは即座に次へ）
- 回答権復活モード (4種類): 復活なし / 即座に復活 / 次の回答まで休み / 次の誤答まで休み
- 誤答ペナルティ（N問休み）
- 同時受付数制限（N人まで受付、既に判定済みの押下は枠から解放）
- **複数正解モード (一問多答)**: 正解最大数を設定し、到達するまで受付継続（同じプレイヤーの複数回回答も可能）
- 一括判定モード（書き問題用、着順ポイント対応、3状態判定: 正解/不正解/無回答）
- 判定ボタンの連打防止（サーバー側 500ms クールダウン + UI ロック）
- 全員不正解時もSTOPまで受付継続（ラウンド終了は正解 or STOP）
- 出題ジングル再生
- サーバー駆動10秒カウントダウンタイマー（フェードアウト対応）
- 音声再生先切替（管理画面/表示画面/DFPlayer を独立にオン・オフ可能）
- 音声ファイルのプリロード（低遅延再生）
- 管理画面からの音源アップロード
- 回答履歴テーブル（問題種別・着順・正誤・無回答・ペナルティ・スルー記録）
- リセットダイアログ（受付停止/ペナルティ解除/スコアリセット/問題番号加減算/全リセット）
  - 物理リセットボタンでダイアログの表示/非表示をトグル
- Wi-Fi設定画面 (`/setup`)
- 各種設定のconfig.json自動保存

## ディレクトリ構成

```
hayaoshi_button/
├── boot.py              # MicroPython起動設定 (150MHz)
├── main.py              # エントリーポイント (Wi-Fi接続、Webサーバー、全体統合)
├── wifi.py              # Wi-Fi接続管理 (STA/AP自動切替)
├── buttons.py           # GPIO制御 (ボタン入力エッジ検出、PWMランプ出力)
├── game.py              # ゲームステートマシン (状態管理、回答権、ペナルティ、一括判定)
├── protocol.py          # WebSocketメッセージプロトコル定義
├── ws_manager.py        # WebSocket接続管理、ブロードキャスト
├── dfplayer.py          # DFPlayer Mini UART制御 (効果音再生)
├── server.py            # (未使用: main.pyに統合済み)
├── config.json          # 設定ファイル (.gitignore対象)
├── config.json.example  # 設定ファイルテンプレート
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
    ├── display.js       # 表示画面ロジック
    ├── setup.html       # Wi-Fi設定画面
    ├── style.css        # 共通CSS変数
    └── sounds/          # 効果音ファイル (.gitignore対象、要配置)
        ├── p1.mp3 ~ p8.mp3   # プレイヤー別押下音
        ├── correct.mp3        # 正解音
        ├── incorrect.mp3      # 不正解音
        ├── jingle.mp3         # 出題ジングル
        ├── countdown.mp3      # カウントダウンBGM
        ├── countdown_end.mp3  # カウントダウン終了音
        └── batch_correct.mp3  # 一括判定正解音
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
 DFP TX  GP4  [6] │●          │ [35] ADC VREF
 DFP RX  GP5  [7] │●          │ [34] GP28
           GND  [8] │●          │ [33] GND
  P7ボタン GP6  [9] │●          │ [32] GP27 ← P6ボタン
  P8ボタン GP7 [10] │●          │ [31] GP26 ← P5ボタン
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
| GP0-GP3 | 1,2,4,5 | プレイヤー1-4 ボタン | INPUT (PULL_UP) |
| GP4 | 6 | DFPlayer TX | UART1 |
| GP5 | 7 | DFPlayer RX | UART1 |
| GP6-GP7 | 9,10 | プレイヤー7-8 ボタン | INPUT (PULL_UP) |
| GP8-GP15 | 11,12,14,15,16,17,19,20 | プレイヤー1-8 ランプ | PWM OUTPUT |
| GP16 | 21 | 正解ボタン | INPUT (PULL_UP) |
| GP17 | 22 | 不正解ボタン | INPUT (PULL_UP) |
| GP18 | 24 | リセットボタン | INPUT (PULL_UP) |
| GP19 | 25 | ARMボタン | INPUT (PULL_UP) |
| GP20 | 26 | STOPボタン | INPUT (PULL_UP) |
| GP21 | 27 | ジングルボタン | INPUT (PULL_UP) |
| GP22 | 29 | カウントダウンボタン | INPUT (PULL_UP) |
| GP26 | 31 | プレイヤー5 ボタン | INPUT (PULL_UP) |
| GP27 | 32 | プレイヤー6 ボタン | INPUT (PULL_UP) |

**ボタン配線**: 各ボタンは GPピン と GND の2本を接続（内部プルアップ使用、外付け抵抗不要）

**ランプ配線**: PWM輝度制御対応。ランプが20mA超の場合は ULN2803 ダーリントンドライバ経由で駆動

**ランプ輝度**: FULL=65535(100%), DIM=6500(約10%), OFF=0

## ゲームステートマシン

```
        ARM           ボタン押下        正解(単独正解モード) or max到達
IDLE ────────→ ARMED ────────→ JUDGING ─────────────────→ SHOWING_RESULT
 ↑                 ↑  │           │                              │
 │                 │  │ 一括判定  │  不正解 or 正解(継続) → 再ARM │
 │                 └──┼───────────┘→ 次の回答者へ                │
 │              STOP/RESET                                       │
 └──────────────────────────────────────────────────────────────┘
                                  RESET
```

| 状態 | 説明 | ボタン受付 |
|------|------|-----------|
| IDLE | 待機中 | 不可 |
| ARMED | 受付中 | 可 |
| JUDGING | 回答権者が回答中 | 可 (後続の押下を記録) |
| SHOWING_RESULT | 結果表示中 | 不可 |

### 受付の継続

**ARM から STOP までの受付窓**が開きっぱなしになる設計:
- 全員不正解 → 自動で再ARM（受付継続）
- 正解（複数正解モードで上限未達）→ 自動で再ARM（受付継続）
- 正解（単独正解モード or 複数正解上限到達）→ SHOWING_RESULT
- STOP → IDLE（受付停止）

### 回答権の移動

1. 最初に押したプレイヤーに回答権（ランプ100%点灯）、後続の押下者は10%点滅で待機
2. 不正解 → 不正解表示 → 回答権が次の押下者に移動（単独正解モードは3秒待ち、複数正解モードは即座）
3. 正解（単独正解モード or 上限到達）→ SHOWING_RESULT（正解者ランプフラッシュ、待ちランプ消灯）

判定済みの押下者は `max_accepts` の枠から解放され、残りのプレイヤーも空き枠の範囲で押下可能。

### 回答権復活モード (`revive_mode`)

不正解者が次に押下可能になるまでの待機ルール:

| 値 | 動作 |
|----|------|
| `none` | 復活なし（このラウンド中は押下不可） |
| `immediate` | 誤答と同時に即座に復活 |
| `next_answer` | 誰かが次に判定されたら復活（正誤問わず） |
| `next_wrong` | 誰かが次に誤答したら復活 |

### 複数正解モード（一問多答）

`max_correct > 1` で有効化。

- ARM 前に「正解最大数」を設定
- 各正解で `correct_count++`、`max_correct` 到達前は受付継続
- 正解者は `pressed_set` から discard され、再押下可能（正解数 > プレイヤー数も対応）
- 管理画面 / 表示画面のヘッダーに残り正解数（`N/M`）を表示
- 誤答時の3秒アニメ待ちはスキップ（テンポ重視）

### 一括判定モード（書き問題用）
- ARMED/JUDGING状態で正解/不正解ボタンが使用可能
- 各プレイヤー行に「正」「無」の2チェックボックス
- 判定:
  - 正チェック → 正解 (`batch_points[rank]` or `points_correct`)
  - 無チェック or 未押下 → 無回答 (`batch_noanswer`, 着順モード時)
  - いずれもチェックなし + 押下あり → 不正解 (`batch_incorrect` or `points_incorrect` + ペナルティ)
- 正解ボタン/不正解ボタンは効果音のみ異なる（判定結果は同一）
- 着順ポイント使用時: 押下順 + 未押下正解者の順にポイント適用

## WebSocketプロトコル

### Server → Client (S2C)

| type | 説明 | 主要フィールド |
|------|------|---------------|
| `state` | 全状態同期 | game_state, players, press_order, answerer_id, colors, revive_mode, max_correct, correct_count, batch_mode, batch_incorrect, batch_noanswer 等 |
| `press` | ボタン押下 | player_id, order, timestamp_us, is_first |
| `judgment` | 正誤判定結果 | result, player_id, new_score, points_delta, correct_count, round_continues (bool, 複数正解で継続時) |
| `batch_result` | 一括判定結果 | results[] (result: "correct"/"incorrect"/"noanswer"), sound |
| `next_answerer` | 回答権移動 | player_id, answerer_idx |
| `no_answerer` | 全員不正解 or 正解で再ARM | revival (bool, 常にTrueで送信=受付継続) |
| `reset` | リセット通知 | game_state |
| `player_update` | プレイヤー情報更新 | player_id, name, score |
| `jingle` | ジングル再生 | - |
| `countdown` | カウントダウン開始 | value |
| `countdown_tick` | カウントダウン毎秒 | value |
| `colors_update` | カラー変更通知 | colors[] |
| `show_reset_dialog` | リセットダイアログの表示トグル | - |
| `audio_mode` | 音声再生先変更 | display (bool) |

### Client → Server (C2S)

| type | 説明 | 主要フィールド |
|------|------|---------------|
| `register` | クライアント種別登録 | client_type ("admin"/"display") |
| `set_name` | プレイヤー名変更 | player_id, name |
| `set_score` | スコア変更 | player_id, score |
| `set_colors` | カラー変更 | colors[] |
| `arm` | 受付開始 | - |
| `stop` | 受付停止 | - |
| `judge` | 正誤判定 | result ("correct"/"incorrect") |
| `batch_judge` | 一括判定 | correct_ids[], noanswer_ids[], sound |
| `reset` | リセット | - |
| `clear_penalty` | ペナルティ一括解除 | - |
| `reset_scores` | スコアリセット | - |
| `reset_round` | 問題番号リセット（0に戻す） | - |
| `set_round` | 問題番号を任意値に設定 | value (int, 0以上) |
| `settings` | ゲーム設定変更 | (下記参照) |
| `jingle` | ジングル再生指示 | - |
| `countdown` | カウントダウン開始指示 | - |
| `audio_mode` | 音声再生先変更 | display (bool), dfplayer (bool) |

### settings メッセージのフィールド

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `num_players` | int | プレイヤー人数 (2-8) |
| `points_correct` | int | 正解ポイント |
| `points_incorrect` | int | 不正解ポイント |
| `revive_mode` | string | 不正解時の復活ルール (`none` / `immediate` / `next_answer` / `next_wrong`) |
| `revival` | bool | (レガシー) true→`next_wrong`, false→`none` に自動変換 |
| `max_accepts` | int | 同時受付数上限 (0=無制限, N=N人まで受付) |
| `max_correct` | int | 正解最大数 (1=単独正解モード, N>1=複数正解モード) |
| `jingle_auto_arm` | bool | ジングル再生時に自動ARM |
| `countdown_auto_stop` | bool | カウントダウン終了時に自動STOP |
| `penalty_rounds` | int | 誤答ペナルティ (0=無効, N=N問休み) |
| `batch_mode` | bool | 一括判定モード |
| `batch_use_order` | bool | 着順ポイントを使用 |
| `batch_points` | int[] | 着順別ポイント配列 |
| `batch_incorrect` | int | 一括判定の不正解ポイント（着順モード時のみ） |
| `batch_noanswer` | int | 一括判定の無回答ポイント（着順モード時のみ） |

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

`config.json.example` をコピーして作成。ゲーム設定は管理画面から変更すると自動保存される。

```json
{
    "wifi_ssid": "YOUR_SSID",
    "wifi_password": "YOUR_PASSWORD",
    "num_players": 8,
    "points_correct": 10,
    "points_incorrect": -5,
    "ap_ssid": "HayaoshiButton",
    "ap_password": "hayaoshi1234",
    "discord_webhook": "",
    "colors": ["#e63946", "#457b9d", "#2a9d8f", "#e9c46a", "#f4a261", "#264653", "#6a4c93", "#1982c4"],
    "revive_mode": "none",
    "max_accepts": 0,
    "max_correct": 1,
    "jingle_auto_arm": false,
    "countdown_auto_stop": false,
    "penalty_rounds": 0,
    "batch_mode": false,
    "batch_use_order": true,
    "batch_points": [10, 8, 6, 4, 3, 2, 1, 1],
    "batch_incorrect": -5,
    "batch_noanswer": 0
}
```

※ 旧設定の `"revival": true/false` は起動時に自動で `revive_mode` に変換されます。

## 画面一覧

| URL | 用途 | 対象 |
|-----|------|------|
| `/` | プレイヤー表示画面 | プロジェクター/大型ディスプレイ |
| `/admin` | 管理画面 | 司会者 (PC/タブレット) |
| `/setup` | Wi-Fi設定画面 | 管理者 |

### 管理画面 (`/admin`)
- 状態バー: 現在の状態 / 問題番号 / 複数正解モード時は残り正解数 (`N/M`)
- 操作ボタン: JINGLE / COUNTDOWN / ARM / STOP / RESET
- 判定ボタン: 正解 / 不正解（500ms クールダウンで連打防止）
- プレイヤー管理: 名前編集、カラー変更、スコア加減算
- 押下順序・回答権表示
- 一括判定モード時: 「正」「無」の2チェックボックス／行
- 設定:
  - プレイヤー人数、正解/不正解ポイント
  - 不正解時の復活ルール（ドロップダウン4択）
  - 同時受付数、ペナルティN問休み
  - ジングル/カウントダウン自動連動
  - 複数正解モード（ON/OFF チェックボックス + 正解最大数）
  - 一括判定モード（ON + 着順ポイント + 不正解/無回答ポイント）
- 音源管理: ファイルアップロード
- 回答履歴テーブル（問題種別・着順・正誤・無回答・ペナルティ・スルー）
- 音声再生先切替（管理画面/表示画面/DFPlayer を独立）
- リセットダイアログ（受付停止/ペナルティ解除/スコアリセット/問題番号加減算/全リセット）

### 表示画面 (`/`)
- ヘッダー: 状態ラベル + 複数正解モード時は残り正解数 (`N/M`)
- 回答権者の大型表示（名前 + 番号、背景色に応じた自動文字色切替）
- 押下順序バー（時間差 0.001秒単位表示）
- スコアボード（ペナルティ中はグレーアウト表示）
- 正解/不正解アニメーション（正解はリセットまで表示維持）
- 一括判定結果の一覧表示（正解○/不正解×/無回答—の3状態）
- カウントダウン表示（残り3秒で赤色、0でTIME UP!）
- 効果音再生（プリロード済み、低遅延）
- 音声有効化オーバーレイ

## 効果音一覧

| ファイル名 | 用途 | 再生タイミング |
|-----------|------|--------------|
| `p1.mp3` ~ `p8.mp3` | プレイヤー別押下音 | ボタン押下時 |
| `correct.mp3` | 正解音 | 正解判定時 |
| `incorrect.mp3` | 不正解音 | 不正解判定時 |
| `jingle.mp3` | 出題ジングル | ジングルボタン/JINGLE押下時 |
| `countdown.mp3` | カウントダウンBGM | カウントダウン中 |
| `countdown_end.mp3` | カウントダウン終了音 | カウントダウン0到達時 |
| `batch_correct.mp3` | 一括判定正解音 | 一括判定で正解ボタン押下時 |

管理画面の「音源管理」から各音源をアップロード可能（200KB以下）。

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
mpremote cp dfplayer.py :dfplayer.py

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

### 5. config.json 作成・編集

```bash
cp config.json.example config.json
```

`config.json` を編集してWi-Fi SSID・パスワード等を設定。
※ `config.json` は `.gitignore` で管理対象外（秘密情報を含むため）

### 6. 起動
USB電源を接続すると自動起動。IPアドレスはDiscordまたは `/setup` 画面で確認。

### 一括転送（更新時）
コード変更後は以下のワンライナーで全ファイルを転送＋再起動:

```bash
mpremote cp main.py :main.py && mpremote cp game.py :game.py && mpremote cp buttons.py :buttons.py && mpremote cp wifi.py :wifi.py && mpremote cp protocol.py :protocol.py && mpremote cp ws_manager.py :ws_manager.py && mpremote cp dfplayer.py :dfplayer.py && mpremote cp www/admin.html :www/admin.html && mpremote cp www/admin.js :www/admin.js && mpremote cp www/display.html :www/display.html && mpremote cp www/display.js :www/display.js && mpremote cp www/setup.html :www/setup.html && mpremote cp www/style.css :www/style.css && mpremote reset
```

## 運用フロー

### 早押しモード

```
1. 電源ON → Wi-Fi接続 → Discord通知
2. /admin にアクセス
3. プレイヤー名・カラーを登録
4. [JINGLE] → 出題ジングル（自動ARM設定時はそのまま受付開始）
5. [ARM]    → 受付開始（問題番号+1）
6. プレイヤーがボタン押下 → ランプ点灯(100%/10%) + 押下音
7. 回答 → [正解] or [不正解]
   - 正解: スコア加算、ランプフラッシュ、待ちランプ消灯
   - 不正解: スコア減算、3秒待ち後に回答権が次の人へ
8. [RESET]  → リセットダイアログ → 次の問題へ
9. 必要に応じて [COUNTDOWN] で10秒タイマー
```

### 一括判定モード（書き問題）

```
1. 設定で「一括判定モード」にチェック
2. [ARM] → 受付開始
3. 全員がボタンを押す（着順記録）/ またはボタンなしで回答
4. 管理画面で正解者にチェック
5. [正解] → チェック者に正解ポイント、未チェック者に不正解ポイント（batch_correct音）
   [不正解] → 同上（incorrect音）
```

## 回答履歴テーブル

管理画面に問題ごとの回答履歴が表示される。

| 問 | 種別 | Player 1 | Player 2 | Player 3 |
|----|------|----------|----------|----------|
| 1 | 早押 | 1位 ○ +10 | 2位 × -5 | - |
| 2 | 早押 | スルー |||
| 3 | 書正 | ○ +1 | × -1 | ○ +1 |
| 4 | 書着 | 2位 ○ +8 | × -1 | 1位 ○ +10 |
| 5 | 書着 | 1位 ○ +10 | — 0 | × -5 |

記号の意味:

- **○**: 正解
- **×**: 不正解
- **—**: 無回答（着順一括判定モード、押下なしまたは「無」チェック）
- **早押**: 早押しモード
- **書正**: 書き問題 正誤判定のみ
- **書着**: 書き問題 着順判定付き
- **スルー**: 誰もボタンを押さずにリセット
- 全リセットで履歴クリア

## 技術的な注意点

- **asyncio.sleep_ms() は使用不可**: MicroPython 1.28 + Pico 2 W 環境では `asyncio.sleep(0.001)` を使用
- **microdot は mip 非対応**: GitHub から手動ダウンロードが必要
- **mpremote run vs ファイル転送**: `mpremote run` はデバッグ用、本番は `main.py` をPicoに転送してスタンドアロン実行
- **ルート定義順序**: microdot では `/ws` を `/<path:path>` より先に定義する必要がある
- **app.run() vs asyncio.run()**: ボタンポーリング + Webサーバー + 診断ループを並行実行するため `asyncio.run()` + `app.start_server()` を使用
- **ランプはPWM制御**: `machine.PWM` で輝度制御。duty_u16(0)=消灯、duty_u16(6500)=約10%、duty_u16(65535)=100%
- **ファイル配信**: 8KB以下はメモリ読み込み、8KB超は2KBチャンクでストリーミング配信（メモリ節約）
- **音声プリロード**: ページ読み込み時に全音声ファイルをブラウザメモリにキャッシュ（Blob URL）
- **ボタン入力はGPIO割り込み駆動**: `Pin.irq(IRQ_FALLING)` + `micropython.schedule` でISR外に本処理を委譲。ポーリング取りこぼしを根本回避
- **チャタリング対策**: IRQ受理後は「ピンが80ms以上HIGH安定」した後のみ次押下を受理。長押し中の擬似押下を完全ブロック
- **`time.ticks_us()` のラップ対策**: RP2の2^30 (~18分) wrap + `ticks_diff` 符号付きに対応。デバウンス判定で負の diff は「十分昔」として受理
- **WebSocket送信はキュー駆動**: クライアントごとに送信ワーカーを生成、5秒タイムアウトで半死クライアントを切り離す。`broadcast()` はキューに積むだけで非ブロック
- **判定クールダウン**: サーバー側500msの全判定クールダウン + 管理画面UIの同期ロック。物理ボタンチャタリングと UI ダブルクリックを両方防止
- **一問多答モードの正解者再受付**: 正解時に `pressed_set.discard(answerer_id)` で解放、`max_correct > プレイヤー数`でも成立
