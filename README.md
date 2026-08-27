# AgentRun企业化A2A部署

本目录是与原始`a2a/demo`隔离的AgentRun部署实现。它构建四个独立的
Linux/AMD64镜像，并在AgentRun中创建四个一一对应的Managed AgentRuntime：

- `a2a-policy-agent`
- `a2a-research-agent`
- `a2a-provider-agent`
- `a2a-concierge-agent`

## 快捷入口

- [AgentRun控制台（华东1/杭州）](https://functionai.console.aliyun.com/cn-hangzhou/agent/runtime/agent-list)
- [AgentRun官方文档](https://help.aliyun.com/zh/agentrun/)
- [ACR `agent-njd/audit`自动构建](https://cr.console.aliyun.com/repository/cn-hangzhou/agent-njd/audit/build)

镜像是存放在ACR中的应用制品；Managed AgentRuntime是AgentRun云上负责拉取
镜像、启动实例、扩缩容、健康检查、版本和Endpoint的托管运行资源。两者不是
同一个概念。本方案的映射是：

| ACR镜像 | AgentRun资源 |
| --- | --- |
| `audit:policy-<tag>` | `a2a-policy-agent` Runtime |
| `audit:research-<tag>` | `a2a-research-agent` Runtime |
| `audit:provider-<tag>` | `a2a-provider-agent` Runtime |
| `audit:concierge-<tag>` | `a2a-concierge-agent` Runtime |

云端只启用阿里云ARMS Python探针发行包。镜像通过`aliyun-bootstrap`下载并
安装官方探针；该发行包内部已经包含`aliyun-loongsuite-instrumentation-*`
等LoongSuite/OpenTelemetry组件，因此不再叠加安装第二套LoongSuite、社区
`opentelemetry-instrument`或旧Demo的`sitecustomize.py`。

## 设计要点

```text
AgentRun Endpoint
       │
       ▼
concierge AgentRuntime
   │          │          │ A2A + W3C trace context
   ▼          ▼          ▼
policy     research    provider AgentRuntime
   └──────────┴──────────┘
               │ aliyun-instrument
               ▼
        AgentRun Observability / ARMS
               │ SearchTraces + GetTrace
               ▼
        Windows本地JSON归档
```

企业部署改进：

- 服务启动不连接LLM或下游Agent，避免冷启动和发布探测失败。
- LLM客户端及concierge依赖在首个业务请求中延迟初始化。
- 统一监听`0.0.0.0:9000`。
- Agent Card根据反向代理头动态生成公开URL，也支持`PUBLIC_BASE_URL`覆盖。
- 提供`/healthz`存活检查与`/readyz`配置检查。
- 阻塞式SDK调用放入工作线程，避免阻塞ASGI事件循环。
- 增加不记录提示词/医疗内容的A2A业务Span。
- JSON结构化日志，ARMS启用日志关联后可带`trace_id/span_id`。
- 镜像以非root用户运行，本地Compose启用只读根文件系统和最小权限。
- 四个镜像只安装各自Agent所需的直接依赖，可独立发布和回滚。
- 密钥放在被Git忽略的`.env.local`中，Runtime YAML只在临时目录渲染。

## 目录

```text
aliyun-dev/
├── docker/
│   ├── Dockerfile
│   └── compose.local.yml
├── requirements/
│   ├── common.txt
│   ├── policy.txt
│   ├── research.txt
│   ├── provider.txt
│   ├── concierge.txt
│   └── trace-export.txt
├── runtime/templates/
│   ├── leaves.yaml.tmpl
│   └── concierge.yaml.tmpl
├── scripts/
│   ├── Build-Images.ps1
│   ├── Deploy-Runtimes.ps1
│   ├── Export-Traces.ps1
│   ├── Render-Runtime.ps1
│   └── Start-Local.ps1
├── src/agentrun_app/
├── tests/
└── tools/
```

## 一、Windows开发兼容性

需要：

- Windows 10/11 x86_64；
- Docker Desktop，启用WSL2和Linux containers；
- Docker Buildx；
- Python 3.11或3.12；
- AgentRun CLI Windows版本；
- 可访问的阿里云ACR、AgentRun和ARMS账户。

AgentRun CLI安装：

```powershell
irm https://raw.githubusercontent.com/Serverless-Devs/agentrun-cli/main/scripts/install.ps1 | iex
agentrun --version
```

本机`C:\msys64\mingw64\bin\ar.exe`是GNU归档工具，与AgentRun的`ar`短命令
冲突。因此本项目所有脚本都调用完整命令`agentrun`，不要调用`ar`。

如果PowerShell禁止脚本，可以在当前进程中临时放开：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

或者每次使用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Local.ps1 -Build
```

## 二、本地开发

```powershell
cd "D:\deskcopy\agent audit\aliyun-dev"
```

仓库已经生成被Git忽略的`.env.local`模板。填写其中的`DEEPSEEK_API_KEY`，然后：

```powershell
.\scripts\Start-Local.ps1 -Build
```

本地开发不会启动ARMS探针，避免污染云端Trace；云端镜像仍然保留ARMS启动命令。

检查存活和Agent Card：

```powershell
curl.exe http://localhost:19090/healthz
curl.exe http://localhost:19090/readyz
curl.exe http://localhost:19090/.well-known/agent-card.json

curl.exe http://localhost:19091/.well-known/agent-card.json
curl.exe http://localhost:19092/.well-known/agent-card.json
curl.exe http://localhost:19093/.well-known/agent-card.json
```

调用concierge：

```powershell
python .\tools\invoke_a2a.py `
  http://localhost:19093 `
  "说明糖尿病症状、保险覆盖，并找Austin附近的医生。"
```

停止：

```powershell
.\scripts\Start-Local.ps1 -Down
```

## 三、构建并推送四个Linux/AMD64镜像

本项目镜像使用阿里云官方示例同款Python 3.11.14基础镜像。ARMS当前兼容约束为Python 3.8～3.12、
`protobuf>=3.20,<6`、`opentelemetry-api<=1.35`。

ARMS探针不是AgentRun专属且不可下载的黑盒：Dockerfile中的
`pip install aliyun-bootstrap`和`aliyun-bootstrap -a install`会在构建期下载
官方探针及其LoongSuite组件。运行时统一通过`aliyun-instrument`启动，不需要
另外安装一个名为LoongSuite的并行探针。

先登录ACR，再填写`.env.local`中的`AGENTRUN_IMAGE_REGISTRY`、
`AGENTRUN_IMAGE_TAG`和四个`AGENTRUN_*_IMAGE`。构建四个本地镜像：

```powershell
.\scripts\Build-Images.ps1
```

推送四个镜像到ACR：

```powershell
.\scripts\Build-Images.ps1 -Push
```

也可单独构建，例如`.\scripts\Build-Images.ps1 -Agent Policy`。

如果使用ACR个人版绑定GitHub自动构建，不需要执行本地构建和push。按照
[`runtime/ACR_AUTO_BUILD.md`](runtime/ACR_AUTO_BUILD.md)配置四条规则；GitHub
分支更新后，ACR会使用本目录中的四个`Dockerfile.*`分别生成四个镜像版本。

脚本为policy、research、provider、concierge分别构建镜像，强制
`--platform linux/amd64`，并在本地构建后检查镜像平台。

镜像构建上下文就是`aliyun-dev`目录，代码、依赖、Dockerfile和演示数据均已
自包含，适合由ACR从GitHub检出后直接构建。

## 四、配置AgentRun CLI

使用拥有最小必要权限的RAM用户或角色。首次配置示例：

```powershell
agentrun config set access_key_id YOUR_ACCESS_KEY_ID
agentrun config set access_key_secret YOUR_ACCESS_KEY_SECRET
agentrun config set account_id YOUR_ACCOUNT_ID
agentrun config set region cn-hangzhou
```

需要完成AgentRun官方要求的服务角色授权，并为调用身份授予
`AliyunAgentRunFullAccess`或等价的最小自定义权限。

## 五、部署三个叶子Runtime

填写`.env.local`。构建和部署脚本会自动加载它；当前PowerShell进程中已设置的
同名变量优先于文件值。不要把真实值写入Runtime模板：

```dotenv
AGENTRUN_POLICY_IMAGE=registry.cn-hangzhou.aliyuncs.com/ns/a2a-policy-agent:arms-v1
AGENTRUN_RESEARCH_IMAGE=registry.cn-hangzhou.aliyuncs.com/ns/a2a-research-agent:arms-v1
AGENTRUN_PROVIDER_IMAGE=registry.cn-hangzhou.aliyuncs.com/ns/a2a-provider-agent:arms-v1
DEEPSEEK_API_KEY=...
ARMS_LICENSE_KEY=...
```

只验证清单：

```powershell
.\scripts\Deploy-Runtimes.ps1 -Phase Leaves -RenderOnly
```

正式创建/更新：

```powershell
.\scripts\Deploy-Runtimes.ps1 -Phase Leaves
```

脚本执行：临时渲染→`agentrun runtime render`→`agentrun runtime apply`→删除
临时敏感文件。

## 六、取得A2A地址并部署concierge

三个叶子Runtime变为`READY`、Endpoint变为`ACTIVE`后，在AgentRun控制台复制
各自A2A基础地址。必须验证：

```text
<POLICY_A2A_URL>/.well-known/agent-card.json
<RESEARCH_A2A_URL>/.well-known/agent-card.json
<PROVIDER_A2A_URL>/.well-known/agent-card.json
```

设置基础地址，不要设置到JSON文件本身：

```powershell
$env:POLICY_A2A_URL = "https://..."
$env:RESEARCH_A2A_URL = "https://..."
$env:PROVIDER_A2A_URL = "https://..."

.\scripts\Deploy-Runtimes.ps1 -Phase Concierge
```

如果AgentRun入口没有正确传递`X-Forwarded-Host/Proto/Prefix`，在对应模板的
`spec.env`中显式增加：

```yaml
PUBLIC_BASE_URL: "https://实际A2A基础地址"
```

然后重新apply生成新版本。

## 七、开启ARMS Trace

AgentRun CLI当前Runtime YAML没有暴露控制台的`Tracing Analysis`开关。首次部署
后，需要在四个Runtime的高级配置中开启该开关。

每个Runtime已经配置不同的应用名：

```text
a2a-policy-agent
a2a-research-agent
a2a-provider-agent
a2a-concierge-agent
```

容器日志应出现`ARMS Agent started successfully`。调用concierge后，在：

```text
AgentRun → Agent详情 → Observability → Tracing Analysis
```

验证同一个Trace ID中包含：

```text
concierge → policy/research/provider → DeepSeek
```

最低通过标准：4个A2A业务Span和跨Runtime HTTP Span完整。OpenAI/LangChain
应出现LLM语义Span；Anthropic兼容端点和BeeAI若只显示HTTP Span，记录为探针
覆盖差异，不判定AgentRun部署失败。

## 八、下载ARMS Trace到Windows

为本地工具创建独立环境：

```powershell
py -3.11 -m venv .venv-trace
.\.venv-trace\Scripts\Activate.ps1
pip install -r .\requirements\trace-export.txt
```

设置只读RAM凭据：

```powershell
$env:ALIBABA_CLOUD_ACCESS_KEY_ID = "..."
$env:ALIBABA_CLOUD_ACCESS_KEY_SECRET = "..."
$env:AGENTRUN_REGION = "cn-hangzhou"
```

下载最近60分钟的concierge Trace：

```powershell
.\scripts\Export-Traces.ps1 -ServiceName a2a-concierge-agent -Minutes 60
```

按已知 Trace ID 直接下载：

```powershell
.\scripts\Export-Traces.ps1 -TraceId e500ef9f554865297d2a3e3f2df264c6 -Minutes 180
```

输出：

```text
trace-export/
├── index.json
├── <trace-id-1>.json
└── <trace-id-2>.json
```

工具先调用`SearchTracesByPage`（SDK不提供时回退`SearchTraces`），再使用
`GetTrace`分页保存完整Span响应。它不会把Trace自动导入本地Jaeger。

## 九、安全注意事项

- 不提交`.env.local`、渲染后的Runtime YAML或Trace导出目录。
- 不在Dockerfile、镜像层或命令行参数中写密钥。
- ARMS Trace可能包含模型请求/响应；涉及医疗信息时先确认采集和脱敏策略。
- `tools/export_arms_traces.py`不打印凭据，但导出的Span标签仍可能含敏感数据。
- POC使用公网Endpoint；生产环境应评估VPC、私网Endpoint、安全组和最小权限。
- `InMemoryTaskStore`适合当前无状态验证；需要长任务恢复时应替换成外部持久化存储。

## 十、已知平台步骤

以下步骤依赖你的阿里云账户，无法由仓库静态完成：

1. 创建/授权AgentRun服务角色。
2. 创建ACR仓库并登录。
3. 获取ARMS LicenseKey。
4. 在控制台开启四个Runtime的Tracing Analysis。
5. 确认平台生成的A2A Endpoint路径和鉴权策略。
