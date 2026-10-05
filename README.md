# Blender Bridge

代码仓库：[ycy1164656/blenderbridge](https://github.com/ycy1164656/blenderbridge)。

本地 Blender 桥接工具，包含 Blender 插件、主线程操作运行时、MCP、命令行与两项建模技能。当前版本 **0.1.0**，本机验证 **Blender 5.2.2 LTS / Windows / Python 3.12.12 / MCP SDK 1.30.0**。

用于通过“检查场景 → 小步编辑 → 实际渲染 → 读回验证”的方式制作游戏模型。桥接能力通过并不代表模型已经达到概念图质量。

## 已实现

| 部分 | 当前能力 |
|---|---|
| Blender 插件 | 侧栏启动/停止；输出与读目录；默认关闭任意 Python |
| 会话与传输 | 回环 HTTP、令牌、准确会话与 revision、主线程队列、稳定任务 ID、防重复执行、状态查询、排队取消 |
| 建模 | 显式网格、基本体、逐点编辑、区域挤出/内插、边倒角/细分、法线、修改器 |
| 外观 | 材质与本地贴图、UV、参考图片、相机/灯光、指定对象灰模/材质渲染、GUI 视口截图 |
| 动画与交付 | 明确骨架/权重、关键帧、检查点、源文件保存、指定对象 FBX 导出、带哈希的产物 |
| Agent 接口 | 7 个分组 MCP 工具，26 个默认启用操作；受信任 Python 为第 27 个可选操作 |
| Skills | `blender-bridge`：运行与操作；`blender-reference-modeling`：参考图质量控制 |

不包含云端图生 3D、自动重拓扑、雕刻笔刷、PBR 烘焙、UE 导入或自动美术评分。没有调用 Meshy、Tripo 或其他付费服务。

## 本机使用

源码在 `C:/dev/BlenderBridge`。Codex 已注册 `blender_bridge` stdio 服务；技能安装为指向此仓库的轻量 router。新 MCP 客户端已完成实际握手测试；现有聊天是否热加载取决于客户端工具目录刷新，未刷新时使用同协议 CLI。

```powershell
# 检查运行实例，不自动启动/切换用户场景
& C:/dev/BlenderBridge/.venv/Scripts/blender-bridge.exe discover

# 启动本任务的后台 Blender；读目录只包含授权参考素材
& C:/dev/BlenderBridge/tools/start_blender.ps1 -OutputRoot C:/path/to/Revision04 -ReadRoot C:/path/to/approved-references
```

已安装的 Blender 插件在 Preferences → Add-ons → Blender Bridge。设置目录后，通过 View3D 侧栏 Bridge → Start 连接现有场景。默认不自动启动监听。需要用户可见窗口时，由用户请求或手动运行启动器加 `-Visible`。

建模时调用 `$blender-reference-modeling`，它会配合 `$blender-bridge`。先选会话，再查询实时操作 schema。写入、渲染、保存和导出必须带当前 revision。详细命令和恢复约定见 [运行说明](skills/blender-bridge/references/runtime.md)。

## 安装到另一环境

```powershell
uv sync --extra dev
uv run python tools/build_addon.py
uv run python tools/install_skills.py --apply
uv run python tools/register_codex.py
```

Blender 插件包为 `dist/blender_bridge-0.1.0.zip`。可在 Blender 中安装；本机自动安装脚本 `tools/install_addon.py` 需由 Blender 执行，保留已有用户偏好，默认遇到已存在插件目录会拒绝覆盖。显式 `--upgrade` 要求 `.tmp/previous-addon.zip` 与现有代码逐字节一致，再备份原插件/偏好后升级。它不会安装 Blender，也不会替换其他插件。

MCP 注册器备份原配置，只新增 `blender_bridge` 并比较其他配置语义；Codex CLI 可能将已有空 `args=[]` 序列化为省略，两者等价。Skill 安装器拒绝覆盖已修改 router。

## 验证与边界

- `uv run pytest -q`：协议、过期上下文、防重复、路径、认证、长请求等。
- `tests/blender_geometry.py`：真实 BMesh 单面/邻接面/全区域挤出，要求闭合样例无非流形边。
- `tests/live_smoke.py`：只针对本任务新建的空白测试实例，32 次操作链路；不是对任意用户场景可重复执行的无害检查。
- `tests/gui_and_mcp_smoke.py`：真实 GUI 视口、渲染、MCP 握手与内联图片。
- `tests/blender_roundtrip.py`：独立 Blender 读取 `.blend` 与 FBX，检查权重/UV/骨骼/形变。

Blender 测试必须加 `--python-exit-code 1`。启动测试实例、停止实例都应记录和核对准确 PID/启动命令；不要按进程名终止 Blender。

当前没有原子事务回滚；一次失败可能留下部分修改。先保存检查点，失败后检查现场。运行中的 bpy/渲染不支持安全强制取消。仅验证列出的版本与场景，不宣称覆盖所有 Blender 版本、所有修改器参数或大型生产场景。

更多内容：[架构与参考来源](docs/001_架构与参考来源.md)、[本机验证记录](docs/002_本机验证记录.md)、[塔与机甲后续制作入口](docs/003_塔与机甲后续制作入口.md)。

