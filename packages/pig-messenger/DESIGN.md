# pig-messenger Design

**通用消息平台Bot框架 - 比pi-mom更强大!**

---

## 🎯 核心理念

**一次编写,处处运行** - 同一个agent,支持多个消息平台

```
pig-agent-core (核心Agent)
       ↓
pig-messenger (消息框架)
    ↙  ↓  ↘
  Slack Discord WhatsApp Telegram Feishu Matrix ...
```

---

## 🏗️ 架构设计

### 层次结构

```
Application Layer (用户代码)
    ↓
pig-messenger Core (消息抽象)
    ↓
Platform Adapters (平台适配器)
    ↓
Platform SDKs (各平台SDK)
```

### 核心组件

#### 1. MessagePlatform (抽象基类)

```python
from abc import ABC, abstractmethod


class MessagePlatform(ABC):
    """消息平台抽象接口"""

    @abstractmethod
    async def send_message(self, channel_id: str, text: str):
        """发送消息"""

    @abstractmethod
    async def upload_file(self, channel_id: str, file_path: str):
        """上传文件"""

    @abstractmethod
    async def get_history(self, channel_id: str, limit: int):
        """获取历史消息"""

    @abstractmethod
    def start(self):
        """启动平台监听"""
```

#### 2. UniversalMessage (统一消息格式)

```python
class UniversalMessage:
    """平台无关的消息格式"""

    id: str
    platform: str  # slack, discord, whatsapp
    channel_id: str
    user_id: str
    username: str
    text: str
    attachments: List[Attachment]
    timestamp: datetime
    is_mention: bool
    is_dm: bool
```

#### 3. PlatformAdapter (适配器)

```python
class SlackAdapter(MessagePlatform):
    """Slack平台适配器"""


class DiscordAdapter(MessagePlatform):
    """Discord平台适配器"""


class WhatsAppAdapter(MessagePlatform):
    """WhatsApp平台适配器"""
```

#### 4. MessengerBot (统一Bot)

```python
class MessengerBot:
    """通用消息Bot"""

    def __init__(self, agent: Agent):
        self.agent = agent
        self.platforms: Dict[str, MessagePlatform] = {}

    def add_platform(self, platform: MessagePlatform):
        """添加平台支持"""

    async def handle_message(self, msg: UniversalMessage):
        """处理消息(平台无关)"""
        response = self.agent.run(msg.text)
        await self.platforms[msg.platform].send_message(msg.channel_id, response.content)
```

---

## 📦 包结构

```
packages/pig-messenger/
├── src/pig_messenger/
│   ├── __init__.py
│   ├── core.py           # MessengerBot核心
│   ├── platform.py       # MessagePlatform抽象
│   ├── message.py        # UniversalMessage
│   ├── session.py        # 多channel会话管理
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── slack.py      # Slack适配器
│   │   ├── discord.py    # Discord适配器
│   │   ├── whatsapp.py   # WhatsApp适配器
│   │   ├── telegram.py   # Telegram适配器
│   │   ├── feishu.py     # 飞书适配器
│   │   └── matrix.py     # Matrix适配器
│   └── utils/
│       ├── storage.py    # 消息存储
│       └── events.py     # 事件系统
├── examples/
│   ├── slack_bot.py
│   ├── discord_bot.py
│   ├── multi_platform.py
│   └── custom_adapter.py
└── README.md
```

---

## 🎮 使用示例

### 单平台Bot

```python
from pig_messenger import MessengerBot
from pig_messenger.adapters import SlackAdapter
from pig_agent_core import Agent
from pig_llm import LLM

# 创建agent
agent = Agent(llm=LLM(provider="anthropic"), tools=[...])

# 创建bot
bot = MessengerBot(agent)

# 添加Slack支持
slack = SlackAdapter(app_token="xapp-...", bot_token="xoxb-...")
bot.add_platform(slack)

# 启动
bot.start()  # 自动监听所有平台
```

### 多平台Bot

```python
# 同一个agent,多个平台!
bot = MessengerBot(agent)

# Slack
bot.add_platform(SlackAdapter(...))

# Discord
bot.add_platform(DiscordAdapter(token="..."))

# WhatsApp
bot.add_platform(WhatsAppAdapter(...))

# Telegram
bot.add_platform(TelegramAdapter(token="..."))

# 启动 - 所有平台同时工作!
bot.start()
```

### 自定义适配器

```python
from pig_messenger import MessagePlatform, UniversalMessage


class MyPlatformAdapter(MessagePlatform):
    """自定义平台适配器"""

    async def send_message(self, channel_id, text):
        # 你的实现
        pass

    async def get_history(self, channel_id, limit):
        # 你的实现
        pass

    def start(self):
        # 启动监听
        pass


# 使用
bot.add_platform(MyPlatformAdapter())
```

---

## 🌟 核心优势

### vs pi-mom

| 特性 | pi-mom | pig-messenger |
|-----|--------|--------------|
| 支持平台 | 仅Slack | **多平台** ✨ |
| 扩展性 | 固定 | **插件化** ✨ |
| 代码复用 | N/A | **高** ✨ |
| 未来proof | 否 | **是** ✨ |

### 优势

1. **一次配置,到处使用**
   - 同一个agent
   - 同一套工具
   - 同一份代码

2. **灵活部署**
   - 单平台部署
   - 多平台同时
   - 按需添加

3. **统一体验**
   - 用户在不同平台体验一致
   - 会话可以跨平台

4. **易扩展**
   - 新平台只需实现接口
   - 不改核心代码
   - 插件式架构

---

## 🔧 技术实现

### Session管理(跨平台)

```python
class MultiPlatformSession:
    """跨平台会话管理"""

    def get_session(self, platform: str, channel_id: str):
        """获取会话"""
        key = f"{platform}:{channel_id}"
        return self.sessions.get(key)

    # 每个平台+channel组合独立会话
    # slack:C123ABC → session1
    # discord:987654321 → session2
```

### 消息路由

```python
async def route_message(self, msg: UniversalMessage):
    """统一的消息路由"""

    # 1. 获取对应会话
    session = self.get_session(msg.platform, msg.channel_id)

    # 2. 运行agent
    response = self.agent.run(msg.text, session=session)

    # 3. 路由回对应平台
    platform = self.platforms[msg.platform]
    await platform.send_message(msg.channel_id, response.content)
```

### 平台适配器接口

```python
class MessagePlatform(ABC):
    """平台适配器必须实现的接口"""

    # 消息
    async def send_message(self, channel_id, text, **kwargs)
    async def edit_message(self, message_id, text)
    async def delete_message(self, message_id)

    # 文件
    async def upload_file(self, channel_id, file_path)
    async def download_file(self, file_id) -> bytes

    # 历史
    async def get_history(self, channel_id, limit)
    async def search_messages(self, query)

    # 用户
    async def get_user_info(self, user_id)

    # 生命周期
    def start()  # 启动监听
    def stop()   # 停止
```

---

## 📋 实现计划

### Phase 1: 核心框架 (2天)
- [ ] MessagePlatform抽象
- [ ] UniversalMessage格式
- [ ] MessengerBot核心
- [ ] Session管理(多平台)
- [ ] 消息路由

### Phase 2: Slack适配器 (1天)
- [ ] SlackAdapter实现
- [ ] Socket Mode集成
- [ ] 文件上传/下载
- [ ] 线程回复

### Phase 3: 更多适配器 (各1天)
- [ ] DiscordAdapter
- [ ] WhatsAppAdapter (via official API)
- [ ] TelegramAdapter
- [ ] FeishuAdapter (飞书)

### Phase 4: 增强功能 (1-2天)
- [ ] 事件系统(定时任务)
- [ ] 跨平台通知
- [ ] 统一配置
- [ ] CLI工具

**总计**: 7-9天 → **5个平台支持**!

---

## 🎯 对比方案

### 方案A: 只做pi-mom (Slack)
- 工作量: 3天
- 功能: +5% (达到98%)
- 价值: 复制pi-mono

### 方案B: pig-messenger (通用框架) ⭐⭐⭐⭐⭐
- 工作量: 7-9天
- 功能: +5% (达到98%)
- 价值: **超越pi-mono!**
- 创新: 多平台支持!

---

## 💡 建议

**我强烈推荐方案B (pig-messenger)!**

原因:
1. **更通用** - 支持多平台
2. **更灵活** - 可扩展
3. **更实用** - 国内外都能用
4. **差异化** - pig-mono的独特优势!

支持平台优先级:
1. **Slack** - 对标pi-mom
2. **Discord** - 开发者社区
3. **Feishu** - 国内企业
4. **Telegram** - 全球用户
5. **WhatsApp** - 日常交流

**主上,要做pig-messenger吗?** 这会让pig-mono**超越pi-mono**! 🚀🫘

还是:
- 现在97%已经足够?
- 只做Slack(py-mom)?
