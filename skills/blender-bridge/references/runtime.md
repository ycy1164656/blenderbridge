# 启动、发现与故障恢复

Windows 本机安装：仓库 `C:/dev/BlenderBridge`；可编辑源码 `src/blender_bridge`，稳定 Python 环境 `.venv/Scripts/python.exe`。MCP stdio 入口 `-m blender_bridge.mcp_server`。不需要模型 API Key。

Host 配置位于 `%USERPROFILE%/.blender-bridge/config.json`，可用 `BLENDER_BRIDGE_CONFIG` 指定。`doctor --json` 只读探测 Blender、Host 依赖、GPU、内存和输出空间；`capabilities --json` 区分操作契约、运行时能力探测与真实测试证据。核心依赖无神经图生模型。

```powershell
& C:/dev/BlenderBridge/.venv/Scripts/blender-bridge.exe discover
& C:/dev/BlenderBridge/.venv/Scripts/blender-bridge.exe --session <SESSION> catalog
& C:/dev/BlenderBridge/.venv/Scripts/blender-bridge.exe --session <SESSION> execute scene.inspect
& C:/dev/BlenderBridge/.venv/Scripts/blender-bridge.exe doctor --json
& C:/dev/BlenderBridge/.venv/Scripts/blender-bridge.exe capabilities --json
```

写入示例先把参数写入任务下的新 JSON 文件；避免 PowerShell 内联 JSON 引号问题：

```powershell
& C:/dev/BlenderBridge/.venv/Scripts/blender-bridge.exe --session <SESSION> execute mesh.vertices --revision <REV> --request-id <UUID> --args '@C:/path/to/edit.json'
& C:/dev/BlenderBridge/.venv/Scripts/blender-bridge.exe --session <SESSION> job <UUID>
```

## 运行方式

- 用户现有 Blender：Preferences → Add-ons → Blender Bridge 设置输出目录及读目录，然后 View3D 侧栏 Bridge → Start。默认不自启，不打开外网监听，不开启任意 Python。
- 新建本任务实例：`tools/start_blender.ps1 -Installed -OutputRoot <任务输出目录> -ReadRoot <参考图片目录>` 从已安装插件启动；开发源码测试才省略 `-Installed`。已有文件加 `-BlendFile <精确文件>`。默认后台实例；用户要求可见编辑器时加 `-Visible`。保留输出的 PID、启动时间、会话描述符和启动命令以核实归属。
- 发现文件在 `%USERPROFILE%/.blender-bridge/sessions/`，含私有本地令牌，不复制到报告。发现接口只回报通过健康检查且身份匹配的运行实例；崩溃后遗留文件不等于活跃实例。
- 换 `.blend` 或重启后重新发现。未找到原会话时不把任务自动投到另一个 Blender。
- 当前 MCP 工具未热加载时，直接用同协议 CLI 完成工作。注册配置和新 MCP 客户端实测不等于旧聊天已刷新工具目录。

## 约束

仅回环 HTTP 在 Blender 端监听，MCP 使用 stdio。令牌保护不防御同用户恶意程序；路径约束不构成任意 Python 的沙箱。模型编辑只在 Object Mode 接受，避免破坏用户正在进行的 Edit/Sculpt 操作。

任务历史每会话上限 1000，队列 128；达到上限要保存检查点并新开实例。未自动驱逐 ID，避免旧 ID 再次执行。运行中的 Blender API 或渲染无法安全强制取消，只有排队任务可取消。终态日志 `.bridge/jobs.jsonl`；崩溃中的任务结果要检查文件与场景，不自动重放。

Host 任务与审阅记录持久化在输出根目录 `.bridge/host/state.sqlite3`。Windows 长任务先启动 `tools/start_host.ps1 -OutputRoot <相同输出根目录>` 的持久 broker；它在 MCP 客户端外派发任务，避免客户端 JobObject 结束时杀死子任务。broker 不注册 Windows 自动启动。MCP/CLI 断开后查询原 ID，不自动重做；`job.recover` 仅允许恢复已证明未开始的中断队列项。

`job inspect --id <ID>` 不指定 session 时查询 Host；原生任务指定其准确 session。后台 Blender worker 单独记录身份、冻结快照、日志与终态；仅 `worker.cancel` 可停止该精确自有进程，保留部分结果。运行 `bake.execute` 的 worker 必须同时传 `bake_plan`，指向与快照匹配的 prepared 烘焙计划；计划复制到隔离工作目录后仍验证源哈希。

`modeling plan --request <JSON>`、`modeling submit --plan <JSON>`、`modeling inspect --id <ID>`、`review record --file <JSON>` 与 `modeling resume --id <ID> --review <JSON> --steps <JSON>` 均路由相同 catalog。场景操作把 `--session` 和 `--revision` 放在子命令前。提交后出现 `awaiting_visual_review` 是正常暂停点：Codex 需实际读图并登记观察，不能自动填充通过评语。用户最终视觉验收独立保留。

已保存文件重启后，先发现并核实新 session/revision，再调用 `modeling reconnect --id <ID>`。只允许待审阅且无活动写任务的记录重连；当前几何、相机与渲染环境须仍匹配旧图。它保留未关闭差异和历史，不重放写入。源已变化则拒绝绑定，应重新检查现场并建立新的候选证据。

Blender 5.2 Geometry Nodes 输入通过 `modifier.properties.inputs` 的 RNA 属性读取；旧版本接口走兼容分支。使用 `geometry_nodes.inspect/set_input` 的 typed 参数，不假定旧式 modifier 自定义属性仍可写。属性驱动输入明确拒绝；没有实测过其他 Blender 版本。UV overlap/padding 是指定分辨率下的栅格测量，小于像素的重叠未测量。

默认使用米，Euler XYZ 弧度。FBX `-Y forward / Z up`，显式选中对象，单位交给 FBX_SCALE_UNITS。UE 资产的朝向、厘米尺寸、骨架与动画兼容性仍须在 UnrealBridge 回读，不能以 Blender 导出成功代替。

动画导出使用 `animation=true` 与明确 `frame_start/frame_end`，否则沿用场景范围。导出后恢复场景范围和当前帧。Blender 内部 FBX 读回用 `anim_offset=0` 才与源帧号一致；导入默认偏移 1 帧，不应据此误判回姿态。

