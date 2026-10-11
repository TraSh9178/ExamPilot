# UI-4：学习页面优化

分支：`ui-4`。基线：`main@bc4f44fbb9ad1e441f97290a6fb22a030d952617`。
本分支保留该基线的 Knowledge Graph 和 Study Cards 实现。

## 已完成

- 统一浅蓝白色背景、卡片、标题、表单和键盘焦点；主操作使用蓝色按钮，次操作使用浅色按钮。
- Dashboard 精简顶部介绍，增加课程、知识点和练习次数概览；创建课程分为命名、上传提取、预览生成三个步骤。
- 上传说明保留文件格式和限制，将详细限制折叠显示；英文图片的来源和页列表使用 `Image` 标签。
- 删除课程需再次确认；取消后保留课程，确认后只清除选中的课程及其本机会话状态。
- 侧栏显示当前课程及切换入口；Study Plan 将范围选择和确认放在课程主题列表之前。
- Practice 显示已答题数量和进度，提交前说明未答题的评分结果；成绩页提供 Progress 和 Knowledge Map 入口。
- Anki 下载按钮提前到卡片列表顶部，显示可导出数量，保留逐卡答案折叠和弱点筛选。
- 手机端优化课程卡片、答题概览、Anki 下载区域及 Graph 与详情的上下布局；Graph 缩放按钮仍横向排列。

## 验证

- 完整 pytest：**294 passed，5 个 SWIG 弃用警告，0 failed**。
- 真实浏览器：**13/13 Pass**，20 张截图；同一浏览器会话覆盖三门 Demo、范围确认、答题进度与评分、Progress、Graph 交互、真实 Anki 下载、TXT/英文 PNG 提取及清理、删除取消及确认。
- 环境：macOS 15.5 arm64，Chromium 153.0.8010.12，Tesseract 5.5.3，`eng` 可用。桌面视口 1440×1000，手机视口 390×844；手机结论属于 Chromium 视口模拟，未验收实体手机或 Safari。
- 删除确认测试验证首次点击不删除、取消后保留、确认后仅删除目标课程。
- PNG/JPG/JPEG 的来源标签和移除后清理使用模拟提取结果测试；实际浏览器验收与模拟测试分别记录。
- 最终浏览器结果见本机 `/tmp/exampilot-ui4-acceptance/artifacts/browser_acceptance.json`，截图位于同一目录。
- 自动化命令：在项目目录使用已安装项目依赖的 Python 环境运行 `python -m pytest -q`。

## 交付边界

此分支基于尚未合并 Auth 的 main；Auth 页面兼容性需要在后续集成版本另行验收。
注册登录、TigerData 连接和课程 Save/Restore 没有接入本分支。课程和练习记录仍属于当前浏览器会话，页面不宣称已同步云端。
本轮未调用 Gemini、未访问或修改真实数据库。Anki TSV 下载不代表 Anki Desktop 导入或 AnkiWeb 同步已验收。
没有修改评分、Mastery、Graph 物理行为或 Anki 导出服务。

## 本机预览

独立工作区：`/Users/charleschen/ExamPilot-ui-4`；原工作区修改已保留。
本轮预览地址：`http://127.0.0.1:8504`。
其他电脑需检出该分支、安装依赖并运行 `python -m streamlit run app.py`。
