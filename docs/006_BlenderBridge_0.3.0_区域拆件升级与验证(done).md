# 006 BlenderBridge 0.3.0 区域拆件升级与验证

日期：2026-10-07。范围：独立 BlenderBridge 工具及本机受管理安装。本文记录本机实现、安装及验证，远端代码版本以 Git 提交记录为准；未修改 ShooterRoyal 代码、资产或用户 Blender 模型。

## 交付结果

版本、Python 包元数据、锁文件、Blender 插件版本统一为 **0.3.0**，协议仍为 1；保持 153 个操作契约、7 个分组 MCP 工具。安装包包含 42 个 Python 文件，源码、包内清单与已安装文件哈希一致。

下列安装包、`.tmp` 机器证据及安装记录为本机产物，未纳入 Git；仓库包含对应源码、测试和构建脚本。

- [安装包](../dist/blender_bridge-0.3.0.zip)
- [区域拆件使用与边界](../skills/blender-bridge/references/separation.md)
- [本轮机器验证摘要](../.tmp/artifacts/separation-0.3.0/release-summary.json)
- [本机安装记录](../.tmp/installation.json)

## 接口与行为

扩展已有 `object.separate`，保留 `faces=[...]` 和 `mode="loose"` 调用；没有重复新增平行拆件系统。

| 输入 | 行为 |
|---|---|
| `selection_id` + `face_policy="all_vertices"` | 仅拆走全部顶点在选区内的面；跨界面留在余件 |
| `selection_id` + `face_policy="any_vertex"` | 拆走至少一个顶点在选区内的面；可能包含边界外邻接面 |
| `keep_original=true` | 在独立副本拆分，保留原件、其选区和部件保护；返回原件、余件及拆出对象 |
| 默认 `keep_original=false` | 保持旧的原位拆分语义，失效旧选区并标记部件区域需重新分配 |

选择边界规则必须显式给出，不从文字猜测。内部读取完整顶点选区，而非返回给调用方的 32 项样本。支持 `selection.query` 已有的空间、材质、顶点组、部件等选区来源。两种规则选择已有面，不沿空间框几何裁切，也不自动识别语义部件。材质顶点选区涉及共享顶点时，精确面材质划分仍应使用明确面集合。

前置检查拒绝对象不匹配、会话/网格/拓扑过期的选区、空面选区、重复或越界索引、输出名称冲突、共享网格和未验证的 Shape Keys。原位修改仍服从部件保护。

## 数据保留与修复

拆分前记录 base 几何和数据，临时索引属性追踪原顶点/原面对应关系，拆分后检查：

- 顶点位置、面绕序、全部面的唯一覆盖、边/孤立顶点覆盖；跨对象重复边界顶点属于预期。
- 每面材质索引、网格及对象材质槽绑定、材质引用、含嵌套节点组的贴图引用。
- 全部 UV 层、逐角 UV、活动 UV 设置、顶点组权重、Armature 绑定和世界变换。
- 保留原件模式下，原件数据仍与拆分前一致。

真实 Blender 5.2.2 测试发现原生 Separate 会将新对象的对象级材质槽改成网格级。封装恢复源材质槽的链接方式与引用，再执行验证。另修复旧顶点/边选择可能使非目标面进入拆分的问题：在临时面选择模式下清空旧选择，明确选中目标面，并恢复调用前的选择模式及活动对象。

后置检查失败不伪装成事务回滚。临时索引会清理，已产生的对象仍有独立 ID，原位拆分旧选区失效；失败 job 保留 `partial_changes_possible`，同一请求 ID 不会重放。已通过主动破坏 UV、权重、贴图引用的负例。

## 实际验证

环境：Windows，Blender 5.2.2 LTS。真实 Blender 测试均使用本任务单独创建的实例，并指定 `--python-exit-code 1`。

| 验证 | 结果与证据 |
|---|---|
| 协议/Host/契约 | `pytest -q`：25 passed；含新参数 schema、错误会话/过期 revision、请求去重、取消与过期队列 |
| 真实源码专项 | 9 项通过，[结果](../.tmp/artifacts/separation-0.3.0/source-release/result.json) |
| 真实安装版专项 | 同一组 9 项通过，[结果](../.tmp/artifacts/separation-0.3.0/installed-release/result.json) |
| 保存后独立读回 | 新 Blender 进程读取保存场景，比较目标对象几何、UV、材质、打包贴图哈希、权重及实际骨骼变形后的坐标，[结果](../.tmp/artifacts/separation-0.3.0/release-readback/readback.json) |
| 新 MCP 客户端 | 7 个工具握手；准确实例/版本；任意 Python 关闭；正式接口完成检查点、完整区域选区、副本拆分、原件指纹、请求去重、固定出图、图片交付与保存，[结果](../.tmp/artifacts/separation-0.3.0/mcp-release/mcp-smoke.json) |
| 固定视角样例 | 实际查看了 [Before](../.tmp/artifacts/separation-0.3.0/mcp-release/before.png) / [After](../.tmp/artifacts/separation-0.3.0/mcp-release/after.png)；测试立方体前后像素一致 |
| 安装与技能 | 42 个安装文件哈希一致；canonical skill 校验通过；安装 router 继续指向仓库技能 |

9 项专项覆盖：旧选择污染、精确面；区域副本/原件；边界规则/全选空余件；松散面/线/孤点；过期选区及前置拒绝；保护/共享/Shape Keys 边界；超过样本上限的完整选区与部件映射；主动数据破坏后的清理/不重放；实际 Armature pose 变形。

保存文件均是隔离测试场景，包含测试与故障注入夹具，不是交付美术资产。测试中 Blender 对 `Material.use_nodes` 发出未来 Blender 6.0 移除的 DeprecationWarning；当前 5.2.2 测试正常退出。

## 安装、保留与生效

本机 `.venv` 中可编辑包已同步为 0.3.0。插件通过既有所有权清单核对后升级，保留 `output_root=C:\dev\BlenderBridge\outputs`、空附加读目录、端口 0、`allow_python=false`，仍不自动启动监听。

首次替换前的 0.2.0 插件保留在 `.tmp/codex-backups/1791352995221667400-blender-addon`，对应偏好备份在 `.tmp/codex-backups/1791352995274796400-blender-preferences`；最终安装前的其他备份路径见安装记录。恢复仍需明确授权，本轮未回滚。

旧的运行中 Blender/MCP 进程没有被热替换。下一次使用新增参数前，重启对应实例或 MCP 客户端连接，并通过实时 catalog 核对；本轮没有结束其他任务实例。所有本轮自有常驻测试实例在保存和验证后按 PID、启动时间、可执行文件和命令行核实后结束。

收尾时，合并的进程停止与会话描述符清理命令被自动审批以 `blocked by policy` 拦截，未返回更具体理由。改为单独核实并停止自有测试进程已成功；会话描述符记录保留，未绕过删除拦截。运行时发现只返回健康检查和身份匹配的活动实例。

## 限制

- Shape Keys 拆分尚未验证，当前明确拒绝；共享网格需要先显式创建独立副本。
- `preservation` 不保证一般修改器求值外形、平滑/自定义法线或其他自定义属性。本轮实际测试的 Armature pose 不代表所有修改器组合均已覆盖。
- 区域边界按现有面选取，不自动生成切割边；模型外观仍需按固定视角审阅。
- 未做大型生产网格性能基准、其他 Blender 版本、美术接受或 UE 导入/运行验证。
- 技能明确优先查询正式接口。`python.execute` 仍是默认关闭的无限制可信入口，不是沙箱；本次新能力无需开启它。
