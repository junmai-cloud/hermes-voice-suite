# Hermes × Codex 技術運用ガイド

この機能は、Hermesが会話の窓口になり、Codexがコード変更の技術判断を担当するための共通ルールです。

## まず覚えること

- Hermesは「受付」「実行」「短い報告」を担当します。
- ローカルPCが起動していて利用可能なら、重い実装をローカルCodexへ送ります。
- ローカルPCが使えなければ、VPS上のCodexへ自動的に切り替えます。
- コード、設定、音声処理、接続経路、再起動、デプロイ、認証変更は、VPS Codexの監査が終わるまで完了扱いにしません。
- 台帳には作業の事実だけを保存し、音声本文、文字起こし本文、APIキーなどは保存しません。

つまり、音声で「直して」と伝えた後にHermesが「完了」と言えるのは、実装だけでなく、テストと独立した監査まで終わった場合です。

## 作業の流れ

```text
音声・文字の依頼
      ↓
Hermesが技術作業として登録
      ↓
ローカルPCのCodexを確認
      ├─ 利用可能 → local-codexが実装
      └─ 利用不可 → vps-codexが実装
      ↓
Hermesが変更点・テスト・稼働確認を記録
      ↓
VPS Codexが監査
      ├─ PASS / PASS_WITH_WARNINGS → 承認可能
      ├─ FAIL → 修正して再検証
      └─ BLOCKED → 人の判断または環境復旧が必要
```

不合格の場合、監査役は作業を先へ流さず、`improvement_plan`に改善案を返します。JUNMAI BOTはその内容を短く音声で伝えます。

> 「監査で問題が見つかりました。テストが1件失敗しています。改善案は、依存関係を固定して再テストすることです。これで修正しますか？」

利用者が了承した場合だけ、`NEEDS_FIX`から修正作業へ戻します。利用者が了承しなければ、変更は反映しません。

作業IDごとに実装担当は1つだけです。ローカルPCとVPSが同じ作業を同時に編集することはありません。コード変更は作業ブランチまたはWorktreeで行い、本番を直接編集しない運用にします。

## 監査の強さ

ファイルを読む、ログを見る、プロセスを確認する、変更なしのテストを実行する、といった読み取り専用の操作は、その場のHermes確認で完了できます。

次の操作は、必ず監査台帳に入り、Codex監査が必要です。

- コード・設定・依存パッケージの変更
- 音声ストリーミング方式やGatewayの変更
- ルーティング変更、サービス再起動、デプロイ
- 認証、権限、ネットワークの変更
- 削除や本番データ変更

削除、秘密情報、公開設定、本番データ、デプロイのような重大操作は、監査に加えて利用者の明示承認が必要です。

## 台帳の状態

| 状態 | 利用者向けの意味 |
| --- | --- |
| `REQUESTED` | 依頼を受け付けた |
| `PLANNED` | 作業内容と戻し方を整理した |
| `IMPLEMENTING` | Codexが実装中 |
| `VERIFYING` | テスト結果を添えて監査中 |
| `APPROVED` | 監査合格。反映可能 |
| `DEPLOYED` | 承認後に反映済み |
| `NEEDS_FIX` | 問題があり、修正が必要 |
| `BLOCKED` | 監査担当・環境・承認などが不足 |
| `CANCELLED` | 作業を取り消した |

監査結果は次の4種類だけです。

- `PASS`: 問題なく反映可能
- `PASS_WITH_WARNINGS`: 注意点はあるが、監査上は反映可能
- `FAIL`: 修正が必要
- `BLOCKED`: 判断に必要な情報や環境が足りない

証拠のない合格、途中で切れた出力、意味が曖昧な文章は合格になりません。

## CLIでの確認

インストール後は `voice-suite tech` または `voice-tech` を使います。

### 作業を登録する

```bash
voice-suite tech create \
  --summary "音声ストリーミングの処理を改善" \
  --operation audio_pipeline_change \
  --repo /path/to/hermes-voice-suite \
  --branch codex/audio-streaming
```

表示された `task_id` を、その後の実装・監査で使います。

### 実装を依頼する

```bash
voice-suite tech dispatch TECH_TASK_ID \
  --prompt "この作業IDの範囲だけを実装し、テスト結果を出力してください"
```

通常はローカルPCが利用可能ならローカル優先です。VPSだけで実装したい場合は `--no-local` を付けます。

### 監査の証拠を送る

```bash
voice-suite tech submit-audit TECH_TASK_ID \
  --command "pytest -q" \
  --expected "全テスト成功" \
  --actual "全テスト成功" \
  --exit-code 0 \
  --changed-file src/voice_suite/streaming.py \
  --test "pytest -q: passed" \
  --health "Gateway health: OK" \
  --prompt "差分、テスト、稼働状態、ロールバック方法を監査し、指定JSONだけを返してください"
```

VPS Codexの返答は、次のようなJSONだけにします。

```json
{
  "status": "PASS",
  "rationale": "変更差分とテスト結果を確認した",
  "evidence": ["pytest -q: passed", "Gateway health: OK"],
  "issues": [],
  "improvement_plan": [],
  "production_ready": true,
  "rollback_plan": "作業ブランチをrevertしてサービスを再起動する"
}
```

```bash
voice-suite tech audit TECH_TASK_ID --result-file audit.json
voice-suite tech show TECH_TASK_ID
```

`APPROVED`になるまで、Hermesは「作業は完了しました」と報告できません。
不合格の場合のCLI結果には、JUNMAI BOTがそのまま読み上げられる`voice_message`も含まれます。

## 重大操作の承認

デプロイ、削除、認証・権限変更などは、監査に合格しても自動実行されません。Hermesが影響範囲を音声で説明し、利用者が明示的に了承した後に、次を実行します。

```bash
voice-suite tech confirm TECH_TASK_ID
voice-suite tech complete TECH_TASK_ID
```

実装開始時に明示承認も同時に渡す場合は、`dispatch` に `--confirm` を付けられます。通常のコード変更には不要です。

## ローカルPCとVPSの接続

ローカルPC側では、リポジトリを直接公開せず、認証付きのワーカーを起動します。

```bash
voice-suite tech worker \
  --worker-id local-codex \
  --host 0.0.0.0 \
  --port 8765 \
  --repo /path/to/hermes-voice-suite \
  --token "$CODEX_WORKER_TOKEN"
```

実際にはVPNやWireGuardなど、VPSからローカルPCへ安全に到達できる経路だけで公開してください。インターネットへ認証なしで公開してはいけません。

VPS側の環境変数には、ローカルPCワーカーのURLを設定します。

```text
CODEX_LOCAL_WORKER_URL=http://local-pc-over-vpn:8765
CODEX_WORKER_TOKEN=環境変数だけで渡す
```

ローカルPCが停止、使用中、Codex未インストール、リポジトリ不備のいずれかなら、ローカル担当は「利用不可」と判定され、VPS担当へ切り替わります。作業の途中で担当を入れ替えず、1つの作業を完了または停止してから次の作業を受け付けます。

## 音声利用時の報告

長いログやコードは読み上げません。Hermesは次の短い状態だけを音声で伝えます。

- 「作業を登録しました」
- 「ローカルCodexが実装中です」
- 「ローカルPCが使えないため、VPS Codexへ切り替えました」
- 「VPS Codexが監査中です」
- 「監査で問題が見つかりました。修正が必要です」
- 「監査に合格しました。反映には承認が必要です」

この仕組みは、運転中の音声操作を短く保ちつつ、詳しい根拠を後から確認できるようにするためのものです。

## 現時点の境界

このリポジトリには、台帳、状態遷移、監査ゲート、ローカル優先/VPS代替ルーター、認証付きワーカーAPI、CLIが実装されています。実際のVPSで常駐させるには、VPS上で `voice-suite tech worker` をサービス化し、Hermes側の環境変数とVPN経路を設定してください。

既存のDiscord音声処理と3秒ごとの先行STT変換をこの監査経路へ接続する作業は、次の統合段階です。音声処理の変更自体は、すでに `audio_pipeline_change` として監査必須にできます。VPSの実装ワーカーをHTTP経由にする場合は、実装用とは別の `CODEX_AUDITOR_URL` を必ず用意し、監査を同じ処理へ自己判定させないでください。
