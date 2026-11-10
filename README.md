# Fenrir 专利写作助手 v3.5.16

基于 PyQt5 的专利申请文件撰写辅助工具，面向专利代理师/工程师，集成多 Tab 编辑、附图标记管理、结构导航、文本校验、OCR、AI 辅助撰写等功能。

## 运行环境

- Windows x64（依赖 win32api / win32gui）
- Python 3.8+（开发环境 3.15）
- 依赖：`PyQt5 qtawesome requests opencv-python numpy pywin32`

```
pip install PyQt5 qtawesome requests opencv-python numpy pywin32
python main.py
```

## 项目结构

```
FenrirV3.5/
├── main.py                 # 根目录启动器（设置 sys.path + CWD 后运行 src/main.py）
├── src/                    # 全部 Python 模块
│   ├── main.py             # 主窗口、Ribbon 工具栏、多 Tab 编辑器、结构导航、文本校验
│   ├── draft_store.py      # 统一草稿存储（data/workspace.json），含专利模板 TEMPLATES
│   ├── completer_popup.py  # 输入法式横向补全弹窗（每页 4 项，←→ 翻页）
│   ├── word_features.py    # 查找替换对话框（含批量替换页签 Ctrl+Shift+H）
│   ├── design_adjust_service.py  # 附图外观调整、XML 修改、特征关系分析
│   ├── image_support.py    # 图片导入/保存
│   ├── web_search_panel.py # 网页检索面板
│   ├── resources.py        # 预编译正则与公共工具函数
│   └── x_*.py              # 辅助面板/图标工具
├── data/
│   ├── workspace.json       # 草稿、标签名、用户词库、对比窗口数据
│   └── images/             # 用户插入的附图缓存
└── README.md
```

## 主要功能

- **多 Tab 编辑器**：最多 30 份文档，拖拽排序、双击重命名、Ctrl+S 保存
- **Ribbon 工具栏**：开始 / 附图 / 工具等页签，按钮透明化与面板同色
- **附图标记管理**：自动提取"名称(标号)"，双击高亮全文相同特征，多色区分
- **文本校验**：术语一致性（标号/名称错配高亮）、专利法 26 条 3/4 款空泛词统计
- **一键格式化（F5）/ 重置格式（F6）**：自动加粗段落标题、步骤编号、区别特征等
- **批量替换**：整合到查找替换对话框第三页签（Ctrl+Shift+H）
- **专利模板**：OA 答复、说明书、权利要求、复审请求、无效宣告，Alt+1~5 一键插入
- **专利检索**：右键框选专利号 → 默认跳转专利汇（iprdb.com）
- **AI 辅助**：扩写（Alt+F）、润色（Alt+E）、续写（Alt+W）、补全 `<>`（Alt+Q）、概念查询（Alt+R）、翻译（Alt+T）
- **附图工具**：拖拽插入图片、外观尺寸调整、XML 修改、特征关系分析、OCR
- **对比窗口**：主窗口与对比窗口共享同一份 workspace.json，互不覆盖

## 快捷键

| 快捷键 | 功能 |
|---|---|
| Ctrl+F | 查找替换 |
| Ctrl+Shift+H | 批量替换 |
| Ctrl+S | 保存 |
| Ctrl+Z / Ctrl+Y | 撤销 / 重做 |
| Ctrl+~ | 关键词联想 |
| F1 / F2 / F3 / F4 | 帮助 / 扩展工具 / 特殊符号 / AI 接口设置 |
| F5 / F6 | 一键格式化 / 重置默认格式 |
| Alt+1~5 | 插入 OA / 说明书 / 权利要求 / 复审 / 无效模板 |
| Alt+F / E / W / Q / R / T | 扩写 / 润色 / 续写 / 补全<> / 概念查询 / 翻译 |

## 更新日志（精简）

### v3.5.15
- 顶部工具栏重排：附图编辑、外观尺寸调整、权利要求分析、EUREKA、复审无效
- 修复拖拽/批量导入附图时崩溃的 BUG
- 简化算法，提升文档处理速度
- 右键新增专利检索（默认专利汇）
- 代码整理：HTML 模板、分词词典、格式词表全部内嵌为常量，删除外部 data/*.txt 与 UI/*.png 依赖
