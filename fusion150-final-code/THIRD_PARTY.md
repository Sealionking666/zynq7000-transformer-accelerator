# 第三方来源与使用说明

本包只含最终融合150MHz工程及其实际使用的冻结模型，不含过去的加速器版本、候选支线、Git历史或外部工具安装包。模型源码沿用冻结模型v1.0.0，这也是最终版正在使用的模型身份。

UCI HAR数据和派生的冻结输入/参数用于本作品验证。原始数据README保存在`THIRD_PARTY/UCI-HAR-README.txt`，须保留其引用和使用条件；其中原文包含非商业使用限制。本包不以不同日期网页许可信息替换随数据保留的原通知。

引用：Davide Anguita, Alessandro Ghio, Luca Oneto, Xavier Parra, Jorge L. Reyes-Ortiz. A Public Domain Dataset for Human Activity Recognition Using Smartphones. ESANN 2013, Bruges, Belgium, 2013. UCI repository DOI: 10.24432/C54S4K.

`software/bsp`及相关生成的驱动、启动代码和链接文件来自AMD/Xilinx工具，保留原始版权和许可通知。Vivado/Vitis/Vitis HLS 2022.2及其内置IP是外部依赖，使用者自行安装获许可的工具；本包未分发工具安装包。

PyTorch、NumPy、scikit-learn、pytest和pyserial为外部依赖，安装时保留各自许可。训练/导出工具使用`model/requirements.txt`；普通固件构建和内容校验无需重新训练模型。

项目自有代码的公开许可证由实际权利人决定；本次整理没有替全队授予MIT或其它公开许可证。GitHub发布、比赛提交以及队员签署由队伍负责人办理。
