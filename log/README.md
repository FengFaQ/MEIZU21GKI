# log/ — 构建失败日志

CI 在**构建失败**时会自动把日志提交到本目录(默认分支 `main`):

```
log/
└─ <run_number>-run<run_id>/
   ├─ README.md            # 摘要: 提交/变体/LTO/extra_config/运行页面链接
   ├─ summary.txt          # build.yml 生成的构建摘要(编译失败时)
   ├─ compile-attempt-1.log# 每次编译尝试的完整日志(set -ex 输出)
   ├─ compile-attempt-2.log
   ├─ disk-usage.txt / ccache-stats.txt
   └─ patch-rejects/       # 补丁冲突文件(.rej/.orig)快照(若有)
```

- 提交日志**不会**再次触发构建:`meizu21.yml` 的 `on.push.paths` 不含 `log/**`。
- 成功构建不写日志;成功产物走 **Releases(预览版)** + `dist` 分支。
- 本地取回失败日志(无需 GitHub API 权限):

```powershell
git -C <本地克隆> fetch origin main
git -C <本地克隆> show FETCH_HEAD:log/<run_number>-run<run_id>/compile-attempt-1.log
```

- 目录会随时间累积,可定期清理旧 `log/<...>/`(保留最近若干次即可)。
