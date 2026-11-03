# 工程复现与操作

从[项目首页](../README.md)开始。工程根为仓库下的`fusion150-final-code`，此目录内有独立内容清单。普通工程构建使用冻结模型，不需要重新训练或重新导出参数。

## 环境

|用途|依赖|
|---|---|
|内容及留存日志校验|Python 3.11+标准库；工程宿主构建另需requirements.txt中的NumPy|
|网页历史回放|Python标准库；串口枚举另需pyserial 3.5|
|实体板操作|AX7Z020B、JTAG、USB-UART、匹配驱动、AMD 2022.2 XSCT及运行中的hw_server|
|HLS/SoC/ARM完整复建|Windows、AMD Vivado/Vitis/Vitis HLS 2022.2、Zynq ARM组件、至少10GiB可用空间|
|训练/量化开发工具|model/requirements.txt；仅开发需要，不能覆盖冻结参数冒充原模型|

将仓库复制到短ASCII路径。以下命令从仓库根目录执行，`E:/vivado`代表包含Vivado、Vitis和Vitis_HLS三个2022.2目录的安装根；请替换为实际位置。

```powershell
$pkg = (Resolve-Path './fusion150-final-code').Path
$py = 'python'
& $py -m pip install -r "$pkg/requirements.txt"
& $py -X utf8 -B "$pkg/tools/verify.py" --package $pkg
```

## 硬件和固件构建

完整链路：冻结检查→1796条宿主/独立C验证→HLS Csim/综合/六例RTL/IP→150MHz SoC/普通及扩大STA→XSA/BSP→validation、benchmark、lifecycle ELF。

```powershell
& $py -X utf8 -B "$pkg/tools/build.py" --package $pkg --out E:/fpga/build01 --xilinx E:/vivado
```

输出目录必须全新且位于工程包外。完整链路和实际日志说明见[原工程README](../fusion150-final-code/README.md)。五用途固件可另外使用随原XSA保存的BSP重编译：

```powershell
& $py -X utf8 -B "$pkg/tools/build_firmware.py" --package $pkg --out E:/fpga/firmware01 --xilinx E:/vivado
```

这包括validation、benchmark、lifecycle、stress和official。新工件保存在输出目录，原`release`工件继续保留。

## 网页演示

```powershell
& $py -X utf8 -B "$pkg/demo-ui/server.py" --data E:/fpga-demo-runs
```

打开 <http://127.0.0.1:8765>。无板时先使用黄色标记的真实历史回放。实板前按[软件README](../fusion150-final-code/demo-ui/README.md)准备hw_server、本次供电/JTAG/实际串口和独占条件；页面操作会调用原release工件。

运行输出在包外，服务重启时沿用同一个`--data`目录可查看既有记录。停止日志采集不等于停止FPGA计算。3121连接失败时先检查AMD hw_server，不要据此判断模型数值失败。

## 官方test及证据

原2026-10-29官方test板验的UART已包含在工程内，普通`verify.py`会离线逐值复核。若另行实际采集新的official用途UART，可以按原工具接口复核：

```powershell
& $py -X utf8 -B "$pkg/tools/verify.py" --package $pkg --official-uart E:/fpga/board-official01/uart.bin --out E:/fpga/official-review01
```

这条命令本身不会下载或运行板卡。官方test用于冻结后的独立终评，不用于继续挑选模型或性能候选。包含UART输出的整段运行时间不作为单次推理延迟。

构建、下载、逐值检查、汇总检查和历史回放的覆盖范围见[验收范围](RESULTS.md)。
