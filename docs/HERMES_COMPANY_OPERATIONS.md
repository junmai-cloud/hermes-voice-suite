# Hermes社 / Codex社 運用設計

更新: 2026-08-26

## 1. 基本構造

HermesとCodexは、同一組織内の上下レイヤーではなく、責任範囲の異なる別会社として扱う。

```text
純米さん（両社を横断する代表・最終判断者）
│
├── Hermes社
│   ├── 総務
│   ├── 財務
│   ├── クリエイティブ研究室
│   └── Hermes監査役
│
└── Codex社
    ├── 企画
    ├── 開発
    ├── コード・システム開発
    └── Codex監査役

共有面: Notion / 限定共有フォルダ / Discord会議
```

会社間で共有するのは、知識・仕様・依頼・成果物・監査結果である。各社の内部ログ、認証情報、セッションDB、実行中SQLite、監査途中データ、内部権限は共有しない。

## 2. 実行場所

### VPS: 常時稼働の司令塔

- Hermes Gateway
- Discord受付・会議
- Notion連携
- 軽量な調査・自動化
- ジョブ受付・分類・監査結果の集約
- ローカルワーカーへの遠隔投入

### ローカルPC: 必要時に増設する専門ワーカー

- 写真・動画・音声・大容量ファイル
- Photoshop / LightroomなどGUI処理
- GPU処理
- ローカルデータに依存する案件
- 深夜など、純米さんがローカルを起動している時間の並列処理

VPSは常時稼働し、ローカルはHeartbeatで参加・離脱する。ローカルが不在でも、VPSで処理できる案件はVPSへ自動退避する。

## 3. Workerルーティング

技術実装は `voice_suite.technical_service.WorkerPool` と `TechnicalOrchestrator` が担当する。

```text
案件受付
  -> Hermesが処理種別を判定
  -> ローカルworkerのready枠を確認
  -> readyならローカルへ投入
  -> 全枠busy / unavailableならVPSへ退避
  -> 実装完了後、独立したVPS auditorへ監査依頼
```

1つのタスクは、同時に複数workerへ投入しない。投入後は担当workerに固定し、結果回収・キャンセルも同じworkerへ送る。これにより、同じ作業ブランチをローカルとVPSが同時編集する事故を防ぐ。

### ローカルworker枠

```bash
CODEX_LOCAL_WORKER_SLOTS=2
```

既定値は1。ローカルPCのRAM、GPU、Whisper常駐状況を確認して調整する。枠数を増やしても、監査権限や本番反映権限は増えない。

### 自動退避の制限

自動切換えの対象は実行場所だけである。次の判断は自動退避しない。

- 本番反映
- 外部送信
- 削除
- 課金
- セキュリティ変更
- Gateway / VPS再起動
- Bot TokenやOAuthの変更

## 4. 監査境界

Hermes社とCodex社には、それぞれ独立した監査役を置く。実装workerと監査workerを同一タスクで兼務させない。

Codex auditorの必須条件:

- `--role auditor`
- `--sandbox read-only`
- rootfs read-only
- `no-new-privileges:true`
- `Privileged=false`
- 実装workerと異なる監査経路
- 認証付き `/health` が `state=ready`

監査役に `danger-full-access` が見えた場合は、指示書の問題ではなく構成差分として扱い、合格扱いにしない。

## 5. 状態と共有

- Notion: 両社で共有する長期知識、仕様、意思決定、成果物索引
- 技術台帳SQLite: Hermesの実行状態と監査証跡。秘密・音声・生ログは保存しない
- VPS共有フォルダ: 会社間で明示的に共有する仕様・成果物・引き継ぎのみ
- 各社の内部領域: セッション、認証、内部ログ、監査途中データを保持
- Discord: 純米さんとの会議・判断・報告。高リスク操作は会議中でも対象確認と監査を省略しない

## 6. ローカルworkerの起動条件

VPSからローカルPCへ直接公開ポートを開けない。WireGuard、Tailscale、SSH reverse tunnelなど、認証された経路の上にworker HTTPサービスを置く。worker tokenは環境変数だけで渡し、DiscordやNotionへ表示しない。

ローカル側の例:

```bash
voice-suite tech worker \
  --worker-id local-codex-1 \
  --role implementer \
  --host 127.0.0.1 \
  --port 8765 \
  --repo C:/AI/APP/hermes-voice-suite \
  --sandbox workspace-write
```

VPS側のHermesには、保護経路上のURLを `CODEX_LOCAL_WORKER_URL` として設定する。ローカルworkerがhealthで `ready` を返す間だけ、Dispatcherがローカルへ投入する。Heartbeatが切れたらVPSへ退避する。

監査workerはローカル実装workerと兼務しない。ローカルが実装しても、監査はVPSの独立auditorへ送る。

## 7. 現在の実装状態

- ローカル優先、VPSフォールバック: 実装済み
- 複数ローカルworker枠: `WorkerPool` 実装済み
- 1タスク1worker固定: 実装済み
- 独立監査の厳格JSON契約: 既存実装
- VPS auditor実体: read-only構成へ対象コンテナを再作成済み
- root所有Composeファイルの永続修正: rootコンソール作業が必要で保留

## 8. 完了条件

次の全てが揃うまで、会社構成の本番運用を完了扱いにしない。

1. ローカルworkerのHeartbeatと容量情報
2. VPS / ローカルの実ジョブ投入テスト
3. 同一タスク二重投入防止テスト
4. auditorのread-only実体監査
5. Notion・共有フォルダの境界確認
6. Gateway、worker、auditorの個別ヘルスチェック
7. 失敗時の再試行・保留・ロールバック確認
8. root所有Compose定義の安全設定への永続反映
