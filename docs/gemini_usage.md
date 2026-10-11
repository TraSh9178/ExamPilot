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

`extract_document(file_bytes, filename)` 接受扩展名不区分大小写的 `.txt`、文字型 `.pdf` 和 `.pptx` 文件。TXT 按 UTF-8（兼容 BOM）读取；PDF 使用 PyMuPDF 逐页提取；PPTX 使用 `python-pptx` 提取文本框、表格和分组中的文字。文件大小上限为 5 MiB，提取文本上限为 50,000 个字符，超过上限会返回失败而不会截断。

PDF 页码从 1 开始；PPTX 的 `pages`/`sources` 页码表示从 1 开始的幻灯片号。PDF 和 PPTX 的 `pages` 都保留空白页，`sources` 只包含有文字的页/幻灯片。TXT 没有真实页码，不返回 `pages` 字段，`sources` 中 `page` 为 `None`。图片 OCR、幻灯片备注和旧版 `.ppt` 均不支持；扫描 PDF 或只有图片的 PPTX 不支持 OCR。

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

- Gemini 与文档两组测试合计 `108 passed`；测试使用离线模拟客户端。
- 曾真实调用成功：TXT 两学科知识点生成、PDF 知识点及页码引用、按 TXT 确认范围生成题目。
- 真实关系生成请求曾返回 HTTP 503；关系生成成功路径尚待真实环境验证。
- UI 流程和跨模块端到端集成尚未验证。
