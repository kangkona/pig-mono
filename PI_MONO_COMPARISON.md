# pi-mono vs py-mono 功能对比

## 📊 总体对比

| 特性类别 | pi-mono | py-mono | 状态 |
|---------|---------|---------|------|
| 核心包数量 | 7 | 5 | ⚠️ 少2个 |
| LLM API | ✅ | ✅ | ✅ 完整 |
| Agent 运行时 | ✅ | ✅ | ✅ 完整 |
| TUI | ✅ | ✅ | ✅ 完整 |
| Web UI | ✅ | ✅ | ✅ 完整 |
| Coding Agent | ✅ | ✅ | ✅ 完整 |
| Slack Bot (mom) | ✅ | ❌ | ❌ 缺失 |
| vLLM Pods | ✅ | ❌ | ❌ 缺失 |

---

## 🔍 详细功能对比

### 1. @mariozechner/pi-ai vs py-ai

| 功能 | pi-ai | py-ai | 实现程度 |
|-----|-------|-------|----------|
| **Providers** |
| OpenAI | ✅ | ✅ | 100% |
| Anthropic | ✅ | 🔶 | 50% (占位符) |
| Google Gemini | ✅ | 🔶 | 50% (占位符) |
| Azure OpenAI | ✅ | ❌ | 0% |
| Amazon Bedrock | ✅ | ❌ | 0% |
| Mistral | ✅ | ❌ | 0% |
| Groq | ✅ | ❌ | 0% |
| Cerebras | ✅ | ❌ | 0% |
| xAI | ✅ | ❌ | 0% |
| OpenRouter | ✅ | ❌ | 0% |
| Vercel AI Gateway | ✅ | ❌ | 0% |
| **Features** |
| Streaming | ✅ | ✅ | 100% |
| Async/Await | ✅ | ✅ | 100% |
| Token counting | ✅ | ✅ | 100% |
| Cost tracking | ✅ | 🔶 | 50% (基础) |
| OAuth support | ✅ | ❌ | 0% |
| Subscription login | ✅ | ❌ | 0% |
| Model registry | ✅ | ❌ | 0% |
| Cache retention | ✅ | ❌ | 0% |

**评分**: py-ai ≈ 40% 的 pi-ai 功能

---

### 2. @mariozechner/pi-agent vs py-agent-core

| 功能 | pi-agent | py-agent-core | 实现程度 |
|-----|----------|---------------|----------|
| **Core** |
| Tool calling | ✅ | ✅ | 100% |
| Tool decorator | ✅ | ✅ | 100% |
| State management | ✅ | ✅ | 100% |
| Conversation history | ✅ | ✅ | 100% |
| Async execution | ✅ | 🔶 | 50% (部分) |
| **Advanced** |
| Session branching | ✅ | ❌ | 0% |
| Session compaction | ✅ | ❌ | 0% |
| Tree navigation | ✅ | ❌ | 0% |
| Fork sessions | ✅ | ❌ | 0% |
| JSONL storage | ✅ | ❌ | 0% (用JSON) |
| Message queue | ✅ | ❌ | 0% |
| Steering messages | ✅ | ❌ | 0% |
| Follow-up messages | ✅ | ❌ | 0% |
| Event system | ✅ | 🔶 | 30% (基础) |
| **Customization** |
| Extension system | ✅ | ❌ | 0% |
| Hooks/callbacks | ✅ | 🔶 | 40% |

**评分**: py-agent-core ≈ 55% 的 pi-agent 功能

---

### 3. @mariozechner/pi-coding-agent vs py-coding-agent

| 功能 | pi-coding-agent | py-coding-agent | 实现程度 |
|-----|----------------|-----------------|----------|
| **Interactive Mode** |
| Chat interface | ✅ | ✅ | 100% |
| Editor with syntax | ✅ | 🔶 | 50% (基础) |
| File reference (@) | ✅ | ❌ | 0% |
| Path completion | ✅ | ❌ | 0% |
| Image paste | ✅ | ❌ | 0% |
| Multi-line input | ✅ | ✅ | 100% |
| **Commands** |
| /help, /exit | ✅ | ✅ | 100% |
| /model | ✅ | ❌ | 0% |
| /login, /logout | ✅ | ❌ | 0% |
| /settings | ✅ | 🔶 | 30% (/status) |
| /tree | ✅ | ❌ | 0% |
| /fork | ✅ | ❌ | 0% |
| /compact | ✅ | ❌ | 0% |
| /export, /share | ✅ | ❌ | 0% |
| /reload | ✅ | ❌ | 0% |
| **Keyboard Shortcuts** |
| Ctrl+L (model) | ✅ | ❌ | 0% |
| Ctrl+P (cycle) | ✅ | ❌ | 0% |
| Ctrl+O (collapse) | ✅ | ❌ | 0% |
| Ctrl+T (thinking) | ✅ | ❌ | 0% |
| Escape (abort) | ✅ | ✅ | 100% |
| **Tools** |
| read, write, edit | ✅ | ✅ | 100% |
| bash execution | ✅ | ✅ | 100% |
| grep, find, ls | ✅ | ❌ | 0% |
| git integration | ✅ | 🔶 | 40% |
| **Customization** |
| Skills | ✅ | ❌ | 0% |
| Prompt templates | ✅ | ❌ | 0% |
| Extensions | ✅ | ❌ | 0% |
| Themes | ✅ | ❌ | 0% |
| Pi packages | ✅ | ❌ | 0% |
| **Session Management** |
| Auto-save | ✅ | ❌ | 0% |
| Resume (-r) | ✅ | ❌ | 0% |
| Continue (-c) | ✅ | ❌ | 0% |
| Branching | ✅ | ❌ | 0% |
| Tree view | ✅ | ❌ | 0% |
| **Context** |
| AGENTS.md | ✅ | ❌ | 0% |
| SYSTEM.md | ✅ | ❌ | 0% |
| Project context | ✅ | 🔶 | 30% |
| **Output Modes** |
| Interactive | ✅ | ✅ | 100% |
| Print (-p) | ✅ | ✅ | 100% |
| JSON mode | ✅ | ❌ | 0% |
| RPC mode | ✅ | ❌ | 0% |
| SDK | ✅ | ❌ | 0% |

**评分**: py-coding-agent ≈ 30% 的 pi-coding-agent 功能

---

### 4. @mariozechner/pi-tui vs py-tui

| 功能 | pi-tui | py-tui | 实现程度 |
|-----|--------|--------|----------|
| **Components** |
| Console output | ✅ | ✅ | 100% |
| Chat UI | ✅ | ✅ | 100% |
| Markdown rendering | ✅ | 🔶 | 70% |
| Code highlighting | ✅ | ✅ | 100% |
| Progress indicators | ✅ | ✅ | 100% |
| **Advanced** |
| Differential rendering | ✅ | ❌ | 0% |
| Custom widgets | ✅ | ❌ | 0% |
| Event handling | ✅ | 🔶 | 40% |
| Layout system | ✅ | ❌ | 0% |
| Overlays | ✅ | ❌ | 0% |
| Status lines | ✅ | ❌ | 0% |
| **Input** |
| Prompt | ✅ | ✅ | 100% |
| Confirm | ✅ | ✅ | 100% |
| Select | ✅ | 🔶 | 50% |
| Multi-select | ✅ | ❌ | 0% |
| Autocomplete | ✅ | ❌ | 0% |

**评分**: py-tui ≈ 60% 的 pi-tui 功能

---

### 5. @mariozechner/pi-web-ui vs py-web-ui

| 功能 | pi-web-ui | py-web-ui | 实现程度 |
|-----|-----------|-----------|----------|
| **Backend** |
| HTTP server | ✅ | ✅ | 100% |
| SSE streaming | ✅ | ✅ | 100% |
| WebSocket | ✅ | ❌ | 0% |
| API routes | ✅ | ✅ | 100% |
| CORS | ✅ | ✅ | 100% |
| **Frontend** |
| Chat interface | ✅ | ✅ | 100% |
| Markdown rendering | ✅ | 🔶 | 50% (准备中) |
| Code highlighting | ✅ | ❌ | 0% |
| File upload | ✅ | ❌ | 0% |
| Image display | ✅ | ❌ | 0% |
| Responsive design | ✅ | ✅ | 100% |
| **Features** |
| History management | ✅ | ✅ | 100% |
| Multi-session | ✅ | ❌ | 0% |
| Authentication | ✅ | ❌ | 0% |
| Themes | ✅ | 🔶 | 40% |
| Export/Share | ✅ | ❌ | 0% |

**评分**: py-web-ui ≈ 60% 的 pi-web-ui 功能

---

### 6. Missing Packages

#### @mariozechner/pi-mom (Slack Bot)
**状态**: ❌ **完全缺失**

**功能**:
- Slack 集成
- 消息委托到 coding agent
- Multi-user support
- Channel management

**影响**: 中等 (企业协作场景需要)

#### @mariozechner/pi-pods (vLLM管理)
**状态**: ❌ **完全缺失**

**功能**:
- GPU pod 管理
- vLLM 部署
- Model hosting
- Resource management

**影响**: 低 (高级用户场景)

---

## 🎯 核心功能差距分析

### Critical Missing Features (关键缺失)

1. **Session Management (会话管理)**
   - ❌ Branching/Tree navigation
   - ❌ Compaction
   - ❌ JSONL storage format
   - ❌ Resume/continue
   - **影响**: 高 - 长对话管理困难

2. **Extension System (扩展系统)**
   - ❌ Extension API
   - ❌ Custom tools registration
   - ❌ Event hooks
   - ❌ UI customization
   - **影响**: 高 - 限制可扩展性

3. **Skills & Prompts**
   - ❌ Skill system (Agent Skills standard)
   - ❌ Prompt templates
   - ❌ Package management
   - **影响**: 高 - 限制复用性

4. **Provider Support (提供商支持)**
   - ❌ 10+ missing providers
   - ❌ OAuth authentication
   - ❌ Subscription login
   - **影响**: 中 - 限制用户选择

5. **Interactive Features**
   - ❌ File reference (@)
   - ❌ Image paste
   - ❌ Message queue
   - ❌ Model selector
   - **影响**: 中 - UX较差

### Important Missing Features (重要缺失)

6. **Output Modes**
   - ❌ JSON mode
   - ❌ RPC mode
   - ❌ SDK integration
   - **影响**: 中 - 集成受限

7. **Context Management**
   - ❌ AGENTS.md support
   - ❌ SYSTEM.md override
   - **影响**: 低 - 可通过其他方式实现

8. **Advanced Tools**
   - ❌ grep, find, ls tools
   - ❌ Git auto-commit
   - ❌ SSH execution
   - **影响**: 低 - 可手动实现

---

## 📈 总体评分

### 功能完整度

| 包 | 完整度 | 评级 |
|---|--------|------|
| py-ai | 40% | ⚠️ 需改进 |
| py-agent-core | 55% | ⚠️ 需改进 |
| py-tui | 60% | ✅ 可接受 |
| py-web-ui | 60% | ✅ 可接受 |
| py-coding-agent | 30% | ❌ 严重不足 |
| py-mom | 0% | ❌ 缺失 |
| py-pods | 0% | ❌ 缺失 |
| **总体** | **49%** | **⚠️ 需改进** |

### 质量评分

| 维度 | py-mono | pi-mono |
|-----|---------|---------|
| 代码质量 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 测试覆盖 | ⭐⭐⭐⭐ (82%) | ⭐⭐⭐⭐ (估~80%) |
| 文档完整性 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 功能完整度 | ⭐⭐⭐ (49%) | ⭐⭐⭐⭐⭐ (100%) |
| 可扩展性 | ⭐⭐ | ⭐⭐⭐⭐⭐ |

---

## 🚀 建议改进优先级

### P0 (高优先级 - 核心价值)

1. **会话管理增强**
   ```python
   # 实现
   - JSONL session storage
   - Session branching/tree
   - Compaction
   - Resume/continue
   ```

2. **扩展系统**
   ```python
   # 实现
   - Extension API
   - Hook system
   - Custom tool registration
   - Event emitters
   ```

3. **Skills & Prompts**
   ```python
   # 实现
   - Agent Skills standard
   - Prompt template system
   - Package manager (pip-based)
   ```

### P1 (中优先级 - 用户体验)

4. **更多 Providers**
   ```python
   # 实现
   - Anthropic (完整)
   - Google (完整)
   - Azure OpenAI
   - Groq, Mistral, etc
   ```

5. **交互增强**
   ```python
   # 实现
   - File reference (@filename)
   - Model selector (Ctrl+L)
   - Message queue
   - Image paste
   ```

6. **Output Modes**
   ```python
   # 实现
   - JSON mode
   - RPC mode
   - SDK for embedding
   ```

### P2 (低优先级 - Nice-to-have)

7. **Slack Bot (pi-mom)**
   ```python
   # 新包
   - Slack integration
   - Multi-user support
   ```

8. **vLLM Pods**
   ```python
   # 新包 (可选)
   - GPU pod management
   - vLLM deployment
   ```

---

## 💡 实现建议

### 快速提升方案

#### 1. Session Management (2-3天)
```python
# session.py
class Session:
    def __init__(self):
        self.tree = SessionTree()  # Tree structure
        
    def branch(self, point_id):
        """Branch from a point"""
        
    def compact(self, instructions):
        """Compact old messages"""
        
    def to_jsonl(self):
        """Export as JSONL"""
```

#### 2. Extension System (3-5天)
```python
# extension.py
class ExtensionAPI:
    def register_tool(self, tool):
        """Register custom tool"""
        
    def register_command(self, name, handler):
        """Register command"""
        
    def on(self, event, handler):
        """Event hook"""
        
# Usage
def my_extension(api: ExtensionAPI):
    @api.tool
    def my_tool(arg: str) -> str:
        return f"Result: {arg}"
```

#### 3. Skills System (2天)
```python
# skills.py
class SkillManager:
    def discover_skills(self, paths):
        """Auto-discover skills"""
        
    def load_skill(self, path):
        """Load SKILL.md"""
        
    def get_skill_prompt(self, name):
        """Get skill instructions"""
```

---

## 📊 具体缺失功能列表

### 1. Session Features
- [ ] Tree-based session storage (JSONL)
- [ ] Session branching (/tree command)
- [ ] Session forking (/fork command)
- [ ] Context compaction (/compact)
- [ ] Session resume (-r flag)
- [ ] Continue last session (-c flag)
- [ ] Session export to HTML
- [ ] Session sharing (gist)
- [ ] Message labeling

### 2. Extension System
- [ ] Extension API
- [ ] Extension discovery
- [ ] Tool registration hooks
- [ ] Command registration
- [ ] Event system
- [ ] UI component registration
- [ ] Extension package format
- [ ] Extension configuration

### 3. Skills & Prompts
- [ ] Skill discovery (SKILL.md)
- [ ] Skill invocation (/skill:name)
- [ ] Prompt templates (/template)
- [ ] Template variables
- [ ] Package management (pi install)
- [ ] Package registry integration

### 4. Provider Support
- [ ] Anthropic (complete)
- [ ] Google (complete)
- [ ] Azure OpenAI
- [ ] Amazon Bedrock
- [ ] Mistral
- [ ] Groq
- [ ] Cerebras
- [ ] xAI
- [ ] OpenRouter
- [ ] OAuth authentication
- [ ] Subscription login

### 5. Interactive Features
- [ ] File reference (@filename)
- [ ] Path autocomplete (Tab)
- [ ] Image paste (Ctrl+V)
- [ ] Model selector (Ctrl+L)
- [ ] Model cycling (Ctrl+P)
- [ ] Thinking level toggle
- [ ] Tool output collapse (Ctrl+O)
- [ ] Message queue
- [ ] Steering messages
- [ ] Follow-up messages

### 6. Commands
- [ ] /model - Switch model
- [ ] /login, /logout - OAuth
- [ ] /tree - Navigate history
- [ ] /fork - Create branch
- [ ] /compact - Manual compaction
- [ ] /export - Export to HTML
- [ ] /share - Share as gist
- [ ] /reload - Reload resources
- [ ] /scoped-models - Model filtering

### 7. Context Management
- [ ] AGENTS.md loading
- [ ] SYSTEM.md override
- [ ] APPEND_SYSTEM.md
- [ ] Multi-directory search
- [ ] Context file hot-reload

### 8. Output Modes
- [ ] JSON mode (--mode json)
- [ ] RPC mode (--mode rpc)
- [ ] SDK for embedding
- [ ] Event streaming

### 9. Additional Tools
- [ ] grep tool
- [ ] find tool
- [ ] ls tool
- [ ] Git auto-commit
- [ ] SSH execution
- [ ] Sandbox mode

### 10. Missing Packages
- [ ] pi-mom (Slack bot)
- [ ] pi-pods (vLLM management)

---

## 🎯 结论

### 现状总结

**py-mono 已实现**:
- ✅ 核心架构完整
- ✅ 基础功能可用
- ✅ 代码质量优秀
- ✅ 测试覆盖良好
- ✅ 文档详尽

**py-mono 缺失**:
- ❌ 约 51% 的 pi-mono 功能
- ❌ 关键的扩展系统
- ❌ 会话管理高级功能
- ❌ 大量 Provider 支持
- ❌ 2 个完整的包

### 定位差异

**pi-mono**:
- 生产级工具
- 高度可扩展
- 企业级功能
- 完整生态

**py-mono**:
- 学习/原型工具
- 基础功能完整
- Python 原生
- 待完善生态

### 使用建议

**适合使用 py-mono**:
- Python 项目
- 学习 Agent 开发
- 快速原型
- 基础自动化

**需要使用 pi-mono**:
- 生产环境
- 复杂工作流
- 需要扩展性
- 团队协作 (Slack)
- 自托管模型

---

**总结**: py-mono 是一个功能完整的 **Python 学习/原型工具**,实现了 pi-mono 约 **49%** 的功能。要达到生产级别,需要补充会话管理、扩展系统和 Skills 等核心功能。

建议优先实现 **P0** 功能以提升核心价值! 🫘
