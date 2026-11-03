# 技术报告证据入口

本目录是最终作品的精简证据，供报告、海报及代码评审交叉核对。源文件按字节复制，来源及SHA256见sources.json；摘要中的历史工作区路径仅是来源记录，不是复建依赖。

|报告编号|包内入口|范围|
|---|---|---|
|E01–E02|E01-summary.json、E02-summary.json；../../candidate.json及源码|最终版本和模型/硬件/PS身份|
|E03、E15|E03-summary.json、E15-summary.json；../official-uart.bin和../../tests/official|2947条官方测试集、17682 logits；verify.py逐值复算|
|E04|E04-summary.json及E04-raw-*.rpt|原部署150MHz实现的资源、时钟与普通STA|
|E05|E05-summary.json及E05-raw-03至10|两侧1796全验与六次原始配对UART；正式3.7008098%下降|
|E06–E07|E06/E07-summary.json、cold-cycles-review.json、long-stress-review.json|三次真实供电后验证与单段32.612238分钟压力|
|E08–E09|E08/E09-summary.json、warning-disposition-confirmed.md|受控生命周期与原21条Warning处置|
|E10–E12|E10/E11/E12-summary.json|完整复建、迁移及引用记录摘要|
|E14、E16|E14/E16-summary.json、E14原始UART|单次演示与初版历史比较，不是直接匹配加速比|
|D01|../DELIVERY-CHECK.json、../SUBMISSION-REVIEW.json|原完整复建与本次交付工具修订验证分开记录|

完整实现过程和历史失败归档另由队伍保存。本目录未收录旧硬件源码，也未把研究支线当最终部署。E05的promote是该研究配对的速度判定，不是其它工作流的标准版本晋级。
