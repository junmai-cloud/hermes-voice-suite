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

Codex領域の技術実装は `voice_suite.technical_service.WorkerPool` と
`TechnicalOrchestrator` が担当する。Hermes内部の運用をこの経路へ強制的に
通さない。システム間連携、同期、共通知識パイプラインなどの主導権は
Codex側に置き、HermesはHermes側アダプターと実行結果だけを担当する。

HermesはVPS上のCodex CLIへ要望を投入できるが、任意の生コマンドを組み立てて
`codex exec --sandbox danger-full-access` を起動してはならない。投入は固定された
Codex worker境界を使い、実装は`workspace-write`、読み取り確認は`read-only`に
限定する。HermesがCodexを起動できることと、Hermesが権限や実装方針を決めて
よいことは同義ではない。

```text
Codex案件受付
  -> Codexが処理種別と所有境界を判定
  -> ローカルworkerのready枠を確認
  -> readyならローカルへ投入
  -> 全枠busy / unavailableならVPSへ退避
  -> 必要な場合だけ、Codex領域内の独立レビューを依頼
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

## 4. 検証境界

全処理の最終確認をVPS Codex auditorへ集約する旧方式は採用しない。
read-only sandboxからHermes内部とCodex内部の双方を正確に確認できないためである。
HermesはHermes領域、CodexはCodex領域をそれぞれ検証する。複数システムを
またぐ連携の設計・実装・検証主導はCodexが持ち、Hermesに設計判断を委ねない。

Codex auditorは、Codex所有タスクで独立レビューが必要な場合に限って使う。
Hermesの完了条件を一律にCodex auditorの結果へ依存させない。

独立レビューを行う場合、実装workerと監査workerを同一タスクで兼務させない。

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

共有知識基盤はCodexが能動的に設計・改善する。Hermesは利用者の要望を受け、
構造化した要求としてCodexへ渡す。Codexはスキーマ、同期、鮮度、重複排除、
障害時バックアップ、検証を所有し、Hermesは合意済みの契約を通じて読み書きする。
Google Calendarなど一つの外部認証が失効しても予定把握が全面停止しないよう、
最小限のデータを共有知識基盤へ一方向同期する復旧経路を設計する。

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
