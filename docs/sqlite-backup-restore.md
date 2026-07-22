# SQLite schema migration、备份与恢复

P&ID-Agent 将结构化图纸、历史记录和项目设置保存在单个 SQLite 数据库中。默认路径为 `data/pid-agent.db`；容器镜像使用 `/data/pid-agent.db`。

Provider API Key、共享部署 Bearer Token 和浏览器 session token 不写入该数据库，因此不会被数据库备份收集。项目设置中的自定义业务 metadata 属于项目数据，仍应按内部工程资料管理备份文件。

## Schema version 与启动迁移

数据库使用 SQLite `PRAGMA user_version` 保存 schema version，并在 `database_metadata` 中保存随机生成、与文件路径无关的持久 `instance_id`。

当前行为：

- 新数据库按顺序执行全部 migration；
- 旧版、尚未设置 `user_version` 的 P&ID-Agent 数据库会被识别并升级；
- migration 在独占事务内执行，失败时回滚；
- 比当前程序更新的数据库会被拒绝打开，防止旧程序降级写入；
- `pid-agent serve`、`pid-agent mcp` 和 `pid-agent db info` 都会在打开数据库时执行必要 migration。

升级应用前应先创建备份。不要用旧版本应用打开已由新版本升级的数据库。

## 查看数据库身份

```bash
pid-agent db info --database /srv/pid-agent/pid-agent.db
```

输出为 JSON，包含：

- 当前 schema version；
- 程序支持的 schema version；
- 持久 `instance_id`；
- 文档数量；
- SQLite page size、page count 和文件大小。

省略 `--database` 时读取 `PID_AGENT_DATABASE_PATH`，其次读取兼容变量 `AGENTCAD_DATABASE_PATH`。

## 在线备份

```bash
pid-agent db backup \
  --database /srv/pid-agent/pid-agent.db \
  --output /srv/pid-agent/backups/pid-agent-2026-07-22.pidbak
```

备份使用 SQLite online backup API，因此可以在服务继续处理请求时取得一致快照。输出 `.pidbak` 是一个只包含以下两个成员的 ZIP 包：

```text
database.sqlite3
metadata.json
```

`metadata.json` 记录备份格式版本、数据库 schema version、`instance_id`、UTC 时间、数据库大小和 SHA-256。命令在同目录生成临时文件，完成 SQLite `quick_check`、foreign-key check、大小和 SHA-256 校验后才原子替换目标文件。

默认不覆盖已有备份；确需覆盖时使用：

```bash
pid-agent db backup --output latest.pidbak --overwrite
```

建议将备份复制到不同主机或对象存储，并另外执行保留周期、加密、访问控制和离线恢复演练。

## 恢复到原实例

恢复前必须停止所有 P&ID-Agent 进程和会访问该数据库的工具：

```bash
systemctl stop pid-agent
pid-agent db restore \
  --database /srv/pid-agent/pid-agent.db \
  --input /srv/pid-agent/backups/pid-agent-2026-07-22.pidbak
systemctl start pid-agent
```

恢复流程在替换线上文件前完成：

1. 校验归档成员、metadata 格式、大小和 SHA-256；
2. 将候选数据库提取到目标目录，保证与目标位于同一文件系统；
3. 验证 schema version、持久 `instance_id`、SQLite `quick_check` 和 foreign-key check；
4. 校验目标数据库实例身份；
5. 使用 `os.replace` 原子替换目标数据库，并同步父目录。

任何校验失败都不会替换目标文件。目标是 symlink、非普通文件，或仍存在 `-wal`/`-shm` sidecar 时会拒绝恢复。sidecar 通常表示服务尚未完全停止或数据库未完成 checkpoint；不要直接删除包含未提交数据的 WAL。

## 缺失、损坏或不同实例的目标

当目标不存在或损坏，程序无法从目标读取实例身份。此时必须显式确认备份输出中的 `instance_id`：

```bash
pid-agent db restore \
  --database /srv/pid-agent/pid-agent.db \
  --input backup.pidbak \
  --expect-instance-id 0123456789abcdef0123456789abcdef
```

默认禁止把 A 实例的备份覆盖到可读取的 B 实例。明确用于克隆、灾难重建或替换错误实例时，必须同时提供两个参数：

```bash
pid-agent db restore \
  --database /srv/pid-agent/pid-agent.db \
  --input backup.pidbak \
  --allow-instance-mismatch \
  --expect-instance-id 0123456789abcdef0123456789abcdef
```

这两个参数只确认目标选择，不会跳过归档 SHA-256、SQLite 完整性或 schema compatibility 校验。

## Docker volume

镜像把数据库放在 `/data/pid-agent.db`，应使用命名 volume：

```bash
docker run -d --name pid-agent \
  -v pid-agent-data:/data \
  -p 8000:8000 \
  pid-agent:latest
```

在线备份可直接写入 volume，再复制到宿主机：

```bash
docker exec pid-agent pid-agent db backup \
  --database /data/pid-agent.db \
  --output /data/pid-agent-backup.pidbak

docker cp pid-agent:/data/pid-agent-backup.pidbak ./pid-agent-backup.pidbak
```

恢复时停止主容器，通过一次性容器挂载同一 volume 和备份目录：

```bash
docker stop pid-agent

docker run --rm \
  -v pid-agent-data:/data \
  -v "$PWD:/backup:ro" \
  pid-agent:latest \
  pid-agent db restore \
    --database /data/pid-agent.db \
    --input /backup/pid-agent-backup.pidbak

docker start pid-agent
```

若 clean stop 后仍存在 sidecar，先确认没有任何容器挂载并写入该 volume，再使用同版本 Python/SQLite 执行 checkpoint；不要在进程仍运行时强制删除 sidecar。

## 灾难恢复检查表

1. 记录当前应用版本、数据库 `instance_id` 和备份 SHA-256。
2. 将 `.pidbak` 复制到隔离位置，验证文件大小和传输校验值。
3. 停止全部应用副本、worker、MCP 工具和维护脚本。
4. 在新目录或临时 volume 先执行一次恢复演练。
5. 检查 `pid-agent db info`、文档数量、关键图纸和历史记录。
6. 恢复正式目标并启动单个应用副本。
7. 检查 `/health`、诊断日志和关键读写事务后再恢复其余副本。
8. 保留恢复前数据库文件或 volume snapshot，直到验收完成。

多副本部署只能共享支持该访问模型的存储架构；不要让多个容器通过不具备正确 POSIX locking 语义的网络文件系统直接写同一个 SQLite 文件。
