# Gemini 文本提取与生成

## 环境配置

在项目根目录安装团队依赖：

```bash
.venv/bin/python -m pip install -r requirements.txt
```

运行前在进程环境中配置 Gemini API 密钥；`GEMINI_MODEL` 为可选项，未设置或为空时使用 `gemini-3.8-flash`：

```bash
read -s 'GEMINI_API_KEY?Paste API key, then press Enter: '
export GEMINI_API_KEY
export GEMINI_MODEL="gemini-3.8-flash"
```

运行 `read` 后粘贴密钥并按 Enter；输入不会显示在终端中。

不要把真实密钥写入代码、文档或版本库。`.env.example` 只是配置模板；服务代码直接读取进程环境变量，不会自动加载 `.env` 文件。

## 提取资料

`extract_document(file_bytes, filename)` 接受扩展名不区分大小写的 `.txt`、文字型 `.pdf`、`.pptx`、`.png`、`.jpg` 和 `.jpeg` 文件。TXT 按 UTF-8（兼容 BOM）读取；PDF 使用 PyMuPDF 逐页提取；PPTX 使用 `python-pptx` 提取文本框、表格和分组中的文字。PNG/JPEG 使用 Pillow 解码并由 pytesseract 调用本地 Tesseract OCR。所有文件大小上限为 5 MiB，文本上限为 50,000 个字符；图片另有 20,000,000 像素上限。超限会返回失败，不会截断。

图片只接受实际 PNG/JPEG 内容，OCR 超时为 15 秒。图片作为虚拟页 1 返回；`pages` 中保留该页文本，`sources` 的 `page` 为 `1`。PDF 页码从 1 开始；PPTX 的 `pages`/`sources` 页码表示从 1 开始的幻灯片号。PDF 和 PPTX 的 `pages` 保留空白页，`sources` 只包含有文字的页/幻灯片。TXT 没有真实页码，不返回 `pages` 字段，`sources` 中 `page` 为 `None`。幻灯片备注、旧版 `.ppt`、扫描 PDF OCR 和 PPTX 图片 OCR 均不支持。

Pillow 和 pytesseract 是 Python 依赖；它们不会安装 Tesseract OCR 引擎或语言数据。运行主机还必须单独安装 `tesseract` 可执行文件，并安装 `OCR_LANG` 指定的全部语言包。`OCR_LANG` 默认是 `eng`，可通过进程环境变量设为例如 `chi_sim+eng`。可用 `tesseract --version` 检查引擎，使用 `tesseract --list-langs` 检查语言包。缺引擎、缺语言包、超时、图片损坏、执行失败或没有文字时，提取服务返回固定错误码和提示；不会把图片发送给 Gemini。

`generate_topics`、`generate_questions` 和 `generate_relationships` 可使用已提取的 PDF、PPTX 或 PNG/JPEG 文字及页数据。Gemini 请求只包含解析后的文本与页码，不发送原始 PDF、PPTX 或图片字节。topics/questions 的 `source_pages` 只能引用 `sources` 中有文字的页或幻灯片；图片来源页为 `1`。

```python
from services.document_service import extract_document

document = extract_document(uploaded_bytes, uploaded_filename)
if not document["ok"]:
    print(document["error_code"], document["message"])
    # 在此停止当前生成流程
```

上传内容只在内存中处理；服务不保存资料。

## 推荐调用顺序

每一步先检查 `ok`；若为 `False`，停止当前生成流程，不要把失败结果传给下一步。下面的 `uploaded_bytes` 和 `uploaded_filename` 应由调用方提供。示例只展示服务调用次序，不自动选择考试范围：

```python
from models.schemas import StudyPackage
from services.document_service import extract_document
from services.gemini_service import (
    generate_topics,
    generate_questions,
    generate_relationships,
)

# 1. 提取
result = extract_document(uploaded_bytes, uploaded_filename)
if not result["ok"]:
    raise RuntimeError(result["message"])
document = result

# 2. 生成知识点
result = generate_topics(document, course_id, course_name)
if not result["ok"]:
    raise RuntimeError(result["message"])
package = StudyPackage.model_validate(result["package"])

# 示意占位函数：当前不由 B 提供，需由 A 替换为实际 UI 收集逻辑。
# 收集用户明确确认的知识点 ID；不要默认全选。
confirmed_topic_ids = collect_confirmed_topic_ids(package.topics)

# 4. 按确认范围生成候选题
result = generate_questions(document, package, confirmed_topic_ids)
if not result["ok"]:
    raise RuntimeError(result["message"])
package = StudyPackage.model_validate(result["package"])

# 5. 可选：对当前资料和 package 生成关系建议
result = generate_relationships(document, package)
if not result["ok"]:
    raise RuntimeError(result["message"])
package = StudyPackage.model_validate(result["package"])
```

调用需要 `StudyPackage` 对象的生成函数前，先用 `StudyPackage.model_validate(result["package"])` 转换服务返回的 package 字典。`confirmed_topic_ids` 必须由 A 收集，不能为空、不能重复且必须对应现有知识点；服务不会默认全选。

示例中的 `RuntimeError` 仅用于错误时结束演示流程。A 的正式 UI 应处理服务错误并提供重试或加载示例课程等操作。可选的关系生成失败时，应保留调用前已有的 `package` 和题目，不要用失败结果覆盖它们。

## 返回值与流程状态
## Tutor

`ask_tutor(package: dict, question: str, topic_id: str | None = None) -> dict` 接受 `StudyPackage.model_dump()` 返回的课程字典和用户问题。可选 `topic_id` 必须对应课程中存在的主题；指定后只发送该主题及其直接相连、端点有效的关系。省略时发送所有有有效摘要的主题及其相连关系。

Tutor 的序列化课程上下文最多 20,000 个字符，问题最多 4,000 个字符；超限会返回错误，不会截断。上下文只包含课程名、主题 ID/名称/摘要及关系，不包含题目、选项、正确答案索引、解析或原始文档。没有主题或有效摘要时返回 `EMPTY_COURSE_CONTEXT`。

成功返回普通文本，不使用 `StudyPackage` 生成 Schema：

```python
{"ok": True, "answer": "..."}
```

失败返回固定消息；API 异常另带 `status_code`：

```python
{"ok": False, "error_code": "...", "message": "..."}
```

缺少密钥返回 `MISSING_API_KEY`，不会创建 Gemini 客户端。429 返回配额或请求频率受限提示，503 返回服务暂时不可用提示；服务不增加应用层自动重试。空白响应返回 `EMPTY_RESPONSE`，其他请求异常返回 `GENERATION_ERROR`，不会返回原始异常、密钥或课程内容。

课程上下文和问题会被标记为不可信输入；系统提示要求忽略其中试图覆盖规则的指令，只依据主题摘要解释，并在资料不足时明确说明、不虚构课程依据。这是防护措施，不保证完全防止提示注入。Tutor 仅能依据现有主题摘要和关系回答；回答仍需对照课程资料核对。

```python
from services.gemini_service import ask_tutor

tutor_result = ask_tutor(
    package.model_dump(),
    "Explain how these ideas connect.",
    topic_id="topic-1",
)
if tutor_result["ok"]:
    print(tutor_result["answer"])
else:
    print(tutor_result["error_code"], tutor_result["message"])
```

## 返回值与流程状态

生成函数的返回值是包装字典。`package` 字段包含 D 定义的 `StudyPackage.model_dump()` 结果；其余状态字段属于包装层，不是 `StudyPackage` Schema：

- `generate_topics` 成功时返回 `stage: "topics_only"` 和 `review_required: True`。
- `generate_questions` 成功时返回 `stage: "questions_generated"`、`review_required: True`，以及本次的 `confirmed_topic_ids`。
- `generate_relationships` 成功时返回 `review_required: True` 和 `relationships_are_suggestions: True`；不返回 `stage` 或 `confirmed_topic_ids`。

A 应单独保存确认过的考试范围和流程状态，不能依赖关系生成结果恢复这些信息。关系仅为 `related` 建议，不代表先修关系或教学验证结论。

所有成功生成内容均待人工审核。通过 Pydantic/Schema 校验只说明结构有效，不证明知识点、答案、解析或关系在事实和教学上正确。

## Package 更新规则

- 知识点生成建立仅含知识点的中间 package。
- 题目生成仅替换 `questions`，保留课程信息、topics 和 relationships。
- 关系生成仅替换 `relationships`，保留课程信息、topics 和已有 questions。
- 这些操作创建并返回新 package，不修改传入的 `StudyPackage`。

## 示例课程与责任边界

`data/sample_course.json` 可由调用方加载，并用 `StudyPackage.model_validate(...)` 校验。示例课程包含 3 道题；这只是演示数据，不保证满足任意请求的组卷数量。加载示例课程的操作由 A 提供；B 的 Gemini 服务不会自动加载示例数据，也不会操作 UI。

## 验证记录

- Gemini 与文档服务测试使用离线模拟客户端；Tutor 测试不调用真实 API。
- 曾真实调用成功：TXT 两学科知识点生成、PDF 知识点及页码引用、按 TXT 确认范围生成题目。
- 真实关系生成请求曾返回 HTTP 503；关系生成成功路径尚待真实环境验证。
- UI 流程和跨模块端到端集成尚未验证。
