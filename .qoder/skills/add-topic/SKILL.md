---
name: add-topic
description: 向苏格拉底学习大纲添加新知识点。修改syllabus.py中的默认大纲并部署生效。当用户说"添加知识点""补充原理""加个新topic"时触发。
---

# 添加新知识点到学习大纲

## 执行步骤

### Step 1: 确认知识点信息
如果用户未完整提供，需确认：
- **名称**（必须）：如"大数定律"
- **领域**：物理/化学/生物/数学/统计学/经济/心理/哲学/计算机/思维方法
- **描述**：一句话说明原理内容

### Step 2: 编辑两处
**代码默认大纲** — `e:\GitCode\LearningAgent\learning\syllabus.py`
在 `DEFAULT_SYLLABUS` 列表末尾添加：
```python
{"id": "tXX", "name": "知识点名称", "domain": "领域", "desc": "描述"},
```

**缓存文件** — `e:\GitCode\LearningAgent\data\syllabus.json`
在 JSON 数组末尾追加对应条目（缓存优先于代码加载，不更新缓存则不会生效）。

- id 递增，查看列表中最后一个 id 的数字 +1
- 如果是新领域，同步更新 `SYLLABUS_GENERATION_PROMPT` 中的领域列表和分类枚举

### Step 3: 部署生效
执行 `/deploy` 技能重启服务。

### Step 4: 确认
告知用户新知识点已添加，可以通过"学习 xxx"开始学习。
