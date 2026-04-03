# MCP 调用示例

以下示例用于验证 MVP 的 4 步闭环。

## 1) 登录并获取会话

工具：`oem_login`

```json
{
  "oem_base_url": "https://192.168.30.230:7803/em/api",
  "username": "your_oem_user",
  "password": "your_oem_password"
}
```

预期：返回 `session_id`。

## 2) 示例问题一：内存硬件告警

工具：`ask_ops`

```json
{
  "session_id": "YOUR_SESSION_ID",
  "question": "x9mdbadm01 这台主机为什么有硬件内存告警"
}
```

预期：
- 正确识别为 `单目标诊断`
- 命中 `Memory_HardwareCorrupted`
- 调用 OEM 接口：targets + latest_data + metric_time_series + incidents + events
- 返回 4 段结构化回答

## 3) 示例问题二：磁盘错误趋势

工具：`ask_ops`

```json
{
  "session_id": "YOUR_SESSION_ID",
  "question": "x9mceladm01 最近有没有磁盘错误上升"
}
```

预期：
- 正确识别为 `趋势分析`
- 命中 `DiskErrorCount`
- 调用 OEM 接口：latest_data + metric_time_series + incidents + events
- 返回 4 段结构化回答

## 4) 缺参数追问验证

工具：`ask_ops`

```json
{
  "session_id": "YOUR_SESSION_ID",
  "question": "最近磁盘错误怎么样"
}
```

预期：
- `need_follow_up = true`
- 返回明确追问，例如“请补充目标名称”

