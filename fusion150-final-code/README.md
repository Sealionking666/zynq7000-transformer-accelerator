# 融合150MHz Transformer 最终版代码

这是AX7Z020B / XC7Z020CLG400-2平台的最终PS/PL协同定点Transformer工程。PL运行单次调用的整网融合内核，PS负责生产驱动、输入复制、缓存维护、启动、结果读取与保护检查。只提供这一版工程。

最终部署bit SHA256：`c5e1a3bb1d4cae7698bf39458b76aa71fa918e79f4252b3c880d478ae617bde2`。最终源码身份及原XSA见`candidate.json`；逐文件来源与hash见`provenance.json`和`MANIFEST.json`。


## 2026年11月3日 数据集选择

网页“完整验证的数据集”可选择开发集1796条或官方test2947条，分别复用原validation/official ELF及run_board.py对应purpose。官方日志使用原verify.py逐logit核验；benchmark仍固定6个输入。切换选项会清空本次条件确认。结果按实际任务区分数据集，不随选择框修改。启动前准备AMD hw_server；详情见demo-ui/README.md。

本次UI修订16项离线测试与真实浏览器检查通过；实板请求在浏览器验证时全部拦截，仅运行历史回放。新增official网页实板端到端尚未在本次修订后验收，不继承历史官方板测成绩。新证据见evidence/DEMO-UI-DATASET-CHECK.json；下方11月2日的软件实板记录保留原范围。模型/硬件/原工具/release均未改。

## 本地网页操作与展示 2026年11月2日新增

在`demo-ui`运行`start.cmd`，或用已有Python执行`python -X utf8 -B demo-ui/server.py --data E:/fpga-demo-runs`，浏览器打开 http://127.0.0.1:8765 。只用Python标准库提供页面；UART需本工程已有pyserial 3.5。页面默认仅监听127.0.0.1，不自动下载或运行。详细环境、AMD hw_server准备、本次板卡确认、validation→benchmark操作和输出说明见`demo-ui/README.md`。

新增界面复用原run_board.py/download.tcl与原release，不训练、改时钟或替换模型/bit。已完成14项离线回归、真实历史回放及COM5本轮validation/benchmark，截图与原始精简证据见`demo-ui/ACCEPTANCE.md`和`evidence/DEMO-UI-CHECK.json`。validation UART仅支持独立汇总核验，逐值比较由原固件执行；benchmark独立核对66调用/60正式计时。本次单轮40.668微秒不替代原正式三配对40.671微秒。

原工具中途停止的实板清理、拔线/断电及第二机展示软件部署尚未验证；停止采集不表示停止FPGA计算或复位。下方此前“仅离线接口检查、没有新板操作”是当时交付记录，本次新增板测范围仅以上两用途，不回改历史验收记录。运行输出必须在整个代码包及demo-ui之外；已纳入清单的evidence/screenshots是封存交付材料，不是运行输出目录。

## 目录和边界

|目录|内容|
|---|---|
|`hardware/hls/src`、`hardware/hls/host`|最终融合内核、冻结参数、六例RTL向量和1796例宿主验证|
|`hardware/soc`|最终150MHz ACP互连、PS/DDR配置、实现与扩大时序检查Tcl|
|`software/ps`|同一生产驱动，以及validation、benchmark、lifecycle、24000轮stress、2947条official五种程序入口|
|`software/bsp`、`software/link`|与原部署XSA对应的BSP、完整生成源、启动/库和链接配置|
|`model`|最终使用的冻结模型、训练/受试者划分/量化导出代码和31项模型锁；模型v1.0.0是当前模型版本，不是旧硬件工程|
|`release`|原已测bit/XSA/PS-init及五种用途的最终ELF；不包含过去版本或新复建bit|
|`demo-ui`|Python本地服务与中文网页；真实日志回放、原工具操作、结果/日志导出；详见其README与ACCEPTANCE|
|`tools`|本包校验、完整源码复建、五种固件构建、易失JTAG下载和串口采集入口|
|`tests/official`、`evidence`|冻结官方test向量和2026年10月29日原始板端UART，供离线逐值复核|

部署范围是JTAG加载、内存预置Q16输入，不包含SD/Flash自启动或在线传感器采集。没有携带旧矩阵工程、其它时钟点、packed研究、源码快照ZIP、私人agent配置、Git目录或大体积实现中间产物。模型训练/导出是开发工具，常规构建无需运行，也不要用它们覆盖冻结参数。

## 环境与内容校验

建议将本目录放到短ASCII路径，例如`E:/fpga/fusion150-final-code`。需要Python 3.11+，完整构建需要AMD Vivado/Vitis/Vitis HLS 2022.2和Zynq ARM组件。Windows构建脚本使用AMD目录内的编译器，无需额外安装GCC。

```powershell
$pkg = 'E:/fpga/fusion150-final-code'
$py = 'C:/path/to/python.exe'
& $py -m pip install -r "$pkg/requirements.txt"
& $py -X utf8 -B "$pkg/tools/verify.py" --package $pkg
```

校验覆盖包内文件、31项冻结模型、构建输入映射、原bit/XSA绑定，以及原始2947条板端日志的17682个logits、输入checksum、固件标识和设备计时自洽性。它不会连接板卡或运行模型推理。

## 技术报告与代码定位

报告证据从`evidence/report/INDEX.md`开始，包含正式配对UART、原时序/资源报告和质量、稳定性摘要。模型结构见`model/har_accel/model.py`，整网计算见`hardware/hls/src/har_net.cpp`，生产驱动见`software/ps/har_net_pl.c`。矩阵操作数主要为INT8，累加为INT32；Q16表示16位小数定点接口，非线性中间计算另按源码使用所需位宽。

## 完整源码复建

输出目录必须全新、位于包外，使用ASCII路径并保留至少10GiB空间。`--xilinx`指向包含Vivado、Vitis、Vitis_HLS三个2022.2目录的安装根。

```powershell
& $py -X utf8 -B "$pkg/tools/build.py" --package $pkg --out E:/fpga/build01 --xilinx E:/vivado
```

链路：冻结检查→1796例宿主/独立C参考→HLS Csim/综合/六例RTL/IP→150MHz SoC/普通及扩大STA→XSA/BSP→validation、benchmark、lifecycle三种ELF。阶段命令、输入hash和原始日志保存在输出目录，失败停止且保留，不覆盖旧输出。工具执行使用共享EDA锁及四线程Vivado。

构建会生成新的bit和ELF；实现字节或master ID可能变化。新工件须独立审查和上板验证，不能继承`release`中原bit的性能、Warning处置或板测成绩；脚本不会自动下载新工件。

若只需要从当前最终源码重新编译五种用途ELF，可使用随原XSA保存的BSP：

```powershell
& $py -X utf8 -B "$pkg/tools/build_firmware.py" --package $pkg --out E:/fpga/firmware01 --xilinx E:/vivado
```

该命令包括stress和official程序，源码、编译、链接日志和新ELF全部落盘。原`release`工件不被替换。模型开发环境另见`model/requirements.txt`，无需为了普通工程复建安装PyTorch。

## 原最终版板端演示

先确认板卡正确供电、SW1为JTAG模式，CP210x串口115200，且当前操作者独占板卡与串口。按板卡手册接线；新会话不能继承旧授权。使用`tools/run_board.py`的显式当前状态参数，它只下载`release`中的原工件到易失PL/DDR，不写Flash或SD。先完整validation，再benchmark：

```powershell
& $py -X utf8 -B "$pkg/tools/run_board.py" --purpose validation --port COM5 --out E:/fpga/board-validation01 --xilinx E:/vivado --powered --jtag --exclusive --authorize-volatile-download
& $py -X utf8 -B "$pkg/tools/run_board.py" --purpose benchmark --port COM5 --out E:/fpga/board-benchmark01 --xilinx E:/vivado --powered --jtag --exclusive --authorize-volatile-download
```

若要运行官方测试集，把`--purpose`设为`official`并使用全新的输出目录。采集完成后独立复核新日志：

```powershell
& $py -X utf8 -B "$pkg/tools/verify.py" --package $pkg --official-uart E:/fpga/board-official01/uart.bin --out E:/fpga/official-review01
```

此命令逐值检查新日志及其固件标识、输入校验和与设备时间；设备时间包含UART，不能作为单次推理延迟。其它用途仍保存原始采集状态，不因出现结束行自动变成独立验收通过。所有构建、采集和核验输出都必须位于包外，防止破坏内容清单。

软件只使用已运行的本地hw_server（默认3121），请通过已安装的AMD工具启动它；脚本不会关闭其它操作者的服务。若出现故障，保留输出和fault记录，停止后续板动作并人工检查，不自动重试。

validation预期1796样本、10776 logits、1449正确、checksum `bd0b22ad`；official预期2947样本、17682 logits、2472正确、checksum `fe0d23fe`；stress预期24000轮、43,104,000次重复推理，checksum `6f1198c5`，完整验收还须检查单段设备时间至少1800秒。采集成功不单凭终止行宣称通过全量数值验收；原始记录保留供独立复核。

## 已有验收事实

正式同频H-bank→融合的匹配AB/BA/AB结果：42.233998775→40.670998821μs，改善3.7008098%。计时为内存Q16到完整PS/PL logits，含生产guard/poison/cache/control；不是所有输入的最坏延迟或持续吞吐。

原bit已完成1796开发集全验、三次真人断电后JTAG全验，以及设备连续32.612238分钟压力。另于2026年10月29日完成2947条官方test实体板全量执行，17682 logits与冻结参考精确一致，accuracy83.88191381%、macro-F1 83.72657272%。原21条DSP Warning由队长确认保留原等级。详细验收归档由队伍另行保存，本代码包保留必要的精简来源和复核入口。

本目录是本地待发布代码。比赛页面和GitHub上传由队伍负责人完成；不含上传成功或已开源的声明。第三方使用条件见`THIRD_PARTY.md`。

## 2026年11月2日本地交付验证

最终版目录整理后已实际执行新入口的预检、1796例宿主验证、HLS Csim/综合/六例RTL/IP、SoC实现/普通及扩大STA、BSP及ARM构建。59项构建输入与此前通过的完整复建输入字节一致；另核对60项原最终固件编译输入一致。

五种固件均使用随原XSA保存的BSP重新编译和链接，其ELF入口及全部PT_LOAD地址、大小、标志和加载内容与原最终工件完全一致。完整SoC复建产生的新bit只作为离线检查输出，未放入release，也未继承原板测成绩。板端采集入口本轮仅做离线接口检查，没有新板操作。

精简验证结果见`evidence/DELIVERY-CHECK.json`。RAR的实际大小、hash、测试和独立解压核验由目录外的交付回执记录；它们不等同于比赛网站或GitHub上传回执。

## 2026年11月2日提交审查修订

修正构建记录的package_manifest_sha256字段，并单独记录candidate_sha256；工具拒绝将输出写入包内；补充官方UART独立复核入口和报告证据。此前完整EDA及五用途ELF验证记录仍保留原日期/原工具语义，本轮验证另见evidence/SUBMISSION-REVIEW.json。模型、HLS/SoC、生产PS、BSP及release部署工件逐字节未改；没有新增板测或性能结论。
