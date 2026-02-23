"""Output modes demonstration."""

import json
import subprocess


def demo_json_mode():
    """Demonstrate JSON mode."""
    
    print("=" * 60)
    print("JSON Output Mode Demo")
    print("=" * 60)
    print()
    
    print("JSON mode outputs structured events as JSON lines:")
    print()
    
    print("Example output:")
    print('{"type": "message", "role": "user", "content": "Hello", "timestamp": "..."}')
    print('{"type": "message", "role": "assistant", "content": "Hi", "timestamp": "..."}')
    print('{"type": "tool_call_start", "tool": "read_file", "args": {...}}')
    print('{"type": "tool_call_end", "tool": "read_file", "result": "..."}')
    print('{"type": "done"}')
    print()
    
    print("Usage:")
    print("  # Pipe input")
    print('  echo \'{"message": "Hello"}\' | py-code --mode json')
    print()
    print("  # Process output")
    print("  py-code --mode json | jq '.type'")
    print()
    print("  # Integration")
    print("  py-code --mode json < requests.jsonl > responses.jsonl")
    print()


def demo_rpc_mode():
    """Demonstrate RPC mode."""
    
    print("=" * 60)
    print("RPC Mode Demo")
    print("=" * 60)
    print()
    
    print("RPC mode provides stdin/stdout JSON-RPC protocol:")
    print()
    
    print("Request format:")
    print('{"id": 1, "method": "complete", "params": {"message": "Hello"}}')
    print()
    
    print("Response format:")
    print('{"id": 1, "result": {"content": "Hi there!"}, "error": null}')
    print()
    
    print("Supported methods:")
    print("  • complete - Get completion")
    print("  • stream - Stream response (sends token events)")
    print("  • ping - Health check")
    print("  • status - Agent status")
    print()
    
    print("Usage:")
    print("  # Start RPC server")
    print("  py-code --mode rpc")
    print()
    print("  # Send request")
    print('  echo \'{"id":1,"method":"complete","params":{"message":"Hi"}}\' | py-code --mode rpc')
    print()
    
    print("Example integration (Python):")
    print("""
import json
import subprocess

# Start RPC process
proc = subprocess.Popen(
    ['py-code', '--mode', 'rpc'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    text=True
)

# Send request
request = {
    "id": 1,
    "method": "complete",
    "params": {"message": "What is 2+2?"}
}

proc.stdin.write(json.dumps(request) + "\\n")
proc.stdin.flush()

# Read response
response = json.loads(proc.stdout.readline())
print(response['result']['content'])
    """)


def demo_integration():
    """Demonstrate practical integration."""
    
    print("=" * 60)
    print("Integration Examples")
    print("=" * 60)
    print()
    
    print("1. Batch Processing (JSON mode):")
    print("""
# requests.jsonl
{"message": "Explain Python"}
{"message": "Explain JavaScript"}
{"message": "Explain Rust"}

# Process
cat requests.jsonl | py-code --mode json | grep '"type":"message"' > results.jsonl
    """)
    
    print("\n2. CI/CD Integration (RPC mode):")
    print("""
# In your CI script
echo '{"id":1,"method":"complete","params":{"message":"Review this code"}}' \\
  | py-code --mode rpc \\
  | jq -r '.result.content'
    """)
    
    print("\n3. Programmatic Usage (Python):")
    print("""
import subprocess
import json

def ask_agent(question):
    proc = subprocess.run(
        ['py-code', '--mode', 'json'],
        input=json.dumps({"message": question}),
        capture_output=True,
        text=True
    )
    
    for line in proc.stdout.strip().split('\\n'):
        event = json.loads(line)
        if event['type'] == 'message' and event['role'] == 'assistant':
            return event['content']

answer = ask_agent("What is FastAPI?")
print(answer)
    """)


def main():
    """Run all demos."""
    demo_json_mode()
    print()
    demo_rpc_mode()
    print()
    demo_integration()
    
    print()
    print("=" * 60)
    print("Try it yourself:")
    print("  py-code --mode json")
    print("  py-code --mode rpc")
    print("=" * 60)


if __name__ == "__main__":
    main()
