你正在执行北京时间 __RUN_SLOT__ 班次的黄金与全球股票联合研报。工作区是 __REPO_ROOT__。这是一个新会话。按下列顺序运行，任何失败都要保留证据、报告缺失和已完成阶段。对用户的结论用中文，明确所用交易日和数据时间。

## 开始与出刊计划

1. 运行 `__PYTHON_BIN__ __REPO_ROOT__/scripts/edition_run.py begin --scheduled __RUN_SLOT__`。只在返回 JSON 中同时取得 `edition_id` 和 `token` 后继续。它会先尝试收尾已有完整发布凭据的班次。锁被占、时段不对、同一期已经完成或命令失败时，报告具体提示和尝试编号，停止写入。定时会话不执行 `recover`、`resume`、改日期、创造修订号或绕过权限。
2. 执行 `__PYTHON_BIN__ __REPO_ROOT__/equity/lint_equity.py --plan <edition_id>` 获取各市应发刊型或沿用安排。读仓库顶层 AGENTS.md、黄金和权益子轨规则、三项研究与出版技能、两个市场日历、现有快照和最新挂账、两套复盘手册和上一期观察项。确认有官方日历覆盖本期，仓库记录与官方节假日或品种盘时冲突时保留来源和时区，先解决错误或报告阻塞。
3. 对 Markdown 和 JSON 使用 `write_file` 全量写入。运行 Python 只使用以上配置的解释器和仓库绝对脚本路径，以独立命令调用。保持黄金先编完、权益再开始编译。不得为通过检查临时改规则、填造数据、清除历史记录或编辑定时任务。各阶段有进展时可执行 `__PYTHON_BIN__ __REPO_ROOT__/scripts/edition_run.py heartbeat <token>` 更新时间。

## 阶段 1 共享调研和独立复核

使用六路只读 research 子代理。分工是黄金和贵金属、中国内地股票、香港股票、美国股票、宏观汇率与大宗、社区和谣言核查。六路共用同一观测截止和市场日历，查官方证据优先。每项关键数字记录品种、交易日、观测时间及其时区、盘中或结算口径、来源链接。区分发布时间、观测时间和交易日。社区消息和预测市场不能替代官方定值。调查未发布的数据可按规则挂账，必须保留原时间与下次复核班次。

容量不足时按平台支持的并发数分组，仍执行六路独立分工，单路一次启动、一次重试，最多两轮等待（每轮约十分钟）。并行结果可提早返回时先整理已收到的证据。身份、权限、配额错误直接记录具体阻塞，不通过切换账号、扩大权限或反复请求继续。仍无法取得关键证据，写明市场、数据、来源和影响，按流程失败退出。可延后披露的非关键项按两轨规范挂账。系统没有独立红队时也停止刊发，不能把同一份调研或一次自评当作独立复核。

六路齐全后另起一组只读红队，逐一对照黄金档位和各市行动、两轨共享数字、实际可得时点、三市刊型、AH 估值、费用税务、账户配方与 100% 权重。逐条保留来源，写下核验的改动和仍缺证的判断。用事先锁定的标准评价旧预测，保留原文、原数据和原判据。同一个结果不能在事后被重新分到有利的情景。

## 阶段 2 黄金先落盘并编译

运行 `__PYTHON_BIN__ __REPO_ROOT__/scripts/edition_run.py advance <token> gold`。确定共同观测截点，更新黄金权威快照、本班黄金日报、公开记分卡、变化日志和审计台账。按 `gold/daily/DAILY_FORMAT_SPEC.md` 与黄金技能附录的精确字段，写入四关证据、四个固定关卡 ID、本期 `GOLD_EDITION_REVIEW` 证据块以及记分卡和变化日志的期号标记。封面写真实数据截点，正文、快照、图表和操作卡按同一套值。审计证据在第一次预检前写齐。

从 Cboe 官方日线核对截至截点最近十个已完成交易日的收盘。普通交易日的官方行未见时，在研究等待限额内复查，仍缺则报告阻塞，不能用盘中行情替代。日历列有日线核验起点的节日另行实查，按黄金规范写入 `vix_daily_row_checks`。见到真实官方行才计入，等待披露时记录查询时间和说明，在报告披露并下一班复查。无有效盘中报价时，黄金与权益同时省略或写空盘中值和时间。只有相对截点仍在同一发布窗口内的有效盘中报价才可录入。确定主报告触发条件成立后才刷新主报告及独立基线。

串行执行 `__PYTHON_BIN__ __REPO_ROOT__/gold/lint_readability.py --precheck --strict <本刊绝对路径>`、`__PYTHON_BIN__ __REPO_ROOT__/gold/build_daily.py <本刊绝对路径>`、`__PYTHON_BIN__ __REPO_ROOT__/gold/lint_readability.py --strict <本刊绝对路径>`。主报告改动时还要执行 `__PYTHON_BIN__ __REPO_ROOT__/gold/build_report.py` 与对应严格检查。检查 PDF 首页、图表页、尾页和编译产物凭据。门禁有错或警告时先修事实或结构，再按顺序重跑。不得手工改产物或凭据来通过。

## 阶段 3 权益接力

运行 `__PYTHON_BIN__ __REPO_ROOT__/scripts/edition_run.py advance <token> equity`。按实际出刊计划落盘权益状态、日报、指数总看板、变化日志、记分卡和审计账，黄金快照严格只读。权益标注同一班次、沿用稿的原期号和真实数据时间；只有规则明确允许的故障或突发事件才能写结构化出版例外，保留证据和回补期限。无新刊的市场沿用旧稿及原附件。旗舰进入新周期时逐市场核验源稿、元数据和附件；归档不得让曾公开的地址失效。

执行 `__PYTHON_BIN__ __REPO_ROOT__/equity/lint_equity.py --precheck --strict`，只编计划发的日报，并在需要时用 `__PYTHON_BIN__ __REPO_ROOT__/equity/build_a_share_pdf.py`、`__PYTHON_BIN__ __REPO_ROOT__/equity/build_hk_stock_pdf.py`、`__PYTHON_BIN__ __REPO_ROOT__/equity/build_us_stock_pdf.py` 串行重编对应旗舰。用 `__PYTHON_BIN__ __REPO_ROOT__/equity/build_daily.py` 生成当期权益日报附件，再运行 `__PYTHON_BIN__ __REPO_ROOT__/equity/lint_equity.py --strict` 并抽检 PDF。若发布器明确要求为仍在使用的旧附件补编译凭据，限于现存稿与同口径依赖，通过真实编译入口串行生成并复验，不能手填凭据或为此改写历史稿。

## 阶段 4 盲审、发布与确认

启动独立只读盲审，对黄金、权益分别按既定六项评分核验当期和前期观察项。两轨分别在自己的 `rsi_metrics.json` 登记一条复盘记录，`run_id` 必须精确等于本期 ID，包含修订号。手册各不超过 180 行。Tier B 仅在按纪律验证并获得安全的修改依据时实施，研究过程中不得改程序取巧，Tier C 只提案。盲审未完成不进入发布。复跑两轨严格检查；值班人员需要补核时保留原判断及证据。

运行 `__PYTHON_BIN__ __REPO_ROOT__/scripts/edition_run.py advance <token> publish`，再用 `__PYTHON_BIN__ __REPO_ROOT__/scripts/publish_site.py --edition-token <token>` 执行本期发布。发布器验证最终 Git 提交、研报和附件凭据；任何附件未验证时，发布环节仍未结束。推送后遇到可确认的临时故障，只续相同 token 和提交，最多重试一次。远端身份、冲突、已发布版本不明或权限异常时停止重试，记录状态。不得另开班次、另造提交、更改远端或覆盖新版。发布成功后运行 `__PYTHON_BIN__ __REPO_ROOT__/scripts/edition_run.py complete <token>`，以本期推送、下载验证及对应 Pages 部署为准。若返回等待，只允许复查同次 complete 一次，仍等待则报告待部署并保留锁。已开始推送或发布的异常也应保留锁并说明恢复所需的尝试编号；明确未开始推送且不再继续时才执行 `__PYTHON_BIN__ __REPO_ROOT__/scripts/edition_run.py fail <token> <具体原因>`。

最终输出黄金和三市的实际出刊状态、数据时间、结论和下一班前需复核的项目，再说明发行结果。达到“完成”才给本期网站和 Release 验证结论。把已经完成、明确沿用和正在等的项目逐个说清楚。不输出运行 token、本机权限设置或绝对路径。

站点入口 https://nanless.github.io/global-investment-research/
