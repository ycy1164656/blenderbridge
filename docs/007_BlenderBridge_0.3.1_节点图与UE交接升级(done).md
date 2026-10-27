# BlenderBridge 0.3.1 节点图与 UE 交接升级

日期：2026-10-27。新增两类工具能力，并将 Python 包、MCP、Blender 插件和安装归属清单统一到 0.3.1。

## 节点图局部修改

`node_graph.inspect` 返回精确 owner、graph token、实时 socket 和 RNA enum。`node_graph.patch` 在私有副本上评估 Geometry Nodes、Shader、Compositor 修改，再切换指定 owner；支持嵌套组、输入和属性修改以及链接/断链。保留共享 peer、外部纹理和其他场景，返回 applied/rolled_back/rollback_failed。

Blender 5.2.2 的六组实际场景验证了几何位移、嵌套组隔离、共享 owner 保持和 Compositor 输出；独立进程重开 blend 回读并查看渲染图。错误 enum/node/link/token 均验证拒绝。

## 模型交接

manifest v2 分开 FBX exporter axes 和实测/声明语义前方，未知方向保持 unknown。`export.package(ue_static_mesh_parts=true)` 使用私有副本导出厘米局部几何，保留部件枢轴与装配关系。

真实加农炮 8 部件经独立 Blender 进程读取、UE 导入/保存/冷读取和运行时 yaw/pitch 验证；源 blend 与原部件几何保持。源模型的非流形及三角面预算警告保留，未声称美术或性能通过。

## 安装

新版包包含 43 个 Python 文件。安装程序验证旧归属、备份插件与偏好、保留路径/端口/Python 开关，再逐文件核对哈希。新进程已从用户 addons 目录冷读取 0.3.1、155 项 catalog 与新增操作。正在运行的 Blender、Host broker 和 MCP 进程需要在各自任务结束后重启；不强制关闭其他任务会话。

详见 [模型交接约定](../skills/blender-bridge/references/model-handoff.md) 和 [维护技能](../skills/blender-bridge/SKILL.md)。
