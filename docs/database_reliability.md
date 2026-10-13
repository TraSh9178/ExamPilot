# 数据库可靠性：本地审核说明

本分支基于已提交的 UI 版本 e3711ae，保持原有页面和账号认证流程。
没有执行 GitHub 拉取、推送或同步；没有对配置中的正式数据库执行迁移。

## 本次修复

- 提交练习：课程、试卷和完整答案在同一 PostgreSQL 事务中保存，任一步失败全部回滚。
- Study Plan 的 Save：本地课程与全部已评分练习一起保存，避免保存一半历史。
- 重复保存同一个练习 ID、相同内容：成功返回，不重复插入答案。
- 同一个练习 ID 改变课程、模式、题目顺序或答案：拒绝覆盖，必须创建新练习。
- 同一用户跨课程并发复用练习 ID：按课程和练习 ID 加事务级锁，防止记录混入另一个课程。
- 保存与恢复：根据题目正确答案核验 is_correct；缺失答案、重复题目、错误课程身份会导致恢复失败，不以损坏记录计算进度。
- 题目版本：沿用原有的追加式题库；修改题目必须使用新 ID，原来的题目及历史成绩保留。不自动重写历史题目。
- 保存失败时保留本地学习记录并标记待保存；重试成功才清除标记。
- 单元测试禁用自动读取 .env 中的数据库地址，避免测试意外触及正式数据库。

## 审核方法

在本地网站正常登录，进入课程并完成一次练习；保存后退出再登录，核对答案与成绩。
同一份记录重试保存应成功且不增加练习次数。开始新练习可以选择不同答案；已经提交的旧练习不会被覆盖。

自动测试中的事务故障通过临时数据库触发器注入，用户不需要断网或修改自己的数据库来复现。

## 结构升级（明确执行才会运行）

新增 db/migrations 与 exampilot_schema_migrations 版本表。迁移使用事务、互斥锁和 SHA-256 校验；
已执行文件被修改或删除会拒绝继续。任何迁移失败，DDL 和版本记录都回滚。

001 建立原有学习表，可重复兼容已有表；002 添加课程 JSON 身份和非空试卷约束。
新增检查采用 NOT VALID，保留旧行供应用校验，约束随后新增和更新的数据，不自动修复旧数据。
升级需要对应的 DDL 权限；现有但结构不兼容的表可能使升级失败，事务会回滚。
账号表、数据库角色、权限和 RLS 策略不在此次迁移范围。

确认备份且审核后，数据库管理员可在项目根目录运行：

```bash
.venv/bin/python -m services.database_migrations
```

该命令读取项目 .env 中的 DATABASE_URL 和 TLS 配置，绝不会因打开网页自动执行。
代码层可靠性修复不要求先运行迁移；新增约束属于额外保护。
后续结构变更新增编号 SQL 文件，不要改写已执行的迁移文件。
旧的 initialize_schema 兼容接口保留，已有部署可使用上述命令接入版本记录。

## 验证与备份恢复

普通检查（不连接正式数据库）：

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider
```

真实 PostgreSQL 测试需显式提供 EXAMPILOT_TEST_DATABASE_URL，必须是一次性本地服务器。
每个测试创建独立 schema 并在结束后移除；不是正式数据库地址，也不要复用有重要数据的本地库。

```bash
EXAMPILOT_TEST_DATABASE_URL='host=127.0.0.1 port=55439 user=postgres dbname=exampilot_test' \
EXAMPILOT_TEST_PG_BIN='/absolute/path/to/postgresql/bin' \
.venv/bin/python -m pytest -q tests/test_database_integration.py
```

恢复测试使用真实 pg_dump / pg_restore，备份临时学习表并恢复到另一个临时数据库，
之后通过应用接口验证课程、试卷、答案及用户隔离。执行账号需要创建 schema／数据库的权限。
测试不会备份或恢复真实账号数据；正式备份还需包含 exampilot_auth、角色权限和其他使用的 schema。

正式运维建议由管理员配置 PGHOST、PGPORT、PGDATABASE、PGUSER 和受保护的 .pgpass，
不把密码放在命令参数里。备份与恢复示例：

```bash
pg_dump --format=custom --file=exampilot-backup.dump
# 把 PGDATABASE 指向预先创建的空恢复数据库，再执行：
pg_restore --exit-on-error --no-owner --no-privileges --dbname="$PGDATABASE" exampilot-backup.dump
```

恢复目标必须是空的隔离库；审核角色权限后再考虑切换应用连接。
备份可能包含账号密码哈希和学习材料，需私密保存，不加入 Git。
这次已准备并测试恢复流程，没有为正式数据库安排自动备份或变更连接。

## 边界

用户身份来自服务端登录会话，持久化查询继续按用户 ID 过滤；本次验证的是应用访问隔离，
不是数据库 RLS。直接连接数据库的高权限角色仍可读写所有数据，正式部署需另行审核权限。
此次没有添加后台任务、连接池或自动数据清理，也没有自动修复已损坏的旧记录。

## 本次验证结果

- 常规测试：543 passed，13 skipped，5 warnings；跳过项是需显式本地 PostgreSQL 配置的集成测试。
- 独立临时 PostgreSQL：13 passed，包含并发、回滚、用户隔离、历史题目、迁移及跨库备份恢复。
- git diff --check 通过。真实数据库证据仅来自临时本地库，不代表正式数据库已迁移或已完成真实账号浏览器验收。
