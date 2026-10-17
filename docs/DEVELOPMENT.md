# 三人协作与提交记录

主开发目录为 `D:\ESP32\tongyu-zhishu-v1`，不要继续在旧副本修改后期待本仓库自动同步。原目录仅保留备份。

仓库为私人仓库。所有者在 GitHub 仓库 Settings → Collaborators 中邀请另外两位队友；队友接受后各自克隆，并配置自己的 Git 姓名和邮箱。不要共用账号或代署名。

每次开始一个实际任务：

```bat
git switch main
git pull --ff-only
git switch -c feat/your-task
```

修改并验证后，在根目录检查并提交对应文件：

```bat
python -m unittest discover -s tests -v
python scripts/verify_repository.py
git diff
git status
git add 本次修改的文件路径
git diff --cached
git commit -m "feat: describe the actual change"
git push -u origin feat/your-task
```

在 GitHub 创建 Pull Request，由另一位队友检查后合并。不同时修改同一大文件能减少冲突；发生冲突时先阅读两边改动，再合并并重新测试。

推荐消息前缀：`feat:` 新功能、`fix:` 修复、`docs:` 文档、`test:` 测试、`refactor:` 保持行为的重构、`chore:` 工程维护。一次提交对应一件可解释的事，消息说明实际改了什么。

提交记录只从实际提交开始积累。已完成的旧工作在初始提交说明中承认是导入成果，不倒填日期或伪造过去逐步开发的记录。GitHub 的 Commits 页面可查看每条提交的时间、作者与文件差异；文件 History 可看单文件变化。这里是协作约定，尚未配置强制分支保护。

密钥只填本机 `xiaozhi-server/data/.config.yaml`。不强制添加被忽略的配置、模型、音频缓存或日志；不把密钥粘贴到 Issue、PR 或提交消息中。
