# 東京 河川水位モニター — 自動化セットアップ

## 構成
```
.
├── collect_river_levels.py     # データ収集スクリプト
├── river_levels.csv            # 収集結果（Actionsが自動更新）
├── tokyo_river_dashboard.html  # ダッシュボード（自動でCSVをfetch）
└── .github/workflows/collect.yml  # 定期実行の設定
```

## セットアップ手順

1. **GitHubに新規リポジトリを作成**（public推奨。河川水位は公開情報なのでpublicで問題ありません。
   privateにする場合はGitHub Pagesの利用にPro/Team以上のプランが必要です）

2. 以下4ファイルをリポジトリ直下に配置してpush:
   - `collect_river_levels.py`
   - `river_levels.csv`（初回は空でも可。1回目のAction実行で生成されます）
   - `tokyo_river_dashboard.html`
   - `.github/workflows/collect.yml`

3. **リポジトリの Settings → Actions → General** で
   「Workflow permissions」を **Read and write permissions** に変更
   （Actionsがcsvをコミット・プッシュできるようにするため）

4. **リポジトリの Settings → Pages** で
   - Source: `Deploy from a branch`
   - Branch: `main` / `(root)`
   を選択して保存 → 数分後に `https://<ユーザー名>.github.io/<リポジトリ名>/tokyo_river_dashboard.html` で公開されます

5. 動作確認：
   - **Actions** タブ → `河川水位データ収集` ワークフロー → `Run workflow` で手動実行してみる
   - 成功すると `river_levels.csv` がコミットされる
   - GitHub Pages のURLでダッシュボードを開き、データが自動表示されることを確認

## 運用頻度について

初期設定は1日2回（JST 7時・19時）です。データ提供元（水文水質データベース）が
「自動収集は原則ご遠慮ください」と明記していることを踏まえた頻度なので、
むやみに増やさないことを推奨します。

## 403エラーが続く場合

GitHub ActionsのランナーもColab同様データセンターIPです。
連続して403になる場合は、収集頻度をさらに下げる（1日1回）か、
正式な配信サービス（水防災オープンデータ提供サービス）への切り替えを検討してください。
