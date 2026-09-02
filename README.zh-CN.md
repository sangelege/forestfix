# ForestFix

> 一个面向 Python 仓库的、以测试证据为核心的补丁验证系统。

[English](README.md) · **简体中文**

ForestFix 的目标不是让 Agent 看起来会写代码，而是回答一个更重要的问题：

> **这个修复补丁，是否真的修好了问题，并且没有越权或破坏其他功能？**

它把候选补丁放进独立的 Git worktree，检查修改范围，重新运行原始失败命令和回归命令，最后生成带执行证据的 JSON 报告。

## 当前版本能做什么

当前是 **v0.2 可验证产品核心**，已经实现：

- 使用 Pydantic 校验不可变的 `TaskSpec`；
- 检查补丁格式、允许路径和禁止路径；
- 检查 rename 的源路径和目标路径；
- 检测常见的测试作弊方式，例如 `skip`、`xfail`、`pytestmark`；
- 为每个候选创建独立的 Git worktree；
- 创建 worktree 和应用补丁时禁用 Git Hook；
- 使用参数数组执行命令，不经过 Shell；
- 对可执行文件做白名单和固定路径解析；
- 超时后终止整个进程组；
- 确认基线 Bug 可以复现；
- 确认候选补丁能让原始失败命令通过；
- 运行额外验收命令并记录退出码、输出和耗时；
- 并行验证多个相互独立的候选；
- 输出 `BaselineReport` 和 `VerificationReport`；
- SQLite 持久化任务、候选与验证报告；
- Hermes / Codex / Claude 打印模式 CLI Provider 适配；
- 将已通过候选应用到独立本地分支；
- FastAPI + 原生 JavaScript 产品控制台；
- 提供无需 API Key 的离线 Demo；
- 提供 `forestfix demo` 与 `forestfix serve` 命令。

## 还没有实现什么

以下仍属于后续阶段，默认不自动执行：

- GitHub Issue/CI 主动监听；
- 自动创建 Pull Request；
- 自动合并代码；
- 主动发现问题的 Agent；
- 已批准的共享能力库。

当前项目的设计顺序是：

> **先把验证器做可靠，再接入生成器。**

## 快速开始

需要 Python 3.12 和 Git。推荐使用 `uv`：

```bash
uv venv
uv pip install -e '.[dev,web]'
```

运行测试和静态检查：

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
```

## 离线 Demo

```bash
.venv/bin/forestfix demo
```

Demo 不需要模型或 GitHub API Key，会实际创建临时 Git 仓库并展示三种结果：

1. 基线代码确实能够复现 Bug；
2. 正确补丁通过原始复现命令；
3. 加入测试跳过标记的作弊补丁被策略层拒绝。

输出是 JSON，可以保存下来作为验证记录。

## 验证一个候选补丁

准备一个 TaskSpec JSON，例如：

```json
{
  "task_id": "parser-task",
  "repo_path": "/absolute/path/to/repository",
  "base_commit": "0123456789abcdef0123456789abcdef01234567",
  "reproduction_command": ["python3", "tests/test_parser.py"],
  "acceptance_commands": [
    ["python3", "tests/test_parser.py"],
    ["python3", "-m", "pytest", "-q"]
  ],
  "allowed_paths": ["src/parser/**", "tests/test_parser.py"],
  "denied_paths": ["pyproject.toml", ".github/**"],
  "candidate_count": 2,
  "timeout_seconds": 300,
  "network_access": false
}
```

然后执行：

```bash
.venv/bin/forestfix verify \
  --spec ./task.json \
  --patch ./candidate.patch \
  --candidate-id candidate-1 \
  --output ./report.json \
  --unsafe-local
```

验证流程是：

```text
检查 TaskSpec
    ↓
在基线 worktree 中确认 Bug 可以复现
    ↓
检查候选补丁的格式和路径
    ↓
在新的候选 worktree 中应用补丁
    ↓
再次运行原始复现命令
    ↓
运行所有验收命令
    ↓
输出 VerificationReport
```

如果原始复现命令在应用补丁后仍然失败，候选一定不会被标记为成功。

## 安全边界

`--unsafe-local` 不是普通的开发模式开关，而是一个明确的安全警告。

当前本地执行器：

- 不是 Docker 或操作系统级沙箱；
- 不能阻止代码访问宿主机网络；
- 不能完全阻止代码读取 worktree 外的宿主机文件；
- 不能隔离进程、内核资源和依赖安装脚本。

因此只能对你信任的 fixture 或本地项目使用：

```bash
--unsafe-local
```

不要对陌生 GitHub 仓库、恶意补丁或生产目录使用它。Git worktree 只解决候选之间的代码隔离，不等于安全隔离。

在实现容器级执行器之前，ForestFix 不宣称支持不可信代码执行。

完整说明见：[安全边界](docs/SECURITY.md)。

## Web 控制台

安装 Web 依赖并启动控制台：

```bash
uv pip install -e '.[web]'
.venv/bin/forestfix serve --unsafe-local
```

打开 `http://127.0.0.1:8000`。控制台可创建任务、运行基线、通过已安装 Provider 生成候选、查看证据，并将通过候选应用到独立本地分支。

当前接口：

### `GET /health`

返回服务健康状态：

```json
{
  "status": "ok",
  "service": "forestfix"
}
```

### `POST /inspect-patch`

只检查补丁格式、修改路径和测试作弊，不执行仓库代码：

```json
{
  "patch": "diff --git ...",
  "allowed_paths": ["src/**"],
  "denied_paths": ["pyproject.toml"]
}
```

API 提供健康检查、补丁检查、任务与候选管理、Provider 生成，以及显式应用分支接口。

## 设计理念

### 不让用户写长 Prompt

未来的任务入口应让用户选择：

- 任务类型；
- 复现命令；
- 允许修改的目录；
- 禁止修改的内容；
- 验收命令；
- 运行预算；
- 完成后的动作。

自然语言只用来补充现象，不应该承担验收标准。

### 不让 Agent 互相争论

Agent 之间不应该围绕同一份答案无限 push back。每个 Agent 应提交冻结的候选补丁，验证器统一检查：

```text
候选生成 → 独立验证 → 不合格淘汰 → 合格结果比较
```

### 知识库只保存证据

未来的能力库不会保存未经验证的聊天记录，而只保存带有以下信息的可复用能力：

- 适用范围；
- 输入和输出；
- 可执行实现；
- 正例和负例测试；
- 来源和版本；
- 历史成功率；
- 回滚方式。

## 代码结构

```text
src/forestfix/
├── api/           # FastAPI 产品控制台
├── domain/        # TaskSpec 与 CandidateRecord
├── orchestration/ # Provider → 验证 → 应用服务
├── policy/        # 补丁和路径策略
├── sandbox/       # Git worktree、执行器和分支应用
├── storage/       # SQLite 任务与候选持久化
├── verification/  # 基线、候选和报告流水线
├── web/           # HTML / CSS / JavaScript 控制台
├── demo_data/     # 安装 Wheel 后仍可运行的离线 Demo 数据
└── cli.py         # forestfix demo / serve / verify
```

## 文档

- [项目方案与路线图](docs/PROJECT.md)
- [当前架构](docs/ARCHITECTURE.md)
- [安全边界](docs/SECURITY.md)
- [贡献指南](CONTRIBUTING.md)
- [更新记录](CHANGELOG.md)

## 开发原则

新增功能时遵守：

1. 先写一个会失败的测试；
2. 再实现最小行为；
3. 运行全量测试和 Ruff；
4. 记录所有安全边界变化；
5. 不要用模型自评替代可执行证据。

## 许可证

当前仓库尚未选择开源许可证。在许可证文件加入之前，不要默认代码可以被重新分发或集成到其他项目中。
