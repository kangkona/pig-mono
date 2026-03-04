# Upgrade Guide: v0.0.3 → v0.0.4

This guide helps you upgrade pig-coding-agent from v0.0.3 to v0.0.4.

## Summary

v0.0.4 adds **resilience** and **cost tracking** features while maintaining full backward compatibility.

## Backward Compatibility

✅ **No breaking changes** - v0.0.4 is fully backward compatible with v0.0.3

- All existing code continues to work
- New features are opt-in (enabled by default but can be disabled)
- No API changes to existing functionality

## Installation

```bash
pip install --upgrade pig-coding-agent
```

Or with uv:

```bash
uv pip install --upgrade pig-coding-agent
```

## New Features

### 1. Resilience (API Key Rotation)

**What it does**: Automatically rotates between multiple API keys when rate limits are hit.

**Setup** (optional but recommended):

```bash
# Add multiple API keys
export OPENAI_API_KEY=sk-...
export OPENAI_API_KEY_2=sk-...
export OPENAI_API_KEY_3=sk-...

# Or for Anthropic
export ANTHROPIC_API_KEY=sk-ant-...
export ANTHROPIC_API_KEY_2=sk-ant-...
```

**Usage**:

```bash
# Resilience is enabled by default
pig-code

# Check status
> /resilience

# Disable if needed
pig-code --no-resilience
```

**Benefits**:
- No more rate limit errors during long sessions
- Automatic failover to backup keys
- Smart cooldown management per failure type

### 2. Cost Tracking

**What it does**: Tracks LLM and tool usage costs automatically.

**Setup**: No setup required - works out of the box!

**Usage**:

```bash
pig-code

# View cost summary
> /cost

# Or
> /usage
```

**Data location**: `.agents/usage.json` in your workspace

**Disable if needed**:

```bash
pig-code --no-cost-tracking
```

**Benefits**:
- Know exactly how much you're spending
- Track usage by model and tool
- Identify cost optimization opportunities

## Configuration

### Update Config File

If you have `.agents/config.json`, you can add:

```json
{
  "enable_resilience": true,
  "enable_cost_tracking": true
}
```

### CLI Flags

New flags available:

```bash
--no-resilience        # Disable API key rotation
--no-cost-tracking     # Disable cost tracking
```

## Migration Checklist

- [ ] Upgrade package: `pip install --upgrade pig-coding-agent`
- [ ] (Optional) Add multiple API keys for resilience
- [ ] Test existing workflows - should work unchanged
- [ ] Try new `/resilience` command
- [ ] Try new `/cost` command
- [ ] Review `.agents/usage.json` for cost insights

## Troubleshooting

### "No API keys found for resilience"

This is normal if you only have one API key. Resilience will be disabled automatically.

To enable:
1. Get additional API keys from your provider
2. Set them as `PROVIDER_API_KEY_2`, `PROVIDER_API_KEY_3`, etc.
3. Restart agent

### "Cost tracking not working"

Check that `.agents/` directory is writable:

```bash
mkdir -p .agents
chmod 755 .agents
```

### "Tests failing"

If you're developing:

```bash
# Ensure pig-agent-core v0.0.4 is installed
pip install pig-agent-core>=0.0.4

# Run tests
pytest tests/
```

## What's Next

After upgrading, you can:

1. **Monitor costs**: Use `/cost` regularly to track spending
2. **Add backup keys**: Set up multiple API keys for resilience
3. **Optimize usage**: Review cost summary to identify expensive operations

## Rollback

If you need to rollback:

```bash
pip install pig-coding-agent==0.0.3
```

Note: Cost tracking data in `.agents/usage.json` will be preserved.

## Questions?

- Check the [README](README.md) for detailed documentation
- See [CHANGELOG](CHANGELOG.md) for all changes
- Report issues on GitHub
