# 启动、发现与故障恢复

Windows 本机安装：仓库 `C:/dev/BlenderBridge`；可编辑源码 `src/blender_bridge`，稳定 Python 环境 `.venv/Scripts/python.exe`。MCP stdio 入口 `-m blender_bridge.mcp_server`。不需要模型 API Key。

```powershell
& C:/dev/BlenderBridge/.venv/Scripts/blender-bridge.exe discover
& C:/dev/BlenderBridge/.venv/Scripts/blender-bridge.exe --session <SESSION> catalog
& C:/dev/BlenderBridge/.venv/Scripts/blender-bridge.exe --session <SESSION> execute scene.inspect
```

写入示例先把参数写入任务下的新 JSON 文件；避免 PowerShell 内联 JSON 引号问题：

```powershell
& C:/dev/BlenderBridge/.venv/Scripts/blender-bridge.exe --session <SESSION> execute mesh.vertices --revision <REV> --request-id <UUID> --args '@C:/path/to/edit.json'
& C:/dev/BlenderBridge/.venv/Scripts/blender-bridge.exe --session <SESSION> job <UUID>
```

## 运行方式

- 用户现有 Blender：Preferences → Add-ons → Blender Bridge 设置输出目录及读目录，然后 View3D 侧栏 Bridge → Start。默认不自启，不打开外网监听，不开启任意 Python。
- 新建本任务实例：`tools/start_blender.ps1 -OutputRoot <任务输出目录> -ReadRoot <参考图片目录>`；已有文件加 `-BlendFile <精确文件>`。默认后台实例；用户要求可见编辑器时加 `-Visible`。保留输出的 PID、启动时间、会话描述符和启动命令以核实归属。
- 发现文件在 `%USERPROFILE%/.blender-bridge/sessions/`，含私有本地令牌，不复制到报告。发现接口只回报通过健康检查且身份匹配的运行实例；崩溃后遗留文件不等于活跃实例。
- 换 `.blend` 或重启后重新发现。未找到原会话时不把任务自动投到另一个 Blender。
- 当前 MCP 工具未热加载时，直接用同协议 CLI 完成工作。注册配置和新 MCP 客户端实测不等于旧聊天已刷新工具目录。

## 约束

仅回环 HTTP 在 Blender 端监听，MCP 使用 stdio。令牌保护不防御同用户恶意程序；路径约束不构成任意 Python 的沙箱。模型编辑只在 Object Mode 接受，避免破坏用户正在进行的 Edit/Sculpt 操作。

任务历史每会话上限 1000，队列 128；达到上限要保存检查点并新开实例。未自动驱逐 ID，避免旧 ID 再次执行。运行中的 Blender API 或渲染无法安全强制取消，只有排队任务可取消。终态日志 `.bridge/jobs.jsonl`；崩溃中的任务结果要检查文件与场景，不自动重放。

默认使用米，Euler XYZ 弧度。FBX `-Y forward / Z up`，显式选中对象，单位交给 FBX_SCALE_UNITS。UE 资产的朝向、厘米尺寸、骨架与动画兼容性仍须在 UnrealBridge 回读，不能以 Blender 导出成功代替。

动画导出使用 `animation=true` 与明确 `frame_start/frame_end`，否则沿用场景范围。导出后恢复场景范围和当前帧。Blender 内部 FBX 读回用 `anim_offset=0` 才与源帧号一致；导入默认偏移 1 帧，不应据此误判回姿态。

