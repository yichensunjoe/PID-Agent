# GitHub 仓库改名

产品、发行包、命令行、网页、API 和文档已统一使用 **P&ID-Agent**。

GitHub 仓库名不能包含 `&`，因此仓库 slug 使用：

```text
PID-Agent
```

仓库所有者需在 GitHub 仓库页面执行：

1. 打开 **Settings**；
2. 在 **General → Repository name** 中将 `agentcad` 改为 `PID-Agent`；
3. 确认重命名。

GitHub 通常会为旧仓库地址保留重定向，但本地克隆建议更新 remote：

```bash
git remote set-url origin https://github.com/yichensunjoe/PID-Agent.git
```

Python 导入路径 `agentcad`、旧 CLI `agentcad` / `agentcad-mcp`，以及旧 `AGENTCAD_*` 环境变量暂时保留为兼容别名。
