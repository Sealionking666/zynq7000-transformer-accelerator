# 融合150 本地操作与展示软件

用于比赛现场操作、录屏和报告截图。中文单页网页由Python本地服务提供，默认且仅监听 **127.0.0.1:8765**，没有前端框架、云端服务或在线资源。模型仍由原PS/PL工程执行；网页不执行模型推理。

## 安装与启动

Python 3.11或更新版本。历史回放、网页及日志导出只用标准库；串口枚举和实体板采集另需pyserial 3.5。沿用工程已有Python环境即可，不需要PyTorch、Node.js或重新构建硬件。

```powershell
# 在本目录打开PowerShell；替换为你实际使用的Python。
$py = 'C:/path/to/python.exe'
& $py -m pip install -r requirements.txt
& $py -X utf8 -B server.py --data E:/fpga-demo-runs
```

浏览器打开 <http://127.0.0.1:8765>。默认输出在 `%LOCALAPPDATA%/fusion150-demo/runs`；原采集工具要求输出路径为ASCII，若用户名含中文，请显式指定如 `E:/fpga-demo-runs`。输出不能放入本软件或最终代码包内。

双击 `start.cmd` 也可启动（需Windows Python Launcher `py -3`）。如果使用已有虚拟环境，先设置 `FUSION_DEMO_PYTHON` 为该环境的python.exe。命令行参数可透传，例如 `start.cmd --data E:/fpga-demo-runs --port 8765`。

独立目录默认查找相邻 `fusion150-final-code`；纳入最终代码包的 `demo-ui` 默认查找父目录。迁移后也可指定：

```powershell
& $py -X utf8 -B server.py --package E:/fpga/fusion150-final-code --data E:/fpga-demo-runs
```

## 建议演示顺序

1. 启动服务、打开网页。此时只显示“当前连接未确认”，不会自动下载、打开串口或启动任务。
2. 无板彩排：选择真实历史日志并点“历史日志回放”。黄色横幅始终标明回放、日期/归档日期和来源。官方test回放可显示原始分类明细；validation和benchmark没有分类明细，显示“未提供”。
3. 实板前：按板卡手册核实本次供电、SW1 JTAG、UART和独占状态。启动已安装AMD工具的hw_server（默认3121）；本软件复用已有服务，不自动关闭别人的服务。例如在独立终端执行 `E:/vivado/Vivado/2022.2/bin/hw_server.bat -s tcp:127.0.0.1:3121`。
4. 点击“刷新枚举”，选择或填写实际COM口；填AMD安装根（如`E:/vivado`，不是`bin`目录），在“完整验证的数据集”选择“开发集 · 1796条”或“官方 test · 2947条”，再展开并逐项确认本次四项条件。切换数据集会清空确认勾选。串口枚举不打开串口，也不能证明板卡或JTAG已连接。
5. 点击“启动开发集验证”或“启动官方 test 验证”。前者调用validation ELF并独立检查汇总，后者调用原official ELF并独立逐值复核2947条/17682 logits；等待结束行、采集退出码0和对应独立核验。再重新确认本次条件，点击“启动benchmark”（固定6个输入，不随数据集选项切换）。所有下载均调用原 `tools/run_board.py` → 原 `download.tcl` → 原release bit/用途ELF，不写Flash/SD。
6. 在记录下拉框查看本轮或已有任务；日志来源可切换UART、AMD下载、工具、预检和任务输出。用“原始UART”“核验JSON”或ZIP导出。截图和录屏应完整保留模式横幅、样本、核验范围及计时说明。

“停止日志采集”向适配进程请求KeyboardInterrupt，由原采集入口的finally关闭UART、清理自己的XSCT子进程及锁。**不表示停止FPGA计算、硬件复位或断电。** 若在已开始下载后停止/失败，原入口可能留下故障锁；保留证据并人工检查，软件不自动删除故障锁或反复重试。中途停止实体板的按钮，本轮只做离线适配清理验证，未主动打断实体板。

## 结果口径

|显示项|含义与限制|
|---|---|
|顶部“已验收指标·历史”|原工件E05三配对40.671微秒、E15官方test 83.88%/2947；不随本次运行变化|
|结束行|只证明收到了完整终止标记，不单独作为验收通过|
|采集进程退出|真实进程退出码；历史回放没有采集进程，显示“无采集进程”|
|validation|1796条开发集；原固件逐logit比较。PC严格核对profile/token、8个进度checksum和最终样本/logits/调用/正确数/checksum，只称“独立汇总核验（非逐logit）”|
|benchmark|严格核对profile/token、频率、66行顺序、预热标志与终止计数；按原timer_hz换算60次正式设备ticks的中位数；UART不含逐项logits或预测|
|official实板/历史回放|实板复用原run_board.py --purpose official及原release/official.elf，原采集上限300秒、外层350秒；两种模式均用原verify.py的official_replay严格复核2947条/17682 logits、标签、预测、输入checksum与计时自洽。回放明确标历史；整段含UART时间不作推理延迟|
|本次实板benchmark|2026-11-02本轮60次正式计时中位40.668微秒，仅单轮功能验证，不替代原三配对性能证据|

设备PS/PL计时边界：内存Q16输入到完整logits，含生产copy/guard/poison/cache/control，排除6预热、JTAG下载、网页响应和UART输出。官方日志整段时间包含UART和逐条校验，不能当作单次延迟或吞吐。没有计时的日志显示“未提供”；进度只使用真实UART报告的计数，不随时间推算。

## 状态、输出与追溯

一次任务对应一个随机编号目录。`request.json`保存用途、数据集与本次确认，`state.json`保存阶段/状态，`*.command.json`保存真实argv、cwd、时间、PID、退出码，`*.log`保存工具输出；`review.json`为独立复核。实板原始记录在`capture/`，含`authorization.json`、`uart.bin`、`download.log`及原始`result.json`。原`captured_unvalidated`不被覆盖，网页独立复核另存。

`files.json`记录任务完成时文件hash快照；`export.zip`包含日志、命令和结果，省略不变的大bit/ELF副本。worker退出观测是后续追加的`worker-exit.json`，不属于早先快照/ZIP；原始运行目录始终完整保留。任务worker独立于网页服务，刷新、关闭网页甚至关闭服务均不会重新开始任务。服务重启会从同一`--data`恢复记录；不会继承页面确认勾选。任务异常中断时保守标为“需人工检查”，不会自动重新下载。

进程内启动互斥、主机共享操作系统锁及原工具board/EDA锁共同防止重复任务。启动第二服务会明确报已有实例；不会绕过旧锁。任务显示“需人工检查”时，先根据输出目录与原PID检查现场；确认旧任务/串口已结束、保存故障记录后由操作者处理，不要盲删锁或更换输出目录来绕过正在运行的任务。正常运行无需手工改状态。

网页按32KiB分段读日志，DOM保留最近约250行/64KiB，不把完整日志塞入页面；完整原始文件不截断。服务日志在启动终端，任务状态不依赖浏览器缓存。

## 验证与截图

详见 `ACCEPTANCE.md`、`evidence/acceptance.json` 和 `screenshots/README.md`。2026-11-02完成14项离线回归、三份真实日志回放及COM5实板validation/benchmark。2026-11-03新增数据集切换后16项离线回归通过，实际浏览器验证两套数据选择、请求路由（实板请求被拦截）、官方历史回放/导出/刷新和响应式布局；该新official网页实板路径尚未在本次修订后重新上板验收。保留开发过程中的一次状态文件共享冲突失败记录；未覆盖或伪填通过。

```powershell
# 确保没有另一个展示服务占用主机共享锁，再运行测试；测试不下载板卡。
& $py -X utf8 -B -m unittest discover -s tests -v
```

测试中的改坏日志与模拟入口均放在明确标注的隔离临时fixture目录，用完清理，不修改真实验收数据。

## 常见问题

- **页面打不开**：确认启动终端没有退出，地址为127.0.0.1及实际端口。8765被占用时用`--port 8766`，不要改成公网监听。
- **py命令不存在**：使用实际python.exe执行server.py，或配置`FUSION_DEMO_PYTHON`。
- **没有串口/pyserial**：在同一个Python环境安装requirements.txt；检查UART线与驱动。也可手填COM口，原工具实际打开时才判断能否使用。
- **XSCT未找到**：安装根下应存在`Vitis/2022.2/bin/xsct.bat`。无需为了本界面重跑HLS或SoC实现。
- **3121连接失败**：先由操作者启动现有AMD hw_server。失败记录保留，不自动启动下载重试。
- **清单验证失败**：不要把日志写到包内；保留错误，核查文件被修改、遗漏或来源错误的原因。界面不会绕过verify.py。
- **看见结束行却未通过**：可能进程仍运行、退出码非零，或独立核验拒绝缺行/错误token/checksum/计时频率等；查看各独立状态和原始日志。

本软件不进行比赛上传、GitHub发布、模型训练、时钟修改或bit替换。网页截图不能替代由队伍拍摄的开发板、电源、JTAG、UART和电脑完整系统实物照。
