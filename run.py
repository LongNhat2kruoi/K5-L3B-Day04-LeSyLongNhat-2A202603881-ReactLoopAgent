import argparse
import json
import os
import sys
from agent import run_agent
from providers import Provider
from status_tools import StatusTools
from bonus.tools import BonusTools


def run(question, mode, provider_name, model, max_steps, fail=False, bonus=False):
    provider = Provider(provider_name, model)
    tools = BonusTools(mode) if bonus else StatusTools(mode, fail=fail)
    return run_agent(question, provider, tools, max_steps=max_steps)


def load_local_env():
    """Load simple KEY=value or PowerShell-style $env:KEY=value entries."""
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, encoding='utf-8') as stream:
            for line in stream:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                name, value = line.split('=', 1)
                name = name.strip().removeprefix('$env:').removeprefix('export ').strip()
                value = value.strip().strip('"').strip("'")
                if name and value and name not in os.environ:
                    os.environ[name] = value
    except OSError:
        pass


def main():
    load_local_env()
    p = argparse.ArgumentParser(description='Chạy status agent')
    p.add_argument('question', help='Câu hỏi cho agent')
    p.add_argument('--bonus', action='store_true', help='Dùng bộ tools bonus')
    p.add_argument('--mode', choices=['snapshot', 'live'], default='snapshot')
    p.add_argument('--provider', choices=['openai', 'gemini', 'anthropic', 'openrouter', 'opencode', 'grok', 'xai'], default=os.getenv('PROVIDER', 'openrouter'))
    p.add_argument('--model', default=os.getenv('MODEL') or os.getenv('API_MODEL'))
    p.add_argument('--max-steps', type=int, default=6)
    args = p.parse_args()
    if args.max_steps < 1:
        p.error('--max-steps phải >= 1')
    try:
        result = run(args.question, args.mode, args.provider, args.model, args.max_steps, bonus=args.bonus)
    except (ValueError, RuntimeError, NotImplementedError) as exc:
        print(f'Lỗi: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'completed' else 1

if __name__ == '__main__':
    sys.exit(main())
