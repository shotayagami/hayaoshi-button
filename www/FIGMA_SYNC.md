# Figma Sync Guide (Code Master)

このプロジェクトは「実装を正」としてFigmaを追従させます。

## Source of Truth

- デザイントークンの正: `www/style.css`
- Figma取り込み用トークン: `www/figma.tokens.json`
- 画面実装の正:
  - `www/admin.html`
  - `www/display.html`
  - `www/setup.html`

## Figma反映手順

1. `www/figma.tokens.json` をFigma Variables/Tokensへ取り込む
2. 下記コンポーネントをFigma Componentsとして作成する
   - `panel`
   - `button/base` + variants (`success`, `danger`, `warning`, `primary`, `purple`, `neutral`)
   - `chip`
   - `field` (label + input)
3. 3画面を実装準拠で再構成する
   - Admin: 情報密度を維持して余白・コントラストを統一
   - Display: 遠目視認優先で大サイズテキストを維持
   - Setup: 入力フォームと主要アクションを強調
4. 反映後、実装との差分確認は「色・余白・角丸」から優先的に行う

## Change Policy

- 新しい色・余白・角丸を追加する場合は、先に `www/style.css` を更新する
- Figma側で独自値を作らず、必ず既存トークンを参照する
- DOMの `id` は挙動依存があるため、見た目修正時も勝手に変更しない
