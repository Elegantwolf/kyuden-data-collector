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

下一次成功采集会发布 retained discovery 和状态。HA 中应出现 `Kyuden Data Collector` 设备。把其中的 `Today Energy`（单位 kWh，energy，state class total_increasing）添加到 Settings > Dashboards > Energy 的电网用电来源。该实体每天归零，避免次日修订前一天结算值时把修订量错误记到当天。

累计值采用“已完成日期的 daily 数据 + 当天 hourly 数据”，避免同一天重复计算。它从本地数据库现有数据起算，不等同于电表终身读数；清空数据库会使 HA 看到一次基线变化。

## Matterbridge / Apple Home

`Matter Cumulative Energy` 与 `Total Energy` 使用相同的累计 kWh 状态，但按
当前部署的 `matterbridge-hass` 要求声明为 `state_class: total_increasing`。它只用于
Matterbridge，不要把它加入 HA Energy Dashboard；Energy Dashboard 使用每天归零的
`Today Energy`。

Apple Home 不显示桥接后的独立 `electricalSensor`，因此采集器还提供一个始终为 ON
的 `Power Meter` MQTT switch，作为 Matter plug-in-unit 的可见外壳。Matterbridge 中
保留 `Matter Cumulative Energy` 和 `Power Meter`，继续排除其他 Kyuden 实体。开关
命令不会控制采集器，也不会切断任何物理设备；下次成功发布时状态会恢复为 ON。

该兼容设备没有伪造即时功率：九州电力页面提供的是分时电量，不是实时 W、V 或 A。

## 登录失效和采集失败

MQTT 状态实体会发布：

- `ok`：采集和入库成功。
- `auth_required`：登录过期，需要运行人工登录。
- `failed`：其他采集失败。

可在 HA 中以 Collector Status 的状态变化建立自动化。详细错误上下文作为该实体的 MQTT JSON attributes 发布。

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
