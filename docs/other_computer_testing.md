# 另一台电脑联测：UI、账户页和 Pilot

统一测试分支：`feature/pilot-mascot`。它包含字体与统计数字放大、知识图谱
节点碰撞/边界反弹、左侧栏账户入口、当前账号展示、会话头像，以及机械飞机机头
Pilot。原有 `fix/floating-ai-tutor-auth@09eb5d8` 和 Draft PR #24 保持不变。

本分支基于已交付 Auth/Tutor 基线，未同步最终 main 或 Save/Restore PR #23。
页面的课程、考试记录仍保存在 Streamlit 会话中；Save/Restore 按钮尚未接线，
不能用此分支宣称学习记录跨设备恢复通过。头像、聊天和草稿也不跨设备同步。

## 获取代码

在新目录克隆，避免覆盖已有工作区：

```bash
git clone --branch feature/pilot-mascot --single-branch https://github.com/TraSh9178/ExamPilot.git ExamPilot-ui-test
cd ExamPilot-ui-test
git rev-parse HEAD
```

将输出的完整 SHA 与 B 提供的交付 SHA 核对并记录；后续分支更新不代表此前
验收结果自动适用于新版本。已有仓库可以 `git fetch origin` 后在独立工作区检出
该分支或指定 SHA，不需要修改 main。

## 安装和启动

建议使用本轮本机测试所用的 Python 3.12。没有 npm 或前端构建步骤；Pilot
图标已包含在仓库中，不需要图像生成工具或生成图片的 API Key。

macOS，在项目根目录运行：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

Windows PowerShell，在项目根目录运行：

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

每台电脑打开自己的 `http://localhost:8501`；B 本机的 8516 预览地址不能直接
用于另一台电脑。Windows 命令供启动使用，本轮未完成 Windows 实机验收。

## 真实登录的配置

请 C 通过团队认可的私密渠道协助配置项目根目录 `.env`：

- `DATABASE_URL`：C 提供的测试 TigerData/PostgreSQL 配置。
- `DATABASE_SSLMODE`：`require`，或 C 指定的更严格 TLS 模式。

配置值不放入群聊、GitHub、截图、日志或验收报告。`.env` 已被 Git 忽略，
不会随代码上传。服务在认证操作时加载项目根目录 `.env`，已有环境变量优先。

由 C 确认测试数据库已有兼容的 `public.demo_users` 和
`exampilot_auth.users`，并提供测试账号或允许注册测试账号。一般 UI 测试者无需
执行建表 SQL，也不要初始化生产数据库。缺少配置时正式网站会停留在登录入口；
没有示例账号或登录绕过。

GitHub 中的正式代码不含 `UI preview · example accounts · no database`。
这个提示和示例账号只存在于 B 本机的临时预览脚本中，该脚本不上传。

## 建议实际检查

1. 注册或使用测试账号登录，在左下角和 My account 页确认当前用户名。
2. 上传 PNG/JPG 头像，检查账户页与侧栏同时更新；更换、删除和无效图片提示。
3. 退出再登录另一账号，确认头像、Pilot 对话和草稿没有残留。
4. 打开 Microeconomics、Calculus I 和 Python Basics Demo，检查标题及首页数字。
5. 进入 Practice、Progress、Anki，检查题目字号、统计数字与手机布局。
6. 打开 Knowledge Map，检查拖动节点后碰墙反弹、节点碰撞和节点详情。
7. 检查 Pilot 的金属蓝机头、青色驾驶舱窗和机械机翼，确认没有像素效果或白色按钮框；
   拖拽、展开、关闭、Esc 和方向键移动均可操作。

仅查看 Demo、布局和图标不需要调用 Gemini。要验证 Pilot 的真实回答，请通过
私密渠道配置有效 `GEMINI_API_KEY` 及可用模型，并单独记录真实服务结果；本轮
浏览器验收使用隔离示例身份，没有验证真实 Gemini。

只有验收图片 OCR 时才需要额外安装 Tesseract 并确认 `eng` 可用。知识图谱
浏览器渲染器需能访问项目使用的 unpkg CDN，Pilot 图片本身使用本地资源。

## 回传结果

提供实际完整 SHA、操作系统、Python 版本、逐项 Pass/Fail，以及问题复现步骤。
说明账号是否使用真实测试数据库、Pilot 是否调用真实 Gemini；不要把 mock 或
浏览器会话数据当成云端恢复证据。可附截图，但不包含凭据。

本轮已有证据：Pilot 桌面/手机 Chromium 浏览器检查 6/6，通过的 Auth 身份由
隔离测试替换；账户页此前浏览器检查 9/9。真实 TigerData 联测需要另一台电脑
按以上配置后独立报告。
