# 邻境

邻境是智能应用创新开发大赛赛题四（银行与小区信息采集及查询系统）的参赛项目，以深圳信息职业技术大学周边为试点。

## 当前进度

已完成学校定位及周边银行、小区的接口验证。以学校为中心查询 3 公里范围，两类各返回第一页 10 条。名称、地址和有效坐标在两组样本中的字段覆盖均为 10/10，地点分类与真实性仍待抽查。

## 运行接口验证

在 Windows 的终端执行 `python probe_amap.py`，按提示在本机输入高德 Web 服务 Key，选择对应的学校地点。程序最多发出三次请求，并在 `reports/` 生成字段覆盖报告。使用 `python probe_amap.py --self-test` 可在离线环境检查字段统计逻辑。

[查看首次验证报告](docs/验证证据/首次接口验证_20261106.md)

## 运行离线流程演示

在 Windows 双击 `打开邻境演示.cmd`，或在项目目录运行 `python demo_web.py --open-browser`。在浏览器依次点击「查附近」「提交纠错」「审核通过」。启动窗口会显示本机访问地址，关闭窗口后演示结束。

在项目目录执行 `python demo_workflow.py`。演示使用虚构地点，依次展示周边查询、提交地址纠错、审核通过及查询更新。数据库只存在于本次运行的内存中。演示不需要 Key 或网络。

后续将接入可持久化的真实数据，扩展地图、列表、账号权限及定时更新。

## 地点数据入库

双击 `打开真实地点查询.cmd` 可以导入并浏览首批真实样本，默认范围为 3 公里。访客可在 ATM 查询结果下提交地址建议。审核时使用启动窗口显示的本次口令登录管理员模式。口令与登录状态随程序重启失效，已通过的本机修订和审核记录保存在 `data/pilot.sqlite`。地点来源、坐标精度与许可见[样本说明](samples/README.md)。

`python import_places.py 数据文件.json` 只检查数据。确认允许存储后，可添加 `--db data/linjing.sqlite` 写入已创建的 `data` 目录。入库后保留来源、使用依据和导入时间。同一来源编号重复导入会跳过，已审核修改不会被覆盖。网页教学演示继续使用独立的虚构数据。

JSON 顶层包含 `coordinate_system`（目前只接受 `WGS84`）、`source_url`、`permission_url`、`school` 和 `places`。`school` 包含 `longitude`、`latitude`、`source_url`、`permission_url`。`places` 中每条包含 `source_id`、`kind`（`bank`、`atm` 或 `community`）、`name`、`address`、`longitude`、`latitude`。程序检查链接格式和 3 公里范围，使用依据需人工核对。
