# 可选人物估算（实验）

监控页可估算疑似成人、疑似儿童和未确定人数。使用预训练 YOLOv8 Pose 提取关键点，再执行比例规则和多帧投票；没有训练成人/儿童专用分类器，不测厘米身高，不识别具体学生。真实准确率尚未验证。

## 网页操作

1. 正常按 F5 启动网页，管理员登录后进入实时监控。
2. 在视频下方切换“启用人物估算（实验）”。默认关闭；开启会启动一个后台识别进程，首次加载模型需等待片刻。
3. 关闭开关会停止后台识别进程，清空页面估算人数。关闭不影响原有 RDK 视频、摔倒/斗殴识别或环境传感器。
4. 普通用户只能查看管理员启用后的结果，不能开关模型；关闭监控或视频权限后不能读取人数。多个浏览器共享电脑端的一个开关和一个进程。
5. 网页服务重启后恢复关闭。正常关闭网页服务也会停止工作进程；VS Code 强制停止后，子进程通过父进程管道关闭信号退出；关闭浏览器标签页不等于关闭服务或模型。

当前在画面下方显示人数，人物分类框不叠加到网页视频中。模型未安装、快照不可用、进程退出、数据过期时会提示，不会用历史人数冒充实时结果。

## 新电脑准备环境

可选依赖使用独立环境，基础网页和语音环境不需要安装这些依赖。仓库根目录下执行：

```powershell
python -m venv output/person-type-env
& ./output/person-type-env/Scripts/python.exe -m pip install -r scripts/requirements-person-type.txt
New-Item -ItemType Directory -Force output/models | Out-Null
Invoke-WebRequest -Uri 'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n-pose.pt' -OutFile output/models/yolov8n-pose.pt
```

Linux/macOS 环境使用 output/person-type-env/bin/python。控制器优先选择本项目 output/person-type-env 中的 Python，否则使用网页服务的 Python。可通过 PERSON_TYPE_PYTHON、PERSON_TYPE_MODEL 指定其他本机解释器和本地模型路径。这两个选项只由电脑端环境配置，网页不接受任意路径或视频 URL。

网页开关不会自动下载模型、安装依赖。启动时缺少依赖或模型会明确提示。运行文件、依赖和权重都在被 Git 忽略的 output 中，不提交到仓库。

## 画面来源与负载

控制器固定从当前 RDK_BASE 对应的 /snapshot 获取图片，最多每秒估算 3 次，避免新增一条 /video_feed 连接。RDK 必须提供 /snapshot，且原有视频采集/识别程序需运行。仍有额外电脑推理和少量网络负载；没有实测前不能保证延迟或准确率。

快照和网页视频不是逐帧同步，接口时间表示本机本次处理完成时间，不是摄像头原始曝光时间。如果上游持续返回同一张旧快照，当前接口无法单独证明摄像头仍在更新。

## 运行与逻辑

- dashboard/person_type_runtime.py：单进程启停、运行编号隔离、旧结果过滤和状态接口。
- scripts/person_type_demo.py：姿态推理和投票，快照失败时显示暂不可用并重试。
- dashboard/person_type.py：比例规则。当前帧未知时保持未知；未知帧计入投票分母；没有稳定跟踪 ID 时不跨人物复用历史，轨迹超时清理。
- output/person-type-runtime/<运行编号>/：独立日志和结果，不读取或覆盖旧 dashboard/person_types.json。

输出中的 agreement 只是投票一致性，不是分类准确率，网页不显示为“准确率百分比”。缺少关键点置信度时保守输出未知。

## 单独实验

```powershell
& ./output/person-type-env/Scripts/python.exe scripts/person_type_demo.py --source 'http://RDK_IP:5000/snapshot' --snapshot --no-show --model output/models/yolov8n-pose.pt --output output/manual-person-types.json
```

默认需要本地模型，不会自动下载。单独脚本输出不会被网页自动读取，网页只读取自己启动的进程结果；避免旧实验结果与实际开关状态混用。直接使用摄像头 0 或 /video_feed 的独立实验仍支持，但可能增加采集负载。

## 验证边界

自动化测试验证登录权限、开关、单实例启停、旧结果和过期过滤及已修复的规则问题。测试摄像头与模型输入为隔离夹具。使用本地权重进行无人物图片推理可验证模型能加载；它不能代替成人、儿童、坐姿、遮挡、距离变化的实机准确率验证。现场仍需校准比例阈值。
