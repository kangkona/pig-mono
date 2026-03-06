# pig-messenger

通用多平台消息机器人框架，提供生产级特性。

[English](./README.md) | 简体中文

## 特性

- **统一抽象**：单一 API 支持 Telegram、Slack、Discord、WhatsApp、飞书
- **流式支持**：3 种流式策略（草稿/编辑/批量），实现实时响应
- **分布式状态**：基于 Redis 的状态管理，支持代理锁和后续队列
- **生产就绪**：重试逻辑、错误处理、优雅关闭
- **类型安全**：完整类型提示和基于 dataclass 的模型

## 安装

```bash
pip install pig-messenger
```

可选依赖：
```bash
pip install pig-messenger[redis]       # 分布式状态管理
pip install pig-messenger[encryption]  # 凭证加密
pip install pig-messenger[telegram]    # Telegram 适配器
pip install pig-messenger[slack]       # Slack 适配器
pip install pig-messenger[discord]     # Discord 适配器
pip install pig-messenger[whatsapp]    # WhatsApp 适配器
pip install pig-messenger[feishu]      # 飞书适配器
pip install pig-messenger[all]         # 所有适配器
```

## 快速开始

```python
from pig_messenger import MessengerManager, MessengerRegistry, MessengerType
from pig_messenger.adapters.telegram import TelegramMessengerAdapter

# 注册适配器
@MessengerRegistry.register(MessengerType.TELEGRAM)
class MyTelegramAdapter(TelegramMessengerAdapter):
    pass

# 创建管理器
def agent_factory(message, thread):
    return f"回声: {message.text}"

manager = MessengerManager(agent_factory=agent_factory)

# 处理事件
await manager.handle_event(
    MessengerType.TELEGRAM,
    raw_event,
    adapter=adapter
)
```

## 架构

### 核心组件

- **BaseMessengerAdapter**：平台适配器的抽象基类
- **MessengerThread**：发送消息的统一接口，支持流式传输
- **MessengerManager**：协调消息生命周期和代理执行
- **MessengerState**：基于 Redis 的分布式状态管理
- **MessengerRegistry**：基于装饰器的适配器注册

### 平台适配器

| 平台 | 特性 | 字符限制 |
|------|------|----------|
| **Telegram** | 草稿流式、文件上传 | 4096 |
| **Slack** | Block Kit、反应、Markdown 转换 | 3500 |
| **Discord** | 线程、反应、嵌入 | 2000 |
| **WhatsApp** | 基于 Twilio | 1600 |
| **飞书** | 卡片消息、流式更新 | 自定义 |

## 流式策略

MessengerThread 自动选择最佳流式策略：

1. **草稿流式**（Telegram）：原生草稿帧，最终提交
2. **编辑流式**（Slack、Discord）：发送初始消息，定时编辑，溢出时自动分割
3. **批量回退**：收集所有块，分割，顺序发送

## 配置示例

### Telegram

```python
from pig_messenger.adapters.telegram import TelegramMessengerAdapter, TelegramConfig

config = TelegramConfig.from_env()  # 从环境变量加载
adapter = TelegramMessengerAdapter(config=config)
```

环境变量：
```bash
TELEGRAM_BOT_TOKEN=your_bot_token
```

### Slack

```python
from pig_messenger.adapters.slack import SlackMessengerAdapter, SlackConfig

config = SlackConfig(
    bot_token="xoxb-...",
    signing_secret="..."
)
adapter = SlackMessengerAdapter(config=config)
```

### 飞书

```python
from pig_messenger.adapters.feishu import FeishuAdapter

adapter = FeishuAdapter(
    app_id="cli_xxx",
    app_secret="xxx"
)
```

## 分布式状态管理

```python
from pig_messenger import MessengerState
import redis.asyncio as redis

# 创建 Redis 连接
redis_client = redis.Redis(host='localhost', port=6379)

# 初始化状态管理
state = MessengerState(redis_client=redis_client)

# 在管理器中使用
manager = MessengerManager(
    agent_factory=agent_factory,
    state=state
)
```

## 高级特性

### 流式响应

```python
async def streaming_agent(message, thread):
    async def generate_chunks():
        yield "正在思考"
        yield "..."
        yield "\n\n这是流式响应！"

    # 自动选择最佳策略
    await thread.stream(generate_chunks())
```

### 文件上传

```python
# 从 URL 上传
await thread.post_file(
    url="https://example.com/file.pdf",
    filename="document.pdf"
)

# 从内容上传
await thread.post_file_content(
    content=file_bytes,
    filename="image.png",
    content_type="image/png"
)
```

### 结构化消息（Slack Block Kit）

```python
blocks = [
    {
        "type": "section",
        "text": {"type": "mrkdwn", "text": "*你好世界*"}
    }
]
await thread.post_blocks(blocks, text_fallback="你好世界")
```

## 开发

```bash
# 安装开发依赖
pip install pig-messenger[dev]

# 运行测试
pytest tests/

# 类型检查
mypy src/pig_messenger/

# 代码格式化
ruff format src/
```

## 许可证

MIT

## 相关链接

- [GitHub 仓库](https://github.com/kangkona/pig-mono)
- [问题反馈](https://github.com/kangkona/pig-mono/issues)
