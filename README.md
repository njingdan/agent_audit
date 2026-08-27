# AgentRun A2A Trace 验证 Demo

本项目用于验证四个 A2A Agent 部署到阿里云 AgentRun 后的服务发现、跨 Agent
调用和 ARMS Trace。四个 Agent 分别是：

| Agent | 作用 |
| --- | --- |
| `a2a-policy-agent` | 根据保险计划文档回答覆盖范围问题 |
| `a2a-research-agent` | 搜索并汇总公开健康资料 |
| `a2a-provider-agent` | 根据地区和专科查找医生 |
| `a2a-concierge-agent` | 发现并调用前三个 Agent，汇总最终回答 |

## 快捷入口

- [AgentRun控制台（华东1/杭州）](https://functionai.console.aliyun.com/cn-hangzhou/agent/runtime/agent-list)
- [AgentRun官方文档](https://help.aliyun.com/zh/agentrun/)
- [ACR `agent-njd/audit`构建页面](https://cr.console.aliyun.com/repository/cn-hangzhou/agent-njd/audit/build)

## 架构和资源关系

```text
用户 / A2A客户端
       │
       ▼
concierge公网Endpoint ──► concierge Runtime ──► 临时容器实例
       │
       ├── A2A发现/调用 ──► policy公网Endpoint   ──► policy Runtime
       ├── A2A发现/调用 ──► research公网Endpoint ──► research Runtime
       └── A2A发现/调用 ──► provider公网Endpoint ──► provider Runtime
                                      │
                                      ▼
                              ARMS / AgentRun Trace
```

- **ACR镜像**是不可运行的应用制品，包含代码、依赖和启动命令。
- **AgentRuntime**是持久的托管配置，记录镜像、环境变量、CPU、内存、协议、
  健康检查和Endpoint。缩容到0不会删除Runtime。
- **容器实例**是Runtime按请求创建的实际执行副本，可以扩容、回收和重新冷启动。
- **Endpoint**是AgentRun分配的数据面入口，把公网请求转发到Runtime当前可用的
  容器实例。

当前映射如下：

| ACR镜像 | AgentRun Runtime |
| --- | --- |
| `audit:policy-<tag>` | `a2a-policy-agent` |
| `audit:research-<tag>` | `a2a-research-agent` |
| `audit:provider-<tag>` | `a2a-provider-agent` |
| `audit:concierge-<tag>` | `a2a-concierge-agent` |

## 公网Endpoint和A2A发现

当前四个Runtime模板都配置了：

```yaml
network:
  mode: PUBLIC
endpoints:
  - name: default
    disablePublicNetworkAccess: false
```

因此四个Runtime都有公网Endpoint。当前部署的四个Agent Card地址均已验证返回
`HTTP 200`：

```text
<A2A基础地址>/.well-known/agent-card.json
```

这里的“A2A发现”是指：调用方已经知道某个Agent的基础地址，然后读取它的
Agent Card，得到Agent名称、能力和实际JSON-RPC调用地址。AgentRun不会让
concierge自动按Runtime名称搜索其他Agent；三个叶子地址必须通过
`POLICY_A2A_URL`、`RESEARCH_A2A_URL`和`PROVIDER_A2A_URL`明确提供给concierge。

Agent Card中的`url`必须是外部调用方真正能够访问的完整地址。应用优先使用
`PUBLIC_BASE_URL`；未配置时，才根据AgentRun反向代理传入的
`X-Forwarded-Proto`、`X-Forwarded-Host`和`X-Forwarded-Prefix`动态生成
该地址。两种方式都无法得到正确公网地址时，Agent Card可能错误地返回容器内部
地址或缺少`/agent-runtimes/.../endpoints/default/invocations`路径，后续A2A
调用就会失败。

“公网可发现”不等于“被公共目录收录”：不知道URL的人不会自动看到这些Agent。
但当前Demo没有配置Endpoint鉴权，知道或获得URL的人可能直接访问，因此不能把
Endpoint URL当作密钥。生产环境应增加鉴权，或改用VPC/PrivateLink和私网Endpoint。

## 实现说明

- `/healthz`只检查Web进程是否存活，供AgentRun判断是否需要重启实例；
  `/readyz`进一步检查必填环境变量，缺失配置时返回`503`。当前平台健康检查使用
  `/healthz`，因此模型或下游短暂不可用不会造成实例反复重启。
- policy、research和provider使用的部分SDK是同步阻塞调用。代码通过
  `asyncio.to_thread()`把这些调用放到工作线程，避免一个较慢的模型或搜索请求
  卡住ASGI事件循环，使健康检查和其他请求仍可被处理。
- `a2a.<agent>.execute`是代码在A2A执行器外层创建的业务Span，用来在Trace中明确
  标出实际执行了哪个Agent。Span只记录Agent名称、A2A方法、耗时和错误状态，
  不记录用户提示词或医疗内容；它与阿里云探针自动生成的HTTP、LLM和工具Span
  共同组成完整调用链。
- 日志使用JSON结构；ARMS启用日志关联后可带`trace_id`和`span_id`。
- 镜像以非root用户运行；可选的本地Compose配置还启用了只读根文件系统和
  最小权限。
- 四个镜像只安装各自Agent需要的直接依赖，可以分别构建、发布和回滚。
- `.env.local`被Git忽略；包含密钥的Runtime YAML只在临时目录生成，部署结束后
  自动删除。

云端镜像只启用阿里云ARMS Python探针发行包。`aliyun-bootstrap`在构建期安装
官方探针及其`aliyun-loongsuite-instrumentation-*`组件，容器通过
`aliyun-instrument`启动，不再叠加安装另一套LoongSuite或社区
`opentelemetry-instrument`。

## 目录说明

| 路径 | 用途 |
| --- | --- |
| `Dockerfile.policy`等四个根目录Dockerfile | ACR分别构建四个Agent镜像 |
| `.env.example` | 可提交的空配置模板；复制为被忽略的`.env.local`后填写真实值 |
| `docker/` | 可选的本地Docker/Compose验证配置，当前云端流程不依赖它 |
| `requirements/` | 公共依赖、四个Agent的独立依赖和Trace导出工具依赖 |
| `runtime/templates/` | 四个Managed AgentRuntime的YAML模板，不包含真实密钥 |
| `runtime/ACR_AUTO_BUILD.md` | ACR个人版自动构建规则说明 |
| `scripts/Render-Runtime.ps1` | 将`.env.local`安全渲染成临时Runtime YAML |
| `scripts/Deploy-Runtimes.ps1` | 按叶子Agent、concierge两个阶段部署Runtime |
| `scripts/Export-Traces.ps1` | 调用ARMS OpenAPI下载Trace |
| `scripts/Build-Images.ps1` | 本地构建的备用脚本；当前ACR构建流程不使用 |
| `src/agentrun_app/` | A2A服务器、四个Agent、配置、日志和业务Span实现 |
| `tools/invoke_a2a.py` | A2A JSON-RPC测试客户端 |
| `tools/export_arms_traces.py` | ARMS Trace查询和JSON归档工具 |
| `tests/` | 不依赖云资源的配置和服务测试 |

## 一、准备本地配置文件

`.env.example`只保存变量名、默认值和占位符，可以提交到Git。真实密钥只能填写
在被Git忽略的`.env.local`中：

```powershell
Copy-Item .env.example .env.local
```

需要填写的主要变量：

| 变量 | 何时填写 | 内容 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | 部署四个Runtime前 | DeepSeek API Key |
| `ARMS_LICENSE_KEY` | 开启ARMS Trace前 | ARMS Python应用接入页面提供的LicenseKey |
| `AGENTRUN_*_IMAGE` | ACR镜像构建完成后 | 四个镜像的完整ACR地址和版本Tag |
| `POLICY_A2A_URL`等三个叶子URL | 三个叶子Endpoint创建后 | 到`/invocations`为止的A2A基础地址 |
| `CONCIERGE_A2A_URL` | concierge Endpoint创建后 | concierge公开基础地址；用于修正Agent Card和测试 |
| `ALIBABA_CLOUD_ACCESS_KEY_ID/SECRET` | 下载Trace时 | 建议使用只读RAM用户的凭据 |

`DEEPSEEK_BASE_URL`、发现超时和重试次数已有默认值，通常不需要修改。
AgentRun CLI使用的账号、地域和部署凭据保存在CLI Profile中，不写进Runtime YAML。

## 二、使用ACR构建四个镜像

当前采用ACR个人版绑定GitHub构建，不需要在Windows上用Docker构建或手动push。
需要重新构建时，在ACR构建页面创建四条规则：

| 分支 | 构建上下文 | Dockerfile | 镜像版本示例 |
| --- | --- | --- | --- |
| `main` | `/` | `Dockerfile.policy` | `policy-1.0.0` |
| `main` | `/` | `Dockerfile.research` | `research-1.0.0` |
| `main` | `/` | `Dockerfile.provider` | `provider-1.0.0` |
| `main` | `/` | `Dockerfile.concierge` | `concierge-1.0.1` |

构建上下文是`/`，因为Git仓库根目录就是本项目根目录，Dockerfile需要读取同一
目录下的`src/`、`requirements/`和`data/`。创建规则后可以单击“立即构建”。

匹配`main`的规则会在每次提交到`main`时触发，并不会判断某个Agent的代码是否
实际发生变化。当前四条规则已经删除，普通README提交不会触发镜像构建；需要
发布新镜像时再临时创建规则即可。

## 三、配置AgentRun CLI

安装AgentRun CLI后，使用拥有最小必要权限的RAM用户或角色配置Profile：

```powershell
agentrun config set access_key_id YOUR_ACCESS_KEY_ID
agentrun config set access_key_secret YOUR_ACCESS_KEY_SECRET
agentrun config set account_id YOUR_ACCOUNT_ID
agentrun config set region cn-hangzhou
```

还需要完成AgentRun服务角色授权，并为调用身份授予
`AliyunAgentRunFullAccess`或等价的最小自定义权限。

## 四、部署三个叶子Runtime

先部署policy、research和provider，因为concierge部署时需要这三个Runtime的
公网A2A基础地址。

先检查渲染结果，不创建云资源：

```powershell
.\scripts\Deploy-Runtimes.ps1 -Phase Leaves -RenderOnly
```

正式创建或更新：

```powershell
.\scripts\Deploy-Runtimes.ps1 -Phase Leaves
```

脚本执行“临时渲染 → `agentrun runtime render` → `agentrun runtime apply` →
删除临时敏感文件”。等待三个Runtime变为`READY`、Endpoint变为`ACTIVE`。

## 五、配置发现地址并部署concierge

在AgentRun控制台复制三个叶子Endpoint的A2A基础地址，并填入`.env.local`：

```dotenv
POLICY_A2A_URL=https://.../agent-runtimes/a2a-policy-agent/endpoints/default/invocations
RESEARCH_A2A_URL=https://.../agent-runtimes/a2a-research-agent/endpoints/default/invocations
PROVIDER_A2A_URL=https://.../agent-runtimes/a2a-provider-agent/endpoints/default/invocations
```

分别验证Agent Card后部署concierge：

```powershell
curl.exe "<POLICY_A2A_URL>/.well-known/agent-card.json"
curl.exe "<RESEARCH_A2A_URL>/.well-known/agent-card.json"
curl.exe "<PROVIDER_A2A_URL>/.well-known/agent-card.json"

.\scripts\Deploy-Runtimes.ps1 -Phase Concierge
```

## 六、开启并验证ARMS Trace

AgentRun CLI的Runtime YAML目前没有暴露控制台的`Tracing Analysis`开关。首次
部署后，在四个Runtime的高级配置中开启该开关。四个ARMS应用名分别对应四个
Runtime名称。

容器日志应出现`ARMS Agent started successfully`。调用concierge后，在：

```text
AgentRun → Agent详情 → Observability → Tracing Analysis
```

验证同一个Trace ID中包含：

```text
a2a.concierge.execute
├── a2a.policy.execute
├── a2a.research.execute
└── a2a.provider.execute
```

同时应看到跨Runtime HTTP Span以及探针能够识别的LLM、Chain和Tool Span。
冷启动会增加首次请求总耗时，但不影响同一Trace中Agent调用关系的分析。

## 七、下载ARMS Trace到Windows

Trace导出工具需要独立Python环境：

```powershell
py -3.11 -m venv .venv-trace
.\.venv-trace\Scripts\Activate.ps1
pip install -r .\requirements\trace-export.txt
```

按已知Trace ID下载：

```powershell
.\scripts\Export-Traces.ps1 `
  -TraceId e500ef9f554865297d2a3e3f2df264c6 `
  -Minutes 180
```

输出保存在被Git忽略的`trace-export/`目录。工具调用`SearchTracesByPage`或
`SearchTraces`定位Trace，再通过`GetTrace`分页保存完整Span JSON；它不会自动
把Trace导入本地Jaeger。

## 八、安全注意事项

- 不提交`.env.local`、渲染后的Runtime YAML或Trace导出目录。
- 不在Dockerfile、镜像层或命令行参数中写密钥。
- 当前公网Endpoint适合Demo验证，不应直接作为生产鉴权方案。
- ARMS Trace可能包含模型请求/响应；涉及医疗信息时应确认采样和脱敏策略。
- `InMemoryTaskStore`适合当前无状态验证；需要长任务恢复时应替换成外部持久化存储。

## 九、控制台步骤

以下步骤依赖阿里云账号，需要在控制台完成：

1. 创建或授权AgentRun服务角色。
2. 创建ACR仓库；需要发版时创建构建规则并生成四个镜像。
3. 获取ARMS LicenseKey。
4. 在四个Runtime中开启`Tracing Analysis`。
5. 根据使用范围配置Endpoint鉴权、VPC或PrivateLink。
