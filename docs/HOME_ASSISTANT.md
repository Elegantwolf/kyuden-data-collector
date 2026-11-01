# Home Assistant 本地接入

采集器通过 MQTT Discovery 提供今日用电、累计用电、Matter 兼容累计用电、最后成功采集时间和采集器状态。未配置 MQTT 时功能完全关闭，不影响采集和 SQLite。

## MQTT 配置

先在 Home Assistant 中安装并配置 MQTT broker／MQTT integration。然后在采集器本机创建已被 Git 忽略的 `secrets/kyuden.env`：

```sh
KYUDEN_MQTT_HOST=homeassistant.local
KYUDEN_MQTT_PORT=1883
KYUDEN_MQTT_USERNAME=replace_me
KYUDEN_MQTT_PASSWORD=replace_me
# KYUDEN_MQTT_TLS=true
```

下一次成功采集会发布 retained discovery 和状态。HA 中应出现 `Kyuden Data Collector` 设备。`Today Energy` 用于普通卡片展示，不再建议作为 Energy Dashboard 的来源：九电小时数据有延迟，跨日后补采不能修复 MQTT 实体已经生成的旧统计。

## 按真实小时回填 Energy Dashboard

启用可选的本地 HA WebSocket 统计同步，在被 Git 忽略的 `secrets/kyuden.env` 添加：

```sh
KYUDEN_HA_URL=http://homeassistant.local:8123
KYUDEN_HA_TOKEN=replace_with_admin_long_lived_token
```

令牌需有管理员权限，只保存在本机权限 600 的 secrets 文件中。采集成功后会将 SQLite 小时数据按 JST 的真实发生时间转换成 UTC，调用 HA 的 `recorder/import_statistics`，写入独立外部统计 `kyuden:consumption`（Kyuden Hourly Consumption）。该 API 会异步排队，接受请求不等同于 recorder 已完成写入；首次启用后需在 HA 统计页面核对。

Energy Dashboard 的电网来源应**替换**为该外部统计，不要与 Today Energy 同时添加，否则重复计量。不删除或改写原 MQTT 实体历史。每次同步幂等重放，补采/修订以前小时后会重算后续累计值，不把历史用电挪到采集时间。缺失小时不会伪造为零或平均分摊。

定时采集自动检查近三天不足 24 小时或与日结电量不符的日期；每日任务另刷新昨天。手动批量回填（最多 62 天，保留既有 profile 和锁）：

```sh
python -m kyuden --mode both --backfill-days 18 --db data/kyuden.sqlite
```

需在运行前加载 secrets 环境。批量补采只读取九电的真实历史页面，验证日期后 UPSERT，不会把今天图表改标成昨天。回填前建议通过 SQLite backup API 保存一致性备份。

累计值采用“已完成日期的 daily 数据 + 当天 hourly 数据”，避免同一天重复计算。它从本地数据库现有数据起算，不等同于电表终身读数；清空数据库会使 HA 看到一次基线变化。

## Matterbridge / Apple Home

`Matter Cumulative Energy` 与 `Total Energy` 使用相同的累计 kWh 状态，但按
当前部署的 `matterbridge-hass` 要求声明为 `state_class: total_increasing`。它只用于
Matterbridge，不要把它加入 HA Energy Dashboard；Energy Dashboard 使用外部统计
`kyuden:consumption`。

Apple Home 不显示桥接后的独立 `electricalSensor`，因此采集器还提供一个始终为 ON
的 `Power Meter` MQTT switch，作为 Matter plug-in-unit 的可见外壳。Matterbridge 中
保留 `Matter Cumulative Energy` 和 `Power Meter`，继续排除其他 Kyuden 实体。开关
命令不会控制采集器，也不会切断任何物理设备；下次成功发布时状态会恢复为 ON。

该兼容设备没有伪造即时功率：九州电力页面提供的是分时电量，不是实时 W、V 或 A。

## Apple Home 的两个数值显示插座（实验性，默认关闭）

此功能用于“在家庭 App 看数”，不提供原生历史电量图表。只在本地
`secrets/kyuden.env` 启用：

```sh
KYUDEN_APPLE_DISPLAY_PLUGS=true
```

- `Hour Avg`：最近一个已结束、已经采到的小时电量 × 1000 W。
  如 0.35 kWh → 350 W；不是当前实时功率。数据区间和采集时间保存在 HA 实体属性。
- `Yesterday`：昨天的日结 kWh 数字直接编码为 W。
  如 6.7 kWh → 6.7 W；**仅显示编码，不是真实功率**，不要用于自动化/计费。

两个设备各有独立 identifiers、虚拟 outlet 和 power sensor；命令发布到专属且无消费者
的 `kyuden/display/.../outlet/set`，不关联任何真实灯、插座或继电器。
**重新配对迁移后，内部桥接名称固定为 `Hour Avg` 和 `Yesterday`。** matterbridge-hass 1.6 的 MutableDevice
使用 `new MatterbridgeEndpoint(..., { id: this.deviceName })`；即使 HA device ID 和序列号
不变，修改设备名也会换端点编号，使 Apple Home 丢失原卡片/房间绑定。
2026-11-01 用户授权仅重新配对用电桥，并将初始名称改为上述英文短名。
这是一次有意改变桥接身份的迁移，不能作为普通在线改名操作重复执行。
后续不改 HA/MQTT 设备名、name_by_user 或插件命名后缀。
辅助配置工具仅从白名单移除本功能旧中文身份名称，保留其他设备。可用
`--no-restart` 仅保存配置，之后按后台正常服务重启流程应用，避免插件热重载卡住。
Matterbridge-hass 要求功率传感器声明 `state_class: measurement` 才创建电气测量 cluster。
因此 HA 可能为这两个新 W 实体保存独立的短期/长期均值历史；昨天实体的历史仅是显示编码，
不是物理功率。它们不提供虚构 energy，不改写既有 kWh 统计，不自动加入 Energy Dashboard，
也不要对它们做功率积分或用于真实能耗计算。
缺昨天日结时不可用，不回退到前天；近期数据区间/采集时间过期也不可用，不伪造零。
连续三小时未收到刷新，power sensor 在 HA 中过期。日结数据每天自然切换。

配置会在正常定时采集成功后发布。无需重新登录或爬取的手动刷新：

```sh
# 运行前加载 secrets 环境，使用现有 MQTT 配置
python -m kyuden --publish-displays-only --db data/kyuden.sqlite
```

它只读 SQLite，只发布四个新 discovery 配置及 display 专属主题，
不改数据库、不更新“最后采集”或采集成功状态、不操作原 Power Meter。

现有 Matterbridge-hass 可将每个新 HA 设备的 switch 和 power 合并暴露。
辅助配置脚本默认只检查；--apply 才创建 HA“Energy”区域、将两个显示设备移入该区域并加入
**现有白名单**并只重启 HA 插件，不重置桥、不修改配对，不改变已有实体。
脚本在内存中复用该插件既有 HA 连接配置，不新建令牌；应用前保存含凭据的
config 备份到 `secrets/display-backups`，权限 600，禁止上传。

```sh
python scripts/configure_apple_displays.py --matterbridge-url http://HA_IP:8283
python scripts/configure_apple_displays.py --matterbridge-url http://HA_IP:8283 --apply
```

若插件的 host 是 add-on 内部地址，可补上 `--ha-url http://HA_IP:8123`，
指向**同一 HA 实例**的局域网地址，不会更改插件的既有 host 或凭据。

验收不能仅看 HA 数值或出现插座：Matter 端必须同时有 OnOffPlugInUnit (0x010A)、
ElectricalSensor (0x0510) 和 ElectricalPowerMeasurement.activePower。
后者使用 mW，例如 HA 的 200 W 应输出 200000，6 W 应输出 6000。
省略 measurement 标记时，插件会忽略 sensor，生成只有开关的设备。
插件热重载请求被接受不代表设备注册完成；若长期 locked 且注册数为零，
应检查初始化情况，必要时使用后台正常服务重启，保留配置和 Matter 配对，
**不要使用 reset/factory reset 或反复重配整个桥**。

Apple Home 的设备命名、小数显示及卡片更新需手机实测。HA 区域不保证自动变成
Apple Home 房间，请在家庭 App 的初次添加流程将桥和两个设备放到“Energy”房间。
**两个显示值可能混入 Apple Home 家庭/房间的功率汇总，该汇总不能再当成物理功率。**
不应将整屋读数与分项读数一起用于真实统计。

回滚：恢复上述受保护的 Matterbridge 配置备份，关闭环境开关；若要移除 HA
显示实体，仅清除 `homeassistant/{switch,sensor}/kyuden_display/` 下本功能的四条
retained discovery 配置，不要清理整个 `homeassistant/#` 或 `kyuden/#`。

## 登录失效和采集失败

MQTT 状态实体会发布：

- `ok`：采集、入库及已配置的发布路径成功（MQTT 已收到 PUBACK）。
- `auth_required`：登录过期，需要运行人工登录。
- `failed`：其他采集失败。

可在 HA 中以 Collector Status 的状态变化建立自动化。详细错误上下文作为该实体的 MQTT JSON attributes 发布。

状态超过三小时无新消息会在 HA 中变为 unavailable，避免 retained `ok` 永久掩盖停机。网络超时/九电错误页面按采集失败处理，只在明确进入身份提供商登录页面时报告 `auth_required`。

进程退出码：0 成功；1 采集失败；20 明确需要人工登录；21 数据已保存但 MQTT 发布失败；22 数据已保存但 HA 历史同步失败。发布失败不会回滚 SQLite，下次采集会重发最新 MQTT 状态并重新同步历史。

现有 webhook 仍可同时使用。在 HA 创建一个仅限本地的 webhook automation，并把下面地址写入同一个本地 env 文件：

```sh
KYUDEN_NOTIFY_WEBHOOK=http://homeassistant.local:8123/api/webhook/replace_with_long_random_id
```

示例自动化：

```yaml
automation:
  - alias: Kyuden collector alert
    triggers:
      - trigger: webhook
        webhook_id: replace_with_long_random_id
        allowed_methods: [POST]
        local_only: true
    actions:
      - action: persistent_notification.create
        data:
          notification_id: kyuden_collector
          title: 九州电力采集器
          message: "{{ trigger.json.message }}"
```

Webhook ID 相当于密码，不要提交到 Git。HA persistent notification 完全在本地显示；以后可在同一自动化中追加自托管 ntfy、灯光或语音动作。
