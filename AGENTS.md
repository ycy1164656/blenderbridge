# BlenderBridge 开发约定

- 本仓库是独立工具，不修改 ShooterRoyal、UnrealBridge 或参考项目。`.tmp/references` 中上游代码只读；新功能在 `src/blender_bridge` 实现。
- `catalog.py` 是操作名与参数的唯一契约；`operations.py` 和 `runtime.py` 中的 bpy 访问只在 Blender 主线程。传输/MCP 工作线程不得接触 bpy。
- 修改协议必须覆盖错误会话、过期 revision、重复 ID、未知结果和取消语义。不要自动重试写操作或声称可以强制取消运行中的 bpy。
- 调试/测试只使用本任务创建且 PID/命令仍匹配的 Blender 实例，保留其他实例与未保存文件。
- 改动先做最轻可靠测试，再真实 Blender 验证受影响操作。保存/导出还需独立读回；图片必须实际查看。测试脚本用 `--python-exit-code 1`，不能仅依赖 Blender 默认退出码。
- 安装/配置写入要备份现有目标，保留无关配置和用户定制；禁止无授权回滚、提交、推送或发布。
- 质量评估分开报告：桥接技术、模型技术、美术参考匹配、UE 验收。不可用单一机械 PASS 替代后三项。
- 长期文档使用中文；安装技能仅为指向本仓库的 router，更新 canonical skill 后不产生第二套漂移实现。
