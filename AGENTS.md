# Gen 上游同步

- 官方基线是 `MediaBrowser/plugin.video.emby` 的 `next-gen-dev-python3`，本地远端名为 `origin`。更新基线时，先确认目标上游提交并保留本地回退引用，再将 Gen 的提交 rebase 到该上游提交。
- 按改动目的解决冲突，核对 Gen 的定制行为和此次采用的上游改动。用 `git range-diff` 对照 rebase 前后的提交，复核分支差异并运行相关检查。
- 推送重写后的分支时，使用 `--force-with-lease` 并指定已确认的远端分支旧提交。已发布的版本标签继续指向各自的发布提交。
