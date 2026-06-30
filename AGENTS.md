Codex作業開始時の注意事項

読むときは、最初の1回目から通常の Get-Content を使わず、必ずUTF-8指定で読むこと。

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Get-Content -LiteralPath 'ファイルパス' -Raw -Encoding UTF8

Codex作業開始時の必読ファイル

以下のファイルを、上から順番に必ず読むこと。

C:\Users\tf10c\.claude\CLAUDE.md
C:\Users\tf10c\project\fx_trading_bot\CLAUDE.md
C:\Users\tf10c\Dropbox\ObsidianVault\EA\EA_main.md
C:\Users\tf10c\Dropbox\ObsidianVault\EA\EA_log.md
C:\Users\tf10c\Dropbox\ObsidianVault\FES1.1案.md
