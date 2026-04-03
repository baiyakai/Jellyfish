---
title: "后端重构阶段总结：路由瘦身、Service 分层与测试补强"
date: 2026-04-03
description: "Jellyfish 后端第一阶段工程化整理总结，包括 route -> service 重构、响应壳统一、错误文案统一与测试体系补强。"
---

这一阶段的后端整理，重点不是继续堆功能，而是把已经基本稳定的主流程真正收成一套**可维护、可验证、可继续演进**的结构。

如果用一句话概括，这一轮完成的是：

- **把胖路由拆薄**
- **把核心业务下沉到 service**
- **把接口返回和错误风格收拢**
- **把测试入口和回归护栏补齐**

## 这轮为什么要做

在整理开始之前，后端虽然已经具备比较完整的业务能力，但也有几个很典型的问题：

- 部分 API 路由承载了过多业务逻辑
- 通用校验、CRUD、错误文案存在大量重复
- 成功响应、删除响应、异常响应的风格不够一致
- 一些复杂链路已经能用，但缺少足够测试护栏

这些问题在原型阶段可以接受，但如果继续往上叠功能，后续维护成本会越来越高。

所以这一阶段的目标很明确：

- 先把结构理顺
- 先把边界厘清
- 先把验证体系补上

## 结构上发生了什么变化

### 1. Route 更薄了

`app/api/v1/routes/` 现在更明确地只做这些事：

- 接收参数
- 依赖注入
- 调 service
- 包装 `ApiResponse`

复杂业务规则、跨实体校验、任务编排、文件与存储处理，已经不再继续堆在 route 文件里。

### 2. Common 层建立起来了

这一轮补了 `services/common/`：

- `validators.py`
- `crud.py`
- `errors.py`

这一层的作用很直接：

- 收掉高频样板代码
- 统一错误风格
- 减少 route 与 service 里的重复实现

### 3. Studio 主链路开始成型

`services/studio/` 现在已经承接了 Studio 侧大部分核心逻辑，包括：

- `shots`
- `shot_assets`
- `shot_details`
- `shot_dialogs`
- `shot_frames`
- `shot_character_links`
- `script_division`
- `files`
- `image_task_validation`
- `image_task_references`
- `image_task_prompts`
- `image_task_runner`

这意味着：

- 分镜主链路
- 文件链路
- 图片任务链路

都已经从“胖路由”逐步收成了“路由入口 + service 实现”的结构。

### 4. LLM / Film 侧也一起收了

这轮没有只处理 Studio，还顺手把另外两条明显偏胖的链路也收了一轮：

- `services/llm/manage.py`
- `services/film/generated_video.py`
- `services/film/shot_frame_prompt_tasks.py`

也就是说，这一轮不是局部美化，而是把后端里最明显的几块结构债一起往前推了一步。

## `entities.py` 这块也做了拆分

`entities.py` 原来是比较典型的大文件技术债。

这一轮把它逐步拆成了下面几层：

- `entity_crud.py`
- `entity_images.py`
- `entity_existence.py`
- `entity_specs.py`
- `entity_thumbnails.py`
- `entities.py`（协调层）

现在 `entities.py` 已经不再自己承载全部实现，而是开始更像一个协调入口。

这对后续继续维护：

- 主资源 CRUD
- 图片 CRUD
- 名称存在性检测

都会轻松很多。

## 接口规范做了哪些统一

### 响应壳统一

这一轮已经把后端接口成功响应统一到了 `ApiResponse`：

- 创建成功：`created_response(...)`
- 普通成功：`success_response(...)`
- 空响应：`empty_response()`
- 分页成功：`paginated_response(...)`

这样做的好处很直接：

- 创建接口不再各写各的 `201`
- 删除接口不再混用 `204` 和空 body
- 前端消费方式更稳定

### 错误文案统一

这一轮新增并逐步接入了这些公共错误模板：

- `entity_not_found(...)`
- `entity_already_exists(...)`
- `required_field(...)`
- `invalid_choice(...)`
- `not_belong_to(...)`
- `relation_mismatch(...)`

当然，少量带上下文信息、对排障有帮助的错误文案还是保留了手写形式，没有强行抽象。

## 测试这轮补到了什么程度

这轮整理里，测试不是最后补的，而是跟着重构同步往前推的。

### Service 层测试

已经覆盖到：

- common helpers
- llm 管理
- 镜头角色关联
- 剧本分镜写库
- 文件服务
- 视频生成
- 分镜帧提示词任务
- `image_task_*`

### API 层测试

已经覆盖到：

- `prompts`
- `llm/providers`
- `projects / chapters / shots`
- `shot-details / shot-dialog-lines / shot-frame-images`
- `files`
- `task_status`
- `shot_character_links`
- `image_tasks`
- `generated_video`
- `tasks_images`
- `entities`

### 当前结果

这一轮结束时，从仓库根目录执行：

```bash
uv run pytest backend/tests -q
```

结果为：

```text
125 passed
```

而且根目录与 `backend/` 目录两种入口都已经可以稳定运行，不再出现 async 用例被误跳过的假通过问题。

## 这轮的直接收益

这轮整理最直接的收益有四个：

### 1. 代码更容易读了

路由文件终于更像路由，service 文件也开始有明确边界。

### 2. 新增功能更容易落位

后面再加逻辑时，更容易判断：

- 哪些留在 route
- 哪些放到 service
- 哪些抽到 common

### 3. 前后端接口协作更稳定

响应壳和错误风格统一后，前端处理成功/失败返回的成本会更低。

### 4. 后续迭代更有安全感

测试护栏已经立起来了，后面继续整理或继续做功能时，回归风险会小很多。

## 当前还保留的技术债

这一轮不是终局，仍然有一些刻意保留或尚未完全收口的点：

- `dependencies.py` 里还有一批直接手写的 `HTTPException`
- 少量错误文案仍然保留了上下文写法
- 个别 route / service 的命名还可以继续统一
- `files.py` 里还保留了少量中文错误文案

另外，`entities.py` 虽然已经拆成了：

- `entity_crud.py`
- `entity_images.py`
- `entity_existence.py`
- `entity_specs.py`
- `entity_thumbnails.py`
- `entities.py`（协调层）

但它依然属于相对复杂的“通用实体服务”，后续还可以继续：

- 降低单文件体积
- 提升类型标注精度
- 继续收敛内部命名风格

不过这些已经不是“结构阻塞项”了，更像第二轮清理项。

## 下一步会做什么

在这一轮完成之后，后续更适合进入下面两个方向之一：

### 1. 回到产品侧优化

也就是最开始规划里的重点：

- 交互性优化
- 提示词优化
- 剪辑功能补强

### 2. 继续做低风险工程化清理

例如：

- 第二轮文案与命名统一
- 剩余历史文件拆分
- 补更多细粒度测试

整体判断是：

**后端已经从“原型堆叠阶段”进入“可持续维护阶段”了。**

这也是这一轮最重要的成果。

## 这一轮的阶段性结论

如果把这一轮的成果再压缩成一句话，它真正完成的是：

- **分层变清楚了**
- **接口变统一了**
- **错误风格开始收敛了**
- **测试护栏补起来了**

这意味着后续不管你是继续做：

- 数据模型标准化
- 交互性优化
- 提示词优化
- 剪辑相关能力补强

后端都已经有了一个更稳的基础。

## 下一步建议

接下来更适合切换到两类工作之一：

### 1. 产品向优化

- 交互性优化
- 提示词优化
- 剪辑能力补强

### 2. 第二轮工程化清理

- 继续拆剩余历史大文件
- 收敛少量残留错误文案和命名差异
- 补更多细粒度测试

如果按当前收益来看，下一步最值得优先切到：

**交互性优化。**
