# 本地插件（6.1）

宿主扫描本目录下一层的 `plugin.json`，默认只显示信息，**不会执行插件代码**。启用由宿主自己的配置文件授权，不能由聊天、插件 manifest 或 HTTP 请求自行启用。

管理面板现在提供“扩展”页：查看本地目录、版本、加载失败/旧版回退状态，以及随应用分发的内置扩展。第一项为纯本地的“文本小工具”，统计字符、行、拉丁单词和汉字数量，不访问文件、网络或模型。此目录只包含应用维护者打包的固定包，不是开放远程市场。

安装默认关闭。宿主需先创建已有、可写、无符号链接/junction 的独立目录，设置 `COMPANION_PLUGINS_DIR` 和 `COMPANION_PLUGIN_INSTALL_ENABLED=true`，重启后才开放管理员安装。通过 `GET /actions/plugins/catalog` 浏览，`POST /actions/plugins/catalog/{id}/install` 提交目录中的 `sha256`；页面在安装前显示包、版本和能力说明。未知名称、版本变化、已存在的同名目录、链接目录和预先启用的同名授权均拒绝。写入中断保留无效目录供宿主检查，不覆盖或自动重试。

安装不修改授权文件，也不执行 setup。宿主审阅后按下文显式授权用户，扫描器才加载。若宿主同时更改授权，则按宿主最新决定处理。HTTP 请求取消会等磁盘线程结束，重试依然不能覆盖。远程下载、任意代码上传、界面编辑执行授权和在线第三方市场不在此入口范围内。

每个插件使用独立目录，版本 1 入口固定为 `plugin.py`，元数据形如：

```json
{"api_version":1,"id":"example_echo","name":"回声示例","version":"1.0.0","entrypoint":"plugin.py"}
```

入口提供 `async def setup(api)`，调用 `api.add_tool(name, description, json_schema, async_handler, read_only=True)`；handler 接收 `(arguments, context)`，返回 `ActionResult`。`context` 的用户/会话/轮次/操作编号由宿主绑定，模型不能通过 arguments 覆盖。参考 `example_echo/plugin.py`。

本地私有授权配置（建议命名为已忽略的 `companion_plugins_config.json`）：

```json
{"plugins":[{"id":"example_echo","enabled":true,"allowed_users":["your-local-user"],"allow_mutations":false,"timeout_seconds":10}]}
```

设置 `COMPANION_PLUGINS_CONFIG_FILE` 指向此文件；可用 `COMPANION_PLUGINS_DIR` 改变目录。`allowed_users` 必须显式列出用户，不支持 `*`；修改类工具还需 `allow_mutations=true`。这些设置属于可信宿主，现有用户身份/鉴权体系的边界仍适用。不要把密钥放入 manifest、源码、描述或错误信息。

可用入口：`GET /actions/plugins` 查看不含路径/授权内容的状态；`ToolCatalog.tools_for/call` 发现/调用，`POST /actions/tasks` 的实际规划器可使用当前用户被授权的插件工具。工具名为 `plugin_<id>__<tool>`。不提供远程包安装、代码上传、聊天启用或修改授权的接口。

每秒检测一次 manifest、入口源码及授权内容的摘要；相同秒内同长度修改也能重载，不使用旧 pyc。候选初始化成功后原子切换；旧调用完成后清理旧版本，未开始的旧请求被拒绝。初始化失败时保留权限未变的旧版本，状态显示失败；授权变化后不保留旧权限。相同失败版本不会反复执行初始化，修改源码/manifest/配置后才重试。禁用、删除或非法宿主配置会撤销工具，排队请求不重放。

资源请通过 `api.resources` 的 `AsyncExitStack` 管理，先登记清理再分配资源。setup 和资源关闭始终位于同一工作任务，兼容要求同任务退出的异步取消域。调用队列最多 32、工具最多 32、源码最多 1 MiB、参数/结果最多 64 KiB，调用有超时。修改类操作中断/异常返回 `outcome_unknown`，不会自行重试。

这是可信本机 Python 扩展，和宿主具有同等权限；不是不可信代码沙箱，CPU 死循环和拒绝取消的代码不能在同一进程内被强制隔离。版本 1 只热加载单入口模块；第三方依赖的安装/升级及其模块缓存需要宿主管理并重启，不递归加载任意子目录。远程扩展优先使用已有 MCP 接口。此范围不替代 7.1 设备沙箱或 7.3 鉴权与数据控制。

验证：真实本地模块/资源作用域回归、运行中旧调用完成、新代码切换、默认禁用发现、身份/权限/参数限制、失败回退、撤销、关闭与修改超时不重放。实际方舟规划器通过 `/actions/tasks` 两次调用隔离的示例扩展，第二次已执行热更后的源码；撤销与跨用户隔离通过。报告在忽略目录 `output/qa/plugins-result.json`。
