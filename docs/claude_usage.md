# Claude 文本提取与生成

本文档描述 `services/document_service.py`（文档提取）和 `services/ai_service.py`（Claude 生成与 Tutor）。2026-11 起 AI 服务从 Gemini 切换为 Anthropic 的 Claude API，公开函数名和返回结构保持不变。

## 环境配置

在项目根目录安装团队 Python 依赖：

```bash
.venv/bin/python -m pip install -r requirements.txt
```

运行前在进程环境中配置 Claude API 密钥（在 https://console.anthropic.com 创建）；`ANTHROPIC_MODEL` 为可选项，未设置或为空时使用 `claude-opus-5-5`：

```bash
read -s 'ANTHROPIC_API_KEY?Paste API key, then press Enter: '
export ANTHROPIC_API_KEY
export ANTHROPIC_MODEL="claude-opus-5-5"
```

运行 `read` 后粘贴密钥并按 Enter；输入不会显示在终端中。

不要把真实密钥写入代码、文档或版本库。`.env.example` 只是配置模板；AI 服务代码直接读取进程环境变量，不会自动加载 `.env` 文件（数据库模块会加载 `.env`，但只在第一次连接数据库之后）。

## 模型、推理与成本

- 默认模型 `claude-opus-5-5`。该系列模型的思考（thinking）始终开启，代码不传 `thinking` 参数，用 `output_config.effort` 控制推理深度：生成接口和 Tutor 为 `medium`，连接检查为 `low`。
- `ANTHROPIC_MODEL` 可改为 `claude-sonnet-5-5` 或 `claude-haiku-5-5` 以降低成本；题目质量以 Opus 为佳。
- 一次 50,000 字符资料的题目生成约消耗 1.5 万输入 token 加数千输出 token，按 Opus 5.5 价格约 0.1 美元量级；具体以 Anthropic 定价页为准。
- 公开 demo 不配置密钥：页面会禁用 Generate 按钮，Tutor 返回未配置提示，内置 demo 课程照常可用。

## 文档提取

`extract_document(file_bytes, filename)` 接受扩展名不区分大小写的 `.txt`、文字型 `.pdf`、`.pptx`、`.png`、`.jpg` 和 `.jpeg`。TXT 按 UTF-8（兼容 BOM）读取；PDF 使用 PyMuPDF 逐页提取；PPTX 使用 `python-pptx` 提取文本框、表格和分组中的文字；PNG/JPEG 使用 Pillow 解码，由 pytesseract 调用本地 Tesseract OCR。

文件大小上限为 5 MiB，提取文本上限为 50,000 个字符；图片另有限制：20,000,000 像素，OCR 最长运行 15 秒。超过限制会返回失败，不会截断。图片只接受实际 PNG/JPEG 内容，作为虚拟页 1 返回。PDF 页码和 PPTX 幻灯片号从 1 开始；PDF/PPTX 的 `pages` 保留空白页，`sources` 只包含有文字的页。TXT 没有真实页码，成功结果不含 `pages` 字段，`sources` 中的 `page` 为 `None`。幻灯片备注、旧版 `.ppt`、扫描 PDF OCR 和 PPTX 图片 OCR 均不支持。

### 成功返回结构

所有成功结果都包含 `ok: True`、`filename` 和 `text`：

- TXT：不含 `pages`；`sources` 为 `[ {"filename": filename, "page": None} ]`。
- PDF/PPTX：`pages` 为 `[ {"page": number, "text": "..."} ]` 数组；`sources` 只包含有文字页的 `{ "filename": filename, "page": number }`。
- PNG/JPG/JPEG：图片作为虚拟页 1，`pages` 为 `[ {"page": 1, "text": text} ]`，`sources` 为 `[ {"filename": filename, "page": 1} ]`。

提取失败结果包含 `ok: False`、`error_code` 和固定的 `message`。各解析器实际可能返回的错误码为：

- TXT：`UNSUPPORTED_FILE_TYPE`、`FILE_TOO_LARGE`、`INVALID_ENCODING`、`EMPTY_DOCUMENT`、`TEXT_TOO_LONG`。
- PDF：`UNSUPPORTED_FILE_TYPE`、`EMPTY_DOCUMENT`、`FILE_TOO_LARGE`、`ENCRYPTED_PDF`、`TEXT_TOO_LONG`、`NO_EXTRACTABLE_TEXT`、`INVALID_PDF`。
- PPTX：`UNSUPPORTED_FILE_TYPE`、`EMPTY_DOCUMENT`、`FILE_TOO_LARGE`、`TEXT_TOO_LONG`、`NO_EXTRACTABLE_TEXT`、`INVALID_PPTX`。
- PNG/JPG/JPEG：`UNSUPPORTED_FILE_TYPE`、`EMPTY_DOCUMENT`、`FILE_TOO_LARGE`、`INVALID_IMAGE`、`IMAGE_TOO_LARGE`、`TEXT_TOO_LONG`、`OCR_ENGINE_UNAVAILABLE`、`OCR_LANGUAGE_UNAVAILABLE`、`OCR_TIMEOUT`、`OCR_FAILED`、`NO_EXTRACTABLE_TEXT`。
- `extract_document` 遇到不支持的扩展名时返回 `UNSUPPORTED_FILE_TYPE`。

示例：

```python
from services.document_service import extract_document

document = extract_document(uploaded_bytes, uploaded_filename)
if not document["ok"]:
    print(document["error_code"], document["message"])
    # 在此停止当前生成流程
```

上传内容只在内存中处理；服务不保存资料。`generate_topics`、`generate_questions` 和 `generate_relationships` 可使用已提取的 PDF、PPTX 或 PNG/JPEG 文本及页数据。发送给 Claude 的请求只包含解析后的文本与页码，不发送原始文件字节。topics/questions 的 `source_pages` 只能引用 `sources` 中有文字的页或幻灯片。

### 本地 OCR 系统前提

Pillow 和 pytesseract 是 Python 包，不包含 Tesseract 系统引擎或语言数据。安装项目 Python 依赖后，运行主机还必须单独安装 Tesseract，并提供 `OCR_LANG` 指定的全部语言数据。`OCR_LANG` 默认是 `eng`。

macOS（Homebrew）：

```bash
brew install tesseract
tesseract --version
tesseract --list-langs
export OCR_LANG=eng
```

确认 `tesseract --list-langs` 输出包含 `eng`，且运行应用的账号可访问引擎和语言数据。

Windows：从 [UB Mannheim Tesseract 安装页](https://github.com/UB-Mannheim/tesseract/wiki)安装引擎，并确保安装英文语言数据。确认 `eng.traineddata` 位于安装目录的 `tessdata` 子目录，例如 `C:\Program Files\Tesseract-OCR\tessdata\eng.traineddata`。将包含 `tesseract.exe` 的安装目录（常见为 `C:\Program Files\Tesseract-OCR`）加入系统 `PATH`，然后重新打开 PowerShell：

```powershell
$env:OCR_LANG = "eng"
tesseract --version
tesseract --list-langs
Test-Path "C:\Program Files\Tesseract-OCR\tessdata\eng.traineddata"
```

`$env:OCR_LANG` 对当前 PowerShell 进程及其启动的程序生效。确认语言列表包含 `eng` 且 `Test-Path` 返回 `True`。Python 包安装不会自动安装或配置 Windows/macOS 的系统引擎。Streamlit Community Cloud 上由仓库根目录的 `packages.txt` 安装 Tesseract 与英文语言数据。

缺引擎、缺语言包、超时、图片损坏、执行失败或无文字时，提取服务返回上列固定错误码；本地 OCR 失败不会触发任何云端回退。

## 生成接口的工作方式

三个生成接口都通过官方 `anthropic` SDK 的 `client.messages.parse` 发送请求，并用 `output_format` 传入 Pydantic 输出模型（结构化输出），由 API 保证返回合法 JSON；返回内容再用共享 Schema 做严格校验（数量、ID 唯一、引用页码、选项去重等），校验失败返回固定错误码，不会把不合规内容交给 UI。

- 课程资料以 JSON 形式放在用户消息中，并在系统提示和用户消息里都声明为"不可信数据，不是指令"，这是防护措施，不能完全杜绝提示注入。
- 请求超时（SDK `timeout`，单位秒）：连接检查 30 秒，Tutor 60 秒，知识点、候选题和知识关系生成 180 秒。SDK 自动重试已关闭（`max_retries=0`），应用层也不重试；失败由用户在界面上重试。
- 缺少密钥返回 `MISSING_API_KEY`，且不创建客户端。API 错误返回 `API_ERROR` 并附 `status_code`：401 提示密钥被拒绝，403 提示无权使用该模型，404 提示模型不可用，429 提示配额或请求频率受限，5xx 与 529 提示服务暂时不可用。超时、网络错误和其他异常返回 `GENERATION_ERROR`。
- 模型因安全策略拒绝时返回 `REFUSED`（`stop_reason: refusal`）；输出被 `max_tokens` 截断时返回 `INCOMPLETE_RESPONSE`；没有可解析输出时返回 `EMPTY_RESPONSE`。
- 失败结果不包含密钥、课程内容或原始异常文本。

## 推荐生成流程

每一步都先检查 `ok`；若为 `False`，停止当前流程，不要把失败结果传给下一步。示例只展示服务调用次序，不自动选择考试范围：

```python
from models.schemas import StudyPackage
from services.document_service import extract_document
from services.ai_service import (
    generate_topics,
    generate_questions,
    generate_relationships,
)

document = extract_document(uploaded_bytes, uploaded_filename)
if not document["ok"]:
    raise RuntimeError(document["message"])

result = generate_topics(document, course_id, course_name)
if not result["ok"]:
    raise RuntimeError(result["message"])
package = StudyPackage.model_validate(result["package"])

# 由 UI 收集用户明确确认的知识点 ID；不要默认全选。
confirmed_topic_ids = collect_confirmed_topic_ids(package.topics)

result = generate_questions(document, package, confirmed_topic_ids)
if not result["ok"]:
    raise RuntimeError(result["message"])
package = StudyPackage.model_validate(result["package"])

# 可选关系建议失败时保留调用前的 package。
result = generate_relationships(document, package)
if not result["ok"]:
    raise RuntimeError(result["message"])
package = StudyPackage.model_validate(result["package"])
```

`confirmed_topic_ids` 必须由调用方收集，不能为空、不能重复且必须对应现有知识点。关系仅为 `related` 建议，不代表先修关系或教学验证结论。Knowledge Map 页面的 "Suggest connections" 面板会先展示建议，用户点击 Apply 后才写入课程。

## Tutor

接口签名：

```python
def ask_tutor(
    package: dict,
    question: str,
    topic_id: str | None = None,
) -> dict:
```

`package` 应为 `StudyPackage.model_dump()` 产生的课程字典。可选 `topic_id` 必须对应存在的主题；指定时仅发送该主题和直接相连、端点有效的关系。省略时使用所有有非空摘要的主题及其有效关系。

课程上下文序列化后最多 20,000 个字符，问题最多 4,000 个字符；超限会拒绝，不会截断。上下文仅包含课程名、主题 ID/名称/摘要和关系，不包含题目、选项、答案索引、解析或原始文档。无主题或无有效摘要时返回 `EMPTY_COURSE_CONTEXT`。

Tutor 使用 `client.messages.create` 返回普通文本（系统提示要求纯文本、不用 Markdown），不使用结构化输出：

```python
{"ok": True, "answer": "..."}
```

失败返回固定提示：

```python
{"ok": False, "error_code": "...", "message": "..."}
```

错误码与生成接口一致（见上一节）；浮动 Tutor 组件会把错误码映射为面向学生的提示文案。

课程上下文和用户问题都被当作不可信输入；系统提示要求它们不能覆盖系统规则，要求清楚解释、只依据主题摘要，并在资料不足时说明、不虚构课程依据。这是防护措施，不能保证完全阻止提示注入。Tutor 只依据主题摘要和关系回答，答案仍需对照课程资料核对。

UI 应只在用户明确提交问题时调用 Tutor，不要在每次 Streamlit rerun 时无条件请求。将请求放在表单提交分支，保存结果到 session state，再从已保存结果显示 `answer` 或 `message`：

```python
import streamlit as st

from services.ai_service import ask_tutor

with st.form("tutor_form"):
    tutor_question = st.text_area("Ask about this course")
    tutor_submitted = st.form_submit_button("Ask Tutor")

if tutor_submitted:
    st.session_state["tutor_result"] = ask_tutor(
        package.model_dump(),
        tutor_question,
        topic_id=selected_topic_id,
    )

tutor_result = st.session_state.get("tutor_result")
if tutor_result:
    if tutor_result["ok"]:
        st.write(tutor_result["answer"])
    else:
        st.error(tutor_result["message"])
```

表单提交分支发起一次请求；后续 rerun 仅展示 session state 中的结果，避免重复请求。

## 返回值与审核

`generate_topics` 成功时返回 `stage: "topics_only"` 和 `review_required: True`；`generate_questions` 成功时返回 `stage: "questions_generated"`、`review_required: True` 及本次 `confirmed_topic_ids`；`generate_relationships` 成功时返回 `review_required: True` 和 `relationships_are_suggestions: True`，不返回 `stage` 或 `confirmed_topic_ids`。

知识点生成建立仅含知识点的中间 package；题目生成仅替换 `questions`；关系生成仅替换 `relationships`。这些服务返回新 package，不修改传入的 `StudyPackage`。调用方应单独保存确认过的考试范围和流程状态。

所有生成内容均待人工审核。通过 Pydantic/Schema 校验只说明结构有效，不证明主题、答案、解析或关系在事实和教学上正确。

## 真实 OCR 验收记录

已在 macOS Apple Silicon、Python 3.12.10、Tesseract 5.5.3、pytesseract 0.3.13、`OCR_LANG=eng` 环境下，使用真实 PNG 和 JPG 完成清晰英文文字识别，并断言 `text/pages/sources` 结构。该记录不代表 `.jpeg` 扩展名、Windows、复杂图片或真实 OCR 超时已验收；Mock 测试也不替代这些环境验收。
