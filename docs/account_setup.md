# 账号与密码配置

ExamPilot 使用通用 psycopg PostgreSQL 连接存储网站账号，可使用 Supabase 或 TigerData。
不要求使用 Supabase Auth；TigerData 的实际连接与注册登录仍需 C 验证。
启动入口仍是 `app.py`。未登录时只显示注册与登录页面；注册成功后自动登录。

## 本地启动

1. 安装依赖：

   ```bash
   .venv/bin/python -m pip install -r requirements.txt
   ```

2. 在项目根目录创建 `.env`，参考 `.env.example` 设置：

   ```dotenv
   DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DATABASE
   DATABASE_SSLMODE=require
   ```

   使用数据库提供方给出的 PostgreSQL 连接配置；TigerData 可使用同一配置接口。
   如使用 Supabase，从项目顶部的 **Connect** 复制 PostgreSQL 连接串，替换数据库密码。
   密码中的特殊字符需要 URL 编码；只支持 IPv4 的环境可以使用 **Session pooler**。
   连接地址和密码只保存在本机 `.env` 或部署环境变量中，`.env` 已加入 Git 忽略列表。
   连接串和网络模式说明见 [Supabase 官方文档](https://supabase.com/docs/guides/database/connecting-to-postgres)。

3. 由 C 确认目标数据库中已有 `public.demo_users`，其 `demo_user_id` 为
   `TEXT` 主键，并确认连接角色已有所需权限。Auth 不创建或迁移这张父表。
   经审核批准后执行一次 Auth 建表命令：

   ```bash
   .venv/bin/python -m services.auth_service
   ```

   默认仅执行 `db/auth_schema_minimal.sql`，在一个事务中按需创建
   `exampilot_auth` schema 和 `exampilot_auth.users`。
   SQL 只有两条 `CREATE ... IF NOT EXISTS`，可以重复执行；不会创建父表、课程、考试或练习表，
   不修改已有表结构、数据、权限、RLS 设置或策略。
   新建账号表通过外键引用已有的 `public.demo_users`；新建时父表缺失会导致初始化失败，
   本次事务中的建表操作会回滚。数据库连接角色需要已有的建表、外键引用及账号读写权限；
   命令不会授予或撤销权限。
   网站不会在普通登录请求中自动建表。

4. 启动网站：

   ```bash
   .venv/bin/python -m streamlit run app.py
   ```

   在 **Create account** 中填写用户名、密码及确认密码，注册后进入 Dashboard。

## 使用规则

- 用户名为 3–32 个字符，允许英文字母、数字、点、下划线和连字符，忽略大小写。
- 密码为 15–128 个字符，支持中文和空格。空格不会被自动删除。
- 同一个账号连续输错密码 5 次，暂停登录 5 分钟；锁定期间的请求不延长到期时间。
  到期后首次输错从 1 重新计数，第 5 次新错误才再次锁定；到期后成功登录则清零。
- 登录会话最长为 8 小时。刷新浏览器、新开会话或会话过期后，需要重新登录。
- 点击侧栏 **Log out** 会清除登录信息、当前课程、上传资料及练习会话。

## 数据结构与边界

默认建表文件是 `db/auth_schema_minimal.sql`。`exampilot_auth.users` 保存账号 UUID、
用户名、密码哈希及登录失败信息。
账号 UUID 同时写入 `public.demo_users`，可用于现有数据库接口的用户隔离。
新建账号表的外键使用 `ON DELETE RESTRICT`，已被账号引用的 `demo_users` 行不能被直接删除。
`CREATE ... IF NOT EXISTS` 不会修复数据库中已有但结构不一致的表。

此分支只提供 `db/auth_schema_minimal.sql` 的最小账号初始化，未包含权限、RLS 或课程表迁移。

密码使用随机盐和 scrypt 哈希，不存明文。哈希参数依据
[OWASP 密码存储指南](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)。
如果 scrypt 因资源或运行环境问题失败，注册、登录返回通用服务不可用提示，
`AuthResult.error_code` 为 `password_service_unavailable`，不泄露底层异常内容。
注册不会创建账号或父表记录；登录会回滚事务，不修改失败次数、不建立登录身份。
不会降低哈希参数或跳过密码验证，需要修复运行环境后重试。
账号表位于独立 schema；最小建表命令不会修改任何表的权限或 RLS。不要把
`exampilot_auth` 加入 Supabase Data API 的 exposed schemas 或向客户端授予访问权限；
schema 的 API 暴露机制见 [Supabase schema 文档](https://supabase.com/docs/guides/api/using-custom-schemas)。

网站账号由 Streamlit 服务器校验，不生成 Supabase Auth token，也不使用 Supabase Auth
的用户身份或公开 API 登录。账号表只通过服务器端 PostgreSQL 连接访问；业务表已有的
Supabase API 权限和策略保持原样。

这次接入的是账号认证。当前学习页面的课程和练习数据仍保存在 Streamlit 会话中，
退出或刷新后不会自动恢复。数据库分支的课程持久化服务尚未接到学习页面。
目前提供注册、登录和退出，尚未提供密码重置、邮箱验证或账号管理界面。

## 验证

```bash
.venv/bin/python -m pytest -q
```

测试覆盖密码哈希、数据库事务与登录锁定、注册及登录表单、页面访问限制、退出清理，
以及原有学习功能。自动化数据库单元测试使用替身连接；实际 Supabase/TigerData 连通性、
事务行为、注册登录及数据归属隔离需要在审核批准的数据库中另行验证。
