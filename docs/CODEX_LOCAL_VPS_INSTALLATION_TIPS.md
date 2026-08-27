# Codex向け：ローカル設置 / VPS設置の実装Tips

## 現在の前提

- VPSは24時間ban中。今はVPSへ接続・再起動・設定変更をしない。
- 今回の目的は会社構造の説明ではなく、ローカルPC上の「純米Bot」の設立。
- ローカルPCは本日稼働したまま。ローカル設置とローカル起動確認を優先する。
- Hermesの既存Gatewayとは別のDiscord Bot tokenを使う。

## ローカル設置の正しい構成

```text
Discord
  -> Codex JUNMAI Bot
  -> 127.0.0.1:8777 の prompt-only Chat Worker
  -> Codex CLI (--sandbox read-only)
```

- Bot本体は `python -m voice_suite.codex_local_cli`。
- Chat WorkerはBotと同一プロセス内でloopback起動する。
- 外部公開ポートは開けない。
- `8765`は既存のWhisper CUDAサービスなので使用禁止。
- 純米BotのChat Worker既定ポートは`8777`。

## 必要なローカルsecret

`.env`へローカルで投入する。Discordやログへ値を出さない。

- `CODEX_DISCORD_BOT_TOKEN`：純米Bot専用Discord token
- `CODEX_CHAT_WORKER_TOKEN`：ローカルChat Worker専用token
- `OPENAI_API_KEY`：STT/TTSおよび必要なCodex連携用

`CODEX_DISCORD_BOT_TOKEN`はHermesの`DISCORD_BOT_TOKEN`と別物にする。
`CODEX_CHAT_WORKER_TOKEN`も技術worker tokenと別物にする。

## 起動と確認

秘密値を表示しない確認：

```powershell
Set-Location C:\AI\APP\hermes-voice-suite
python -m voice_suite.codex_local_cli --check
```

必要な3項目が揃ってからBotを起動する。起動後はDiscord接続、guild/channel制限、`/health`の`ready`を別々に確認する。

## VPS側との分離

- VPSは現在変更しない。ban解除後に初めて再確認する。
- ローカルBotの設立にVPS reverse tunnelは必須ではない。
- まずローカルBot→ローカルChat Worker→Codex CLIを成立させる。
- ローカル実動確認後、必要な場合だけVPSから到達する経路を設計する。
- 同じDiscord Bot tokenをローカルとVPSで同時起動しない。

## 安全な実装原則

1. Bot token、Chat Worker token、OpenAI keyをログ・Discord・Gitへ出さない。
2. Bot APIはprompt-only。task metadataやdeploy/delete指示をHTTPで受け付けない。
3. Codex CLIは`--sandbox read-only`を固定する。
4. local Botの権限とVPS Hermesの権限を自動で混ぜない。
5. 起動済みプロセス・ポートを検知し、二重起動しない。
6. 失敗時はcredentials待機または再試行し、tokenを推測して続行しない。
7. `--check`成功だけで稼働扱いにせず、Discord接続と実際のprompt応答を確認する。

## 設立の完了条件

```text
[ ] 3つのsecretがローカルに存在（値は非表示確認）
[ ] --checkが成功
[ ] 純米Botプロセスが起動
[ ] Discordへ専用Botとして接続
[ ] guild/channel制限が有効
[ ] Chat Worker healthがready
[ ] prompt 1件に応答
[ ] Hermes Botとは別token
[ ] VPSは未変更のまま
```

上記を満たすまで「純米Bot設立完了」とは呼ばない。
