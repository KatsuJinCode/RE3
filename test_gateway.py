"""Test gateway subprocess call - run from PowerShell to diagnose."""
import subprocess
import tempfile
import os

home = os.environ.get('HOME', os.environ.get('USERPROFILE', ''))
home = home.replace('\\', '/')
gateway = home + '/.claude/scripts/safe-model-load.sh'

print(f"Gateway path: {gateway}")
print(f"Gateway exists: {os.path.exists(gateway.replace('/', os.sep))}")

# Write prompt to temp file
with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
    f.write('What is 2+2?')
    prompt_file = f.name
prompt_unix = prompt_file.replace('\\', '/')

cmd = f'bash "{gateway}" request text --prompt-file "{prompt_unix}" --temperature 0'
print(f"Command: {cmd}")
print("Running...")

try:
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    print(f"Return code: {result.returncode}")
    print(f"Stdout: {repr(result.stdout[:100]) if result.stdout else '(empty)'}")
    print(f"Stderr: {repr(result.stderr[:200]) if result.stderr else '(empty)'}")
except Exception as e:
    print(f"Exception: {e}")

os.unlink(prompt_file)
