# 005 BlenderBridge 0.2.0 原生视觉闭环升级与验证

日期：2026-10-05。工作区：`C:/dev/BlenderBridge`。授权来源：用户要求按照完整升级指南实施本次升级。规格为 [004](004_Blender原生视觉闭环建模完整升级规格.md)，不是仅 P0/P1，也不是仅文档修订。未提交或推送 Git，未写入 ShooterRoyal/Unreal Content，旧 R2/R3 与批准参考原件保持。

## 1. 交付结论

0.2.0 已实现并安装：参考冻结、原生建模、固定多视图、真实图片交付与差异审阅、局部修正、UV/PBR/投射/烘焙、绑定与动作、导出独立读回，以及后台任务、检查点和待审阅重连。统一目录包含 153 个操作契约：127 原生、26 Host，仍保持 7 个分组 MCP 工具。任意 Python 默认关闭；核心不需要神经图生模型、云端推理或权重下载。

桥接工程验收通过。A02 的 `self_review_passed` 只覆盖头/肩/胸的局部比例与厚度改善；完整机甲概念匹配及 `pending_user_review` 独立保留。A01/A03/A04 为明确标注的工程件，没有被宣称为 ShooterRoyal 已批准生产资产。UE 导入和运行验证为 `not_run`。

测试结果：23 个 pytest 用例通过；真实 Blender 基础 8 项、扩展 7 项、交付补充 4 项通过。源 `.blend`、FBX、GLB、OBJ 在独立 Blender 进程中读回通过。安装 41 个 Python 文件与源码逐文件核对，MCP/CLI/实时 catalog 逐项参数校验见 [最终证据](../artifacts/native-modeling/final-verification.json)。计数仅描述已执行测试，不代表全部参数组合或所有 Blender 版本。

另外，A01/A02/A03 最终 scoped `.blend` 已在独立 Blender 重新打开，分别核实 13/373/15 个对象与全部稳定 ID，源文件哈希未变，见 [源文件读回](../artifacts/native-modeling/saved-source-readback.json)。这些通过 library write 保存的 scoped 文件会输出 `Library file, loading empty scene` 提示；实际场景对象完整读回。本轮未据此声称 GUI 工作区布局也已保存。

## 2. 直接打开的交付物

- [安装包 0.2.0](../dist/blender_bridge-0.2.0.zip)、[README](../README.md)、[运行与恢复说明](../skills/blender-bridge/references/runtime.md)。
- [批准参考 / R3 / R4 对比图](../artifacts/native-modeling/a02/final/approved-R3-R4.png)、[R3/R4 相同相机对比](../artifacts/native-modeling/a02/final/R3-R4-same-camera.png)。概念相机为近似匹配，R3/R4 为完全相同相机；没有拉伸图像伪造轮廓一致。
- [R4 可编辑源文件](../artifacts/native-modeling/checkpoints/b7f79ce0b89842d182bf0793d48398e9/source.blend)、[R4 最终多视图/保护范围/审阅证据](../artifacts/native-modeling/a02/final-evidence.json)。
- [工程塔源文件](../artifacts/native-modeling/a04/export/source.blend)、[FBX](../artifacts/native-modeling/a04/export/asset.fbx)、[GLB](../artifacts/native-modeling/a04/export/asset.glb)、[OBJ](../artifacts/native-modeling/a04/export/asset.obj)、[贴图与交付清单](../artifacts/native-modeling/a04/export/delivery.json)。应连同同目录纹理和 OBJ MTL 使用。
- [本次完整 Blender 工作现场](../artifacts/native-modeling/session/native-upgrade-final.blend)，包含测试件及历史候选；精简交付优先使用上面各自的 scoped source。

![批准参考、旧 R3 与新 R4](../artifacts/native-modeling/a02/final/approved-R3-R4.png)

## 3. 实现范围

| 部分 | 实际实现与关键边界 |
|---|---|
| Catalog 与协议 | 单一 schema、执行域/写入/产物/长任务/取消声明；准确 session/revision、稳定 request ID、防重复、持久日志；旧会话任务不占新会话容量，也不自动重放 |
| Host | SQLite 任务/参考/审阅/产物/图片交付记录；Windows 独立 broker 使任务跨 MCP 客户端退出继续；冻结 blend worker、准确进程身份、取消和部分产物 |
| 参考 | 原图只读，派生裁切、真实 alpha 检查、等比校准、地线/中心线/landmark、视角与姿态冲突、冻结哈希及未知区域 |
| 原生造型 | 轮廓拉伸、截面放样、运输坐标扫掠、曲线、边环、slide/cut；修改器参数/顺序；recipe 重放为新对象；Geometry Nodes 已暴露输入 |
| 局部控制 | 对象/网格 ID，独立与共享复制，语义部件、锁定区域，拓扑选择与集合运算、固定图正交/透视 ray、裁切缩放、遮挡检测；evaluated 索引不冒充 base |
| 雕刻/重拓扑 | 遮罩与几何 grab/inflate/smooth/flatten/symmetrize；高模保留、低模 decimate/voxel、四边条带/投射/误差；有数据丢失的重网格明确声明 |
| 图像闭环 | 六类固定渲染、turntable/局部图、源/相机/环境指纹、图像真实返回、版本绑定差异单、待审阅恢复；已交付图片不等于自动视觉批准 |
| 表面 | UV seams/unwrap/pack/density、栅格 overlap/padding；可见性受限的多视图 UV 投射；PBR 色彩空间与法线方向；真实 Cycles high/low/cage bake |
| 动作/游戏 | 刚性/柔性绑定、deform-only 统计、权重编辑/平滑/镜像/转移/归一、pose suite/回姿态；LOD/碰撞/具体 profile 验证 |
| 保存/交付 | 依赖闭包检查点，恢复追加新候选并失效旧 session/selection；batch 部分完成如实记录；源/FBX/GLB/OBJ/纹理哈希与独立导入测量 |
| Skill/UI | 两项 canonical Skill 更新，已安装 router 无漂移；侧栏显示原生能力/建模阶段/差异数/图片/检查点和输出入口。侧栏代码已加载，本次未声称完整 GUI 交互验收 |

Blender `bpy` 始终在主线程。Host 代码不导入 `bpy`。耗时快照任务使用隔离 Blender；交互实例正在执行的 bpy 不提供安全强制取消。

## 4. A01—A06 实测

| 任务 | 状态与结果 | 证据 |
|---|---|---|
| A01 原生视觉循环 | `passed`，工程校准件；参考源几何不复制为候选。明确注入左臂 +0.30 m 偏差，实际读图后只改四顶点，六个非目标对象指纹不变；新图、线框、未提供的三分之四角度已查看 | [记录](../artifacts/native-modeling/a01/evidence.json)、[保护区](../artifacts/native-modeling/a01/local-fix-protection.json)、[对比](../artifacts/native-modeling/a01/evidence/reference-final-comparison.png) |
| A02 批准机甲局部改善 | `self_review_passed`（限定局部）/ `pending_user_review`。首个 78 件新造型因肩形和结构不足未通过，自评记录为 needs_work；随后独立追加 R3 建 R4，不改原件。降低/缩小头部、压低加宽肩冠、增加胸甲宽度和深度，140 对象修改、233 对象指纹不变；实际复核六视图 | [局部操作](../artifacts/native-modeling/a02/local-fix-result.json)、[最终记录](../artifacts/native-modeling/a02/final-evidence.json)、[三方对比](../artifacts/native-modeling/a02/final/approved-R3-R4.png) |
| A03 可控硬表面 | `passed`，9 部件工程塔：自定义截面/厚度、服务凹槽、24 段转轴、扫掠管线；recipe 底座宽 +24%、深 +12%、厚 +22%，保留原件并生成变体；灰模/线框实际查看 | [recipe、参数、操作和图片](../artifacts/native-modeling/a03/evidence.json) |
| A04 游戏资产与动作 | `passed`（工程技术范围）。9 mesh / 3 bones / 1162 triangles，保留 high；512×512 的 Normal/AO/BaseColor/Roughness/Metallic 五通道真实烘焙、UV/材质、刚性 rest/sweep/return_rest，最大边长相对变化小于 1e-4。独立柔性测试有 45°/90°弯曲、权重修正和回姿态指纹 | [全记录](../artifacts/native-modeling/a04/progress.json)、[材质图](../artifacts/native-modeling/a04/material.png)、[独立读回](../artifacts/native-modeling/delivery-readback/904ea0d952514840a08f5a692db36acb/verification.json)、[柔性测试](../artifacts/native-modeling/extended-fixture/acf32c7e2990/result.json) |
| A05 恢复/中断 | `passed`，编辑前/修改后/新候选恢复图实际查看；恢复图像像素与原图一致，原修改现场保留，旧 session/selection 失效。真实 worker 受控中断后 worker 和父 job 均 cancelled、错误 PID 被拒绝、无成功产物发布、源哈希不变；待审阅恢复见 A06 | [恢复测试](../artifacts/native-modeling/delivery-fixture/8233641b9627/result.json)、[真实取消](../artifacts/native-modeling/a05/worker-cancel-e8b4dfc352b045b6b0bc01316586e1eb.json) |
| A06 安装与 MCP | `passed`，实际安装路径加载；initialize/7 tools/catalog/native edit/独立 worker/真实 PNG/审阅/resume 均实测。待审阅保存并替换自有 Blender 后重连，保留 top-height 差异、不重放；四上顶点降低 0.25 m，其余八顶点保持；未读图和旧候选 review 均拒绝 | [MCP 全链](../artifacts/native-modeling/a06/progress.json)、[跨断开成功 worker](../artifacts/native-modeling/a06/worker-success.json)、[安装/catalog 核对](../artifacts/native-modeling/final-verification.json) |

A02 保留的差距：肩甲仍偏圆，缺少概念中更强的斜面/楔形叠层；胸板细分和磨损不足；背面和绝对尺寸是推断。没有将这些项目标成完整美术验收。A04 在独立工程塔上进行，没有提前绑定不合格机甲来掩盖造型问题。

## 5. T01—T40 证据矩阵

引用缩写：U = `tests/test_protocol.py`、`test_host.py`、`test_native_contracts.py`（23 passed）；N = [基础实测](../artifacts/native-modeling/native-fixture/1a7106d4dd0d/result.json)（8 passed）；E = [扩展实测](../artifacts/native-modeling/extended-fixture/acf32c7e2990/result.json)（7 passed）；D = [交付实测](../artifacts/native-modeling/delivery-fixture/8233641b9627/result.json)（4 passed）。测试源码在 `tests/`，测试 Blender 全部采用 `--python-exit-code 1`。

| 项 | 状态 | 实际覆盖 / 限制 |
|---|---|---|
| T01 | passed | U：session/revision/稳定 ID、冲突/去重、旧 journal 容量与不重放 |
| T02 | passed | 单源分域和线程边界；A04/A06 在冻结源的隔离 worker 完成烘焙/渲染 |
| T03 | passed | U：裁切、有效蒙版、等比校准、landmark 变换及源哈希保持 |
| T04 | passed | A01 不对称臂长/侧部构造、角色坐标标签、固定正侧背及保留视角实际查看 |
| T05 | passed | U：不透明 RGBA 明确拒绝当作去背景 |
| T06 | passed | U：参考冻结快照不被新输入替换；A01/A02 绑定 frozen revision/hash |
| T07 | passed | U：重复/冲突视图拒绝；A02 单三分之四图与未知背面明确降级 |
| T08 | passed | U：缺 Blender/依赖报告真实缺口；默认无神经模型；原生不支持能力明确拒绝 |
| T09 | passed | A01 真实参考→新几何→读图→四顶点修正→新图复核及可编辑源 |
| T10 | passed / not_run | U 受控 MemoryError 和部分完成日志、A05 真 worker 中断、A06 重连 passed；实际耗尽显存/RAM not_run |
| T11 | passed | D：typed asset.import 的 GLB/OBJ/FBX，asset.append 的 blend；2 倍缩放读回尺寸 4×4×0.4 m，UV 存在 |
| T12 | passed | E：精确身份、同名冲突、共享数据写入拒绝、独立复制 |
| T13 | passed | E：改名/复制/合并/分离与身份、部件映射 |
| T14 | passed | E：修改器参数/顺序实际几何改变；Blender 5.2 Geometry Nodes 暴露参数真实影响几何 |
| T15 | passed | N/E：base/evaluated 差异与多次查询无 mesh 数据泄漏 |
| T16 | passed | E：拓扑变化/检查点恢复后旧选择拒绝 |
| T17 | passed | E：正交/透视 ray、裁切和显示缩放坐标、遮挡、画面方向 |
| T18 | passed | E：evaluated 面只用于诊断，拒绝以其面索引直接写基础网格 |
| T19 | passed | N 的锁定区域拒写；A01 六对象/A02 233 对象保持；E 雕刻 mask 外不变 |
| T20 | passed | U 退化/自交/截面循环对齐；D 轮廓体积、扫掠闭合与正体积、退化路径拒绝、曲线实体、边环闭合、四边条带 |
| T21 | passed | E：mask grab/inflate/smooth/flatten/symmetrize、voxel 数据丢失确认、异常上下文恢复；不包含 GUI 笔刷回放 |
| T22 | passed | N/A04：高模保留、低模 decimate 与误差报告；D 条带、E 单独柔性关节。QuadriFlow 可用性探测，未执行专项质量验收 |
| T23 | passed | E：意外/允许重叠及密度；D：近 UV 岛 padding 冲突，分离后通过；亚像素重叠未测 |
| T24 | passed | E：前/背面与遮挡投射分离，未覆盖像素有报告 |
| T25 | passed | N/A04：high/low/cage 实际五通道 bake、图像统计与实际查看、源修改后 plan stale；worker 精确复制 prepared 计划 |
| T26 | passed | N/D：数据 Non-Color、颜色 sRGB、重复设置 normal Y 只一层翻转、取消翻转后直接连接；AO 单独保留 |
| T27 | passed | N/E：deform 骨骼权重，不让遮罩等非骨骼组充数；缺权重失败 |
| T28 | passed | A04 刚性边长检查与回姿态；E 柔性 45°/90°过渡、权重平滑/转移、姿态后原指纹恢复，实际图片查看 |
| T29 | passed | E/A06：固定镜头、旧几何/相机/环境证据失效；真实 MCP ImageContent PNG |
| T30 | passed | U：无校准/有效 alpha 时指标 not_applicable，无虚构 art score |
| T31 | passed | N/E/D：恢复为新候选、场景保留、旧 session/selection 失效；恢复图像像素一致 |
| T32 | passed | E：第二步失败时首步真实保留，completed 与 failed_step 准确，不声称 rollback |
| T33 | passed | U：篡改产物哈希被发现；A05 半成品不发布为成功；导出/烘焙发布检查 |
| T34 | passed | A04 和最终 N：独立进程源/FBX/GLB/OBJ，尺寸/三角面/UV/rig/deform 权重/帧范围/纹理。OBJ 本身不带骨骼动画，按格式能力标明 |
| T35 | passed | N：LOD 实际减面、命名、convex collision 与交付路径 |
| T36 | passed | U 契约 handler/参数覆盖；最终 153 操作的 MCP describe 与 CLI/实时 catalog 完整 schema 相等 |
| T37 | passed | 41 文件实际安装 hash、一致版本、偏好保留、A06 安装态重连、其他 Codex 配置语义比较 |
| T38 | self_review_passed / pending_user_review | A02 真实批准图/R3/R4 对比和局部修改证据；全艺术匹配未通过，不以工程件或贴图代替 |
| T39 | passed | A06 未读图片拒绝、旧候选 review 拒绝、待审阅恢复仍保留差异；U stale reconnect 不改原记录 |
| T40 | passed | 无图生模型/权重安装；核心本机原生闭环和独立 worker 全链运行 |

## 6. 真实修复与失败记录

- Blender 5.2 partial `.blend` 写入前，新 Scene 的 ViewLayer 必须同步；已修复触发 `BKE_view_layer_copy_data` 的崩溃并以 checkpoint/export 回读复验。
- glTF 导出应用修改器，修复源/GLB 三角面与尺寸不一致；FBX 读回使用 `anim_offset=0` 保持原帧范围。
- Windows MCP 进程的 JobObject 可终止其子任务，增加 MCP 外持久 broker；以提交后断开和重新查询实测。
- worker 取消曾错误地使父 Host job 显示 succeeded，现统一 cancelled；只引用最终取消证据，旧失败记录保留。
- Boolean 留下未使用空材质槽时，烘焙只为实际 polygon 引用的材质设置节点；源/材质状态恢复并复测五通道。
- Geometry Nodes 5.2 使用 `modifier.properties.inputs`；typed 输入与嵌套节点树状态进入指纹，排除 execution_time/界面折叠等非几何瞬态。
- PNG 原始文件哈希可能因 RenderTime 元数据不同而变化；恢复测试比较实际像素和几何，不要求不同时间生成的 PNG 字节相同。

## 7. 安装、保存和限制

本机 Blender 5.2.2 LTS、Host Python 3.12.12、MCP 1.30.0、Pillow 12.3.0、psutil 7.2.2。Host 配置为 `%USERPROFILE%/.blender-bridge/config.json`，输出 `artifacts/native-modeling`，只读参考目录为授权 Revision02。原插件偏好的输出目录/读目录/port/allow_python 保留，任务启动器显式覆盖本任务目录。

Windows Store Codex 进程下实际安装读取来自 LocalCache/Roaming 映射；准确安装路径、文件数、哈希、当前保存源及 schema 核对在 `final-verification.json`。插件与偏好备份均在 `.tmp/codex-backups/`，安装 router 指向仓库 canonical Skill，不复制第二套正文。

与早先配置备份对比，所有其他 MCP 服务配置一致；全局 `model_reasoning_effort` 与旧备份不同，但当前配置最后写入为 14:23:49，早于本次 14:55:31 升级起点。本次未写入 Codex 配置，也未恢复这一已有设置；证据中保留此历史差异，未把全配置比较虚报为相等。

此次未扩大到其他 Blender 版本、任意修改器/GN 节点、GUI 笔刷、真正资源耗尽、重型长期性能、UE 导入或多人运行验收。图像交付回执只证明内容交付；是否实际观察仍由 agent 的可审阅记录负责。人类艺术接受不会被机械指标替代。

当前文件已保存。最终会话/进程和是否仍运行见 [最终运行状态](../artifacts/native-modeling/final-status.json)；只处理本任务创建且身份匹配的进程。未查询或修改 Unreal Editor/PIE/Dirty。历史失败图、恢复备份和报告引用证据保留；没有清空项目缓存或删除用户资产。下一指针是使用现有 Skill 开始明确的新建模任务，本次不自动领取机甲全身重制或 UE 导入。

收尾时无活动任务，已关闭准确匹配的自有测试 Blender PID 64040，发现结果无活动 Bridge 会话；Host broker PID 75152 保持运行供后续后台任务使用。新建模任务按运行说明启动新会话并重新发现身份。文档编号 001—005 无重复/缺号，本地链接审计通过。
