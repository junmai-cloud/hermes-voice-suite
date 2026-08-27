# 純米サーバー Hermes / Codex 分離構成

更新: 2026-08-27 JST

## 先に結論

- 既存の Hermes Bot は、VPS ホスト側の `hermes-gateway.service` を経由する旧経路である。
- JUNMAI の Codex Discord Bot は、その経路を使わない。専用の `codex-discord-bot` から専用の `codex-chat-worker` へ、`prompt` だけを送る。
- JUNMAI の通常のチャット応答・音声応答に、Hermes の outbound audit、`codex-auditor`、technical task、technical ledger を通さない。
- この文書の「定義されている」と「VPS で稼働している」は別である。本番切替が未実施なら、ローカル実装だけで Bot が復旧したとは扱わない。

## 目標構成図

```mermaid
flowchart TB
    D[Discord 純米サーバー\nテキスト / ボイス]
    D -->|Hermes Bot の既存経路| G
    D -->|JUNMAI / Codex Bot の分離経路| B

    subgraph V[VPS]
        G[Hermes Gateway\nVPSホスト側の systemd --user\nhermes-gateway.service\nhermes_cli.main gateway run]
        S[Hermes状態・技術台帳\n秘密情報は保存しない]

        subgraph C[Docker Compose: hermes-voice-suite]
            W[codex-worker\n実装担当\n127.0.0.1:8765\nworkspace-write]
            A[codex-auditor\n独立監査担当\n127.0.0.1:8766\n設計上は read-only]
            B[codex-discord-bot\n専用 Discord アプリ\nhost network]
            C[codex-chat-worker\nprompt-only\n127.0.0.1:8777\nread-only Codex]
        end

        G --> S
        G -->|内部HTTP| W
        G -->|別経路で監査依頼| A
        B -->|POST /chat の prompt のみ| C
    end

    W -->|実装| R[作業ブランチ / worktree]
    A -->|監査| R
    G -->|最終報告・TTS| D
    B -->|Discord 応答・音声| D
```

## 経路ごとの責務

| 経路 | Discord 接続 | Codex 呼出し | Hermes 監査 | 変更操作 |
| --- | --- | --- | --- | --- |
| Hermes Bot | `hermes-gateway.service` | technical worker / Hermes 処理 | あり得る | Hermes の技術タスク契約に従う |
| JUNMAI / Codex Bot | `codex-discord-bot` | `codex-chat-worker` の prompt-only API | なし | Chat Worker は固定 `--sandbox read-only` |

JUNMAI / Codex Bot の認証情報は `CODEX_DISCORD_BOT_TOKEN` と
`CODEX_CHAT_WORKER_TOKEN` を使う。Hermes の `DISCORD_BOT_TOKEN`、技術用の
`CODEX_WORKER_TOKEN` と共有しない。特に同じ Discord Bot Token を Hermes と
Codex Bot が同時に使用してはならない。

`codex-chat-worker` の API は `POST /chat` に JSON の `{"prompt": "..."}`
だけを受け付ける。`task`、監査、ブランチ、サンドボックスをリクエストから
指定できない。実際の Codex CLI 呼出しもソース内で `--sandbox read-only` に
固定される。

## 事実と注意点

- 2026-08-04 の実測では、既存の Discord と音声を担当する Hermes Gateway は Docker コンテナではなく、VPS ホスト側の `hermes-gateway.service` で動作していた。
- Docker で稼働しているのは `hermes-voice-suite-codex-worker-1` と `hermes-voice-suite-codex-auditor-1`。ポートは VPS 内部の `127.0.0.1:8765` と `127.0.0.1:8766` に限定される。
- `compose.yaml` には `hermes-gateway` と分離経路の `codex-discord-bot` / `codex-chat-worker` が定義されているが、定義だけでは現在稼働中とは言えない。VPS の `docker ps` とログで個別に確認する。
- Compose の設計上、auditor は read-only である。実測コマンドラインに `--sandbox danger-full-access` が出る場合は、構成差分として監査・是正対象にする。合格扱いにしない。
- 既存 Hermes Gateway のログで Discord adapter が監査を呼び出している場合、それは旧 Hermes 経路の事実であり、JUNMAI / Codex Bot の分離経路へ持ち込まない。

## JUNMAI / Codex Bot の起動確認

本番操作の前に、対象をこの 2 サービスだけに限定して確認する。Hermes Gateway、
technical worker、auditor の再起動はこの確認には含めない。

```bash
docker compose ps codex-chat-worker codex-discord-bot
docker compose logs --tail 100 codex-chat-worker codex-discord-bot
curl -fsS -H "Authorization: Bearer ${CODEX_CHAT_WORKER_TOKEN}" \\
  http://127.0.0.1:8777/health
```

トークン値や `.env` の内容は出力しない。`health` は認証済みであることと
`state=ready` を確認するためだけに使う。Discord 側は Bot のログイン、Gateway
Ready、voice channel 接続、音声受信、TTS 再生を個別に確認する。

## 再起動時の判断

1. まず読み取り専用で実体を確認する。`docker ps` だけで Gateway コンテナが存在しないなら、Docker の Gateway を再起動対象にしない。
2. 現行のホスト側 Gateway を再起動する場合だけ、root ユーザーの systemd ユーザーサービスとして次を使う。

```bash
systemctl --user restart hermes-gateway.service
systemctl --user show hermes-gateway.service -p ActiveState -p SubState -p MainPID
```

3. `docker restart` や `docker compose restart` を無差別に実行しない。worker／auditor の再起動は、対象サービスと影響範囲を確定した技術タスクで行う。
4. ホスト側 Gateway と Docker 側 Gateway を同じ Discord Bot Token で同時起動しない。二重接続・競合の原因になる。
5. コード、設定、音声経路、ルーティング、再起動、デプロイは、テストと独立監査が終わるまで完了扱いにしない。デプロイや停止を伴う場合は利用者の明示承認も必要。

## Hermes 再発防止ガードレール

再起動や障害対応では、次の順番を崩さない。

1. 依頼を受けたら、「何を直すか」「どこで動いているか」「停止・切断の影響」を短く宣言する。
2. 実行前に `docker ps`、対象プロセス、サービス名、実行ユーザーを読み取り専用で照合する。
3. 構成が食い違う、確信がない、コンテナとホストを判別できない場合は、コマンドを出さず `BLOCKED` にして調査へ戻る。
4. 操作は 1 対象・1 コマンドに限定し、Docker 全体、Compose 全体、VPS 全体を再起動しない。
5. 実行前に対象、対象外、想定影響、ロールバックを提示し、重大操作は人の明示承認を待つ。
6. 実行後に `ActiveState` / `SubState` / `MainPID`、対象コンテナ、直近ログ、Discord 接続を確認してから報告する。
7. 「コマンドを実行した」だけで「正常」と言わない。確認結果が不足する場合は未完了または `BLOCKED` と報告する。
8. コード、設定、音声経路、ルーティング、再起動、デプロイは、テストと独立監査が終わるまで完了扱いにしない。

次のどれか 1 つでも該当したら停止する。

- 操作対象が特定できない
- Bot Token の二重起動のおそれがある
- 監査証拠が不足している
- 想定外のログ、権限不一致、環境差分がある

## Discord に貼る短縮版

```text
【Hermes 現行システム構成｜2026-08-04 実測】

Discord 純米サーバー（テキスト／ボイス）
  │ メッセージ・音声
  ▼
VPS ホスト側
  └─ hermes-gateway.service（systemd --user）
     └─ /usr/local/lib/hermes-agent/venv/bin/python
        └─ hermes_cli.main gateway run
           ├─ Discord接続、音声受信、STT、TTS、Hermes処理
           ├─ http://127.0.0.1:8765
           │  └─ Docker codex-worker（実装担当／workspace-write）
           └─ http://127.0.0.1:8766
              └─ Docker codex-auditor（独立監査／設計上read-only）

【重要】
・現在の docker ps で確認できるのは worker と auditor。Gatewayコンテナは確認されていない。
・compose.yaml に Gateway の定義があっても、現在稼働中とは限らない。
・再起動前に実体を確認し、対象だけを操作する。
・ホスト側 Gateway と Docker側 Gateway を同じBot Tokenで同時起動しない。
・auditor に danger-full-access が見えたら、read-only設計との構成差分として監査・是正する。

【現行ホストGatewayの確認・再起動】
systemctl --user restart hermes-gateway.service
systemctl --user show hermes-gateway.service -p ActiveState -p SubState -p MainPID
```
