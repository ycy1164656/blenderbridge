# BlenderBridge 0.4.0 版本发布

日期：2026-11-10。按用户要求，将 0.3.1 提升一个 minor 为 0.4.0；协议保持 1。此发布整理版本入口和交付说明，原有节点图、区域拆件、模型保护与 UE 部件交接的实现保持。

## 版本与文件

- `pyproject.toml`、`uv.lock` 中包版本为 0.4.0，依赖未升级。
- `src/blender_bridge/__init__.py` 的 `__version__` 为 0.4.0、`bl_info.version` 为 `(0, 4, 0)`；Host、原生 Runtime 与 MCP 继续从该入口取得版本。
- README 指向 `dist/blender_bridge-0.4.0.zip`，当前拆件夹具／MCP 冒烟检查同步期望版本。
- [007 历史验证](<007_BlenderBridge_0.3.1_节点图与UE交接升级(done).md>) 保留原版本与验证范围。

## 本次实际验证

- `.venv/Scripts/python.exe -m pytest -q`：27 项通过。
- `uv lock --check --offline`：通过，40 个包的锁定结果有效。
- `tools/build_addon.py`：生成 0.4.0 安装包，43 个 Python 文件与所有权清单逐项 SHA256 一致。
- 全新 stdio MCP 客户端：initialize 回报 `BlenderBridge / 0.4.0`，tools/list 为 7 项，进程在退出连接后结束。
- 任务自有 Blender 5.2.2 LTS 后台 `--factory-startup --python-exit-code 1`：从本次源码实际导入 0.4.0，插件版本元组一致，无打开文件，无用户场景写入，进程正常退出。
- 包 SHA256：`89dbc3c4b7ab5824877a4a28fa47903651221be90e6c477b91b16721b387af45`。

轻量回执位于 `.tmp/artifacts/minor-release/Blender-Win64/latest/validation.json`，原生启动日志同目录保存。本次测试针对版本、打包和接入；未重跑历史模型制作／导出全矩阵，没有新增美术或性能验收结论。

## 安装与边界

本次为仓库发布与包验证，没有覆盖用户当前安装的 add-on、修改 Host 配置或中断既有 Blender／MCP。安装包升级仍使用带所有权核对与备份的既有流程，不能把源码版本等同于现有进程已加载版本。源文件、原始模型和其他仓库的项目内容保持。
