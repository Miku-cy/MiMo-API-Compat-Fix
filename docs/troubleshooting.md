# 故障排除指南

## 常见问题

### 1. 代理服务器启动失败

**错误：`Address already in use`**

```bash
# 查找占用端口的进程
lsof -i :9090
# 杀掉进程或换一个端口
python proxy/server.py --port 9091
```

**错误：`No module named 'fastapi'`**

```bash
pip install -r requirements.txt
```

**错误：`MIMO_API_KEY not set`**

```bash
export MIMO_API_KEY=your-api-key
# 或
python proxy/server.py --api-key your-api-key
```

### 2. 400 Bad Request 错误

**原因：** MiMo API 要求 `assistant` 消息有 `tool_calls` 时必须带 `reasoning_content`。

**解决：**
- 使用代理（自动修复）
- 或手动在每个 assistant 消息中添加 `"reasoning_content": ""`

### 3. 推理模式不显示

**检查清单：**
1. 模型配置中 `reasoning: true` 是否设置
2. `thinkingFormat: "deepseek"` 是否配置
3. 工具 UI 中的 thinking toggle 是否开启
4. 是否发送了 `/reasoning on` 命令

### 4. OpenClaw 补丁失效

**原因：** OpenClaw 更新后源码被覆盖。

**解决：** 重新运行补丁脚本
```bash
python scripts/patch_openclaw.py
```

### 5. 工具配置不生效

**检查：**
1. 配置文件路径是否正确
2. JSON 格式是否有效
3. 工具是否重启
4. 代理是否正在运行

### 6. 流式响应中断

**原因：** 代理超时或上游连接断开。

**解决：**
- 检查网络连接
- 增加超时时间（修改 `proxy/server.py` 中的 `timeout` 值）
- 检查 MiMo API 状态

### 7. Anthropic 协议转换错误

**原因：** 消息格式不兼容。

**解决：**
- 检查工具是否支持 OpenAI 协议（优先使用 OpenAI 协议）
- 查看代理日志：`MIMO_LOG_LEVEL=DEBUG python proxy/server.py`

## 获取帮助

1. 查看代理日志
2. 运行验证脚本：`python scripts/verify.py`
3. 提交 Issue 到 GitHub
