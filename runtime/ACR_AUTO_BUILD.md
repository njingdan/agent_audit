# ACR个人版：GitHub自动构建四个Agent镜像

目标仓库：

```text
crpi-nm6lgaazs8hv7fi0.cn-hangzhou.personal.cr.aliyuncs.com/agent-njd/audit
```

## 构建结果

一次Git分支更新触发四条ACR规则：

```text
Dockerfile.policy    -> audit:policy-1.0.0
Dockerfile.research  -> audit:research-1.0.0
Dockerfile.provider  -> audit:provider-1.0.0
Dockerfile.concierge -> audit:concierge-1.0.0
```

四个tag对应四次独立Docker构建和四个不同的镜像digest。它们共用一个ACR
Repository，但不是同一个镜像。

## 前置条件

本项目把本地`aliyun-dev/`目录本身作为Git仓库根目录。因此GitHub仓库根目录
直接包含`Dockerfile.*`、`src/`、`requirements/`和`data/`。ACR只读取已经
push到GitHub的提交，看不到Windows工作区中尚未提交的文件。

## 四条构建规则

在`audit -> 构建 -> 添加规则`中添加以下四条规则。四条规则都选择“分支”，
Branch/Tag选择实际存放代码的分支（以下以`main`为例）。

| 规则 | 类型 | Branch/Tag | 构建上下文 | Dockerfile文件名 | 镜像版本 |
| --- | --- | --- | --- | --- | --- |
| policy | 分支 | `main` | `/` | `Dockerfile.policy` | `policy-1.0.0` |
| research | 分支 | `main` | `/` | `Dockerfile.research` | `research-1.0.0` |
| provider | 分支 | `main` | `/` | `Dockerfile.provider` | `provider-1.0.0` |
| concierge | 分支 | `main` | `/` | `Dockerfile.concierge` | `concierge-1.0.0` |

个人版普通构建规则的镜像版本输入框只接受字母、数字、点、下划线和连字符，
不要在这里填写`$version`。截图中的`tags:release-v$version`属于ACR内置规则，
不是普通自定义规则的输入格式。

保留“代码变更自动构建镜像”为开启。不要启用“不使用缓存”。四个镜像包含
相似的A2A/ARMS依赖层，保留缓存可以缩短构建时间。个人版单次构建上限为30分钟。

## 触发和验收

将当前仓库根目录的全部项目文件提交并push到上述分支。ACR随后自动启动四条规则。
构建完成后，`镜像版本`页面必须同时出现：

```text
policy-1.0.0
research-1.0.0
provider-1.0.0
concierge-1.0.0
```

四条记录均成功并具有digest后，才进入AgentRun部署阶段。

## 下一版本

当前个人版规则使用固定镜像版本。发布新版本前，先把四条规则的镜像版本改为
`policy-1.0.1`、`research-1.0.1`、`provider-1.0.1`和`concierge-1.0.1`，同时更新
`.env.local`中的四个镜像地址，再push代码。不要覆盖已用于生产的版本标签。
