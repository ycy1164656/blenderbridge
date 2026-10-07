# Blender Bridge

代码仓库：[ycy1164656/blenderbridge](https://github.com/ycy1164656/blenderbridge)。

本地 Blender 原生视觉闭环建模工具，包含 Blender 插件、主线程运行时、持久 Host、MCP、命令行与两项建模技能。当前版本 **0.3.0**，本机验证 **Blender 5.2.2 LTS / Windows / Python 3.12.12 / MCP SDK 1.30.0**。

用于通过“检查场景 → 小步编辑 → 实际渲染 → 读回验证”的方式制作游戏模型。桥接能力通过并不代表模型已经达到概念图质量。

## 已实现

| 部分 | 当前能力 |
|---|---|
| Blender 插件 | 侧栏启动/停止；输出与读目录；默认关闭任意 Python |
| 会话与传输 | 回环 HTTP、令牌、准确会话与 revision、主线程队列、稳定 ID、防重复、持久任务历史、排队取消 |
| 参考与闭环 | 裁切/有效透明蒙版/等比校准/冻结；计划、固定出图、实际图片交付、差异单、自主修正与待审阅重连 |
| 建模 | 自定义轮廓、放样、扫掠、曲线、边环、局部修形、几何雕刻、修改器、Geometry Nodes 暴露参数、可编辑 recipe |
| 区域拆件 | `object.separate` 接收完整选区与显式面边界规则；可保留原件；逐角 UV、材质/贴图引用、权重及 base 几何检查；无需任意 Python |
| 身份与保护 | 对象/网格 ID、部件与锁定区域、拓扑选择、正交/透视拾取、裁切坐标映射、base/evaluated 分离、保护区指纹 |
| 外观 | 固定灰模/材质/线框/轮廓/法线/部件图，UV seams/unwrap/pack/密度/栅格重叠，多视图可见性投射、PBR、高低模 cage 烘焙 |
| 动画与交付 | 刚性/柔性权重、修正/平滑/镜像/转移/归一、pose suite、保留高模的重拓扑、LOD/碰撞、源/FBX/GLB/OBJ 与独立读回 |
| Host 后台 | SQLite 持久记录、Windows broker、冻结快照 worker、准确身份取消、部分产物与终态、对比图和技术报告 |
| Agent 接口 | 7 个分组 MCP 工具，153 个操作契约（127 原生、26 Host；任意 Python 可选且默认关闭）；MCP/CLI 共用 schema |
| Skills | `blender-bridge`：运行与操作；`blender-reference-modeling`：参考图质量控制 |

默认不依赖 Hunyuan3D、神经模型权重或外部图生 3D 服务。雕刻使用明确范围的几何操作；没有承诺 GUI 笔刷重放。QuadriFlow 等可选能力按运行时探测报告。没有自动美术评分或 UE 导入。操作契约数量不代表每个参数组合都经过生产测试。

## 本机使用

源码在 `C:/dev/BlenderBridge`。Codex 已注册 `blender_bridge` stdio 服务；技能安装为指向此仓库的轻量 router。新 MCP 客户端已完成实际握手测试；现有聊天是否热加载取决于客户端工具目录刷新，未刷新时使用同协议 CLI。

```powershell
# 检查运行实例，不自动启动/切换用户场景
& C:/dev/BlenderBridge/.venv/Scripts/blender-bridge.exe discover

# 启动持久 Host，供后台任务跨 MCP 断开继续运行
& C:/dev/BlenderBridge/tools/start_host.ps1 -OutputRoot C:/path/to/Revision04

# 从已安装代码启动本任务的后台 Blender
& C:/dev/BlenderBridge/tools/start_blender.ps1 -Installed -OutputRoot C:/path/to/Revision04 -ReadRoot C:/path/to/approved-references
```

已安装的 Blender 插件在 Preferences → Add-ons → Blender Bridge。设置目录后，通过 View3D 侧栏 Bridge → Start 连接现有场景。默认不自动启动监听。需要用户可见窗口时，由用户请求或手动运行启动器加 `-Visible`。

建模时调用 `$blender-reference-modeling`，它会配合 `$blender-bridge`。先选会话，再查询实时 schema。写入、渲染、保存和导出必须带当前 revision。通过 `reference.freeze → modeling.plan/submit → 实际读图 → review.record → modeling.resume` 小步迭代；工具要求图片被交付和证据未过期，Codex 仍须承担实际视觉判断。详细命令、Host 配置与恢复约定见 [运行说明](skills/blender-bridge/references/runtime.md)。

## 安装到另一环境

```powershell
uv sync --extra dev
uv run python tools/build_addon.py
uv run python tools/install_skills.py --apply
uv run python tools/register_codex.py
```

Blender 插件包为 `dist/blender_bridge-0.3.0.zip`，递归包含 42 个 Python 文件与所有权哈希清单。可在 Blender 中安装；`tools/install_addon.py` 需由 Blender 执行，先核对旧所有权清单、备份插件和偏好，再按显式 `--upgrade --apply` 升级并验证实际安装哈希。首次管理旧插件需要匹配的 `--previous-archive`。保留原输出路径、读目录、端口和 Python 开关；不替换其他插件。

0.3.0 的区域选区与拆件参数见 [区域拆件说明](skills/blender-bridge/references/separation.md)。正在运行的旧 Blender/MCP 进程不会热更新：下一次使用新参数前重新启动对应实例或客户端连接，并核对实时 schema；不要中断其他任务的工作实例。

MCP 注册器备份原配置，只新增 `blender_bridge` 并比较其他配置语义；Codex CLI 可能将已有空 `args=[]` 序列化为省略，两者等价。Skill 安装器拒绝覆盖已修改 router。

## 验证与边界

- `uv run pytest -q`：协议、过期上下文、防重复、路径、认证、长请求等。
- `tests/blender_separation_fixture.py`：9 项区域/精确面/松散部件拆分、材质绑定、UV、贴图引用、权重、骨骼变形、选区/保护/失败处理，支持安装版验证及独立进程保存读回。
- `tests/separation_mcp_smoke.py`：新 MCP 客户端对明确归属的 0.3.0 空白实例，验证关闭任意 Python 时的选区、拆件、固定视角出图、图片交付、请求去重与保存。
- `tests/blender_native_fixture.py`：8 项真实 Blender 原生建模、保护、UV/PBR、固定图、骨骼、检查点、重拓扑、烘焙与导出。
- `tests/blender_extended_fixture.py`：7 项身份/共享数据、修改器、拾取、投射、柔性权重、部分失败恢复、雕刻与 Geometry Nodes。
- `tests/blender_delivery_fixture.py`：4 项曲线/扫掠/边环/条带、UV padding/法线方向、四格式导入尺度、恢复前后实际像素比较。
- `tools/a06_mcp_loop.py` 与 `tools/a06_worker_success.py`：真实安装版 MCP 的读图、审阅、重连、局部修正和后台任务。这些是一次验收流程，不应在用户任意场景无条件重跑。
- `tests/blender_geometry.py`：真实 BMesh 单面/邻接面/全区域挤出，要求闭合样例无非流形边。
- `tests/live_smoke.py`：只针对本任务新建的空白测试实例，32 次操作链路；不是对任意用户场景可重复执行的无害检查。
- `tests/gui_and_mcp_smoke.py`：真实 GUI 视口、渲染、MCP 握手与内联图片。
- `tests/blender_roundtrip.py`：独立 Blender 读取 `.blend` 与 FBX，检查权重/UV/骨骼/形变。

Blender 测试必须加 `--python-exit-code 1`。启动测试实例、停止实例都应记录和核对准确 PID/启动命令；不要按进程名终止 Blender。

当前没有原子事务回滚；一次失败可能留下部分修改。先保存检查点，失败后检查现场。交互实例内运行中的 bpy/渲染不支持安全强制取消；隔离 worker 可以按准确归属中断并保留部分产物。仅验证列出的版本与场景，未强制耗尽实际显存/RAM，未做大型长局性能验收。UV 栅格检测不保证发现亚像素重叠。

本次交付：[0.3.0 区域拆件升级与验证报告](docs/006_BlenderBridge_0.3.0_区域拆件升级与验证(done).md)。本轮仅升级工具，没有修改用户模型或执行 UE 验收。

0.2.0 历史交付：[完整升级与验证报告](docs/005_BlenderBridge_0.2.0_原生视觉闭环升级与验证(done).md)、[完整规格](docs/004_Blender原生视觉闭环建模完整升级规格.md)、[机甲参考/R3/R4 对比](artifacts/native-modeling/a02/final/approved-R3-R4.png)。历史机甲仅完成当时的局部比例改善自评，完整概念匹配及用户视觉接受仍待评审。

历史记录：[架构与参考来源](docs/001_架构与参考来源.md)、[0.1 本机验证](docs/002_本机验证记录.md)、[塔与机甲后续制作入口](docs/003_塔与机甲后续制作入口.md)。

