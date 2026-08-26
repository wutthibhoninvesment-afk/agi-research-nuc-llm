#!/usr/bin/env python3
"""NucScript (ncs) — Tiny task-script language for NUC agent ops."""
import sys, os, json, time, subprocess, re
from datetime import datetime


class Miss(object):
    """A failed computation result (like WhENCE miss)."""
    __slots__ = ("reasons", "line", "trace")
    
    def __init__(self, reasons, line=0, trace=None):
        self.reasons = tuple(reasons)
        self.line = line
        self.trace = trace or []


class TaskResult(object):
    """Outcome of executing an NCS task."""
    def __init__(self, name, status, output="", error=None, elapsed_s=0):
        self.name = name
        self.status = status
        self.output = output
        self.error = error
        self.elapsed_s = elapsed_s


class NCSEngine:
    """Execute NCS task scripts with telemetry."""
    
    def __init__(self, telemetry_endpoint=None):
        self.start_time = time.time()
        self.results = {}
        self.telemetry_endpoint = telemetry_endpoint
        
    def parse(self, source_text):
        tasks = {}
        chain_order = []
        current_task = None
        
        lines = source_text.split('\n')
        in_chain = False
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if line.startswith('task '):
                match = re.match(r'task\s+"([^"]+)":', line)
                if match:
                    task_name = match.group(1)
                    current_task = {
                        "name": task_name,
                        "command": "",
                        "retries": 3,
                        "budget": 300,
                        "rescue": None,
                        "optional": False,
                        "line": i
                    }
                    tasks[task_name] = current_task
                    
            elif current_task and line.startswith('command:'):
                cmd_match = re.search(r'command:\s*(.+)', line)
                if cmd_match:
                    current_task["command"] = cmd_match.group(1).strip()
                    
            elif current_task and line.startswith('retries:'):
                ret_match = re.search(r'retries:\s*(\d+)', line)
                if ret_match:
                    current_task["retries"] = int(ret_match.group(1))
                    
            elif current_task and line.startswith('budget:'):
                bud_match = re.search(r'budget:\s*(\d+)', line)
                if bud_match:
                    current_task["budget"] = int(bud_match.group(1))
                    
            elif line.startswith('- ') and not line.startswith('--'):
                chain_item = line[2:].strip().rstrip('?')
                optional = '?' in line
                chain_order.append({"name": chain_item, "optional": optional})
                
            i += 1
            
        return {"tasks": tasks, "chain_order": chain_order}
    
    def execute_command(self, task_def):
        cmd = task_def["command"]
        max_retries = task_def["retries"]
        budget = task_def["budget"]
        task_name = task_def["name"]
        
        for attempt in range(max_retries + 1):
            attempt_start = time.time()
            
            elapsed_total = time.time() - self.start_time
            if elapsed_total > budget:
                return TaskResult(task_name, "timed_out", 
                                  error=f"Budget exceeded: {elapsed_total:.2f}s > {budget}s")
            
            try:
                # Parse HTTP commands specially
                http_match = re.match(r'http_(get|post)\s+(\S+)', cmd)
                
                if http_match:
                    method = http_match.group(1).upper()
                    url = http_match.group(2)
                    output = self._execute_http(method, url)
                else:
                    # Shell command
                    proc = subprocess.run(cmd, shell=True, capture_output=True, 
                                          text=True, timeout=budget)
                    output = proc.stdout
                    if proc.returncode != 0:
                        raise RuntimeError(f"Exit code {proc.returncode}: {proc.stderr.strip()}")
                
                return TaskResult(task_name, "success", output=output, 
                                  elapsed_s=time.time() - attempt_start)
                
            except Exception as e:
                error_msg = str(e)
                if attempt == max_retries:
                    return TaskResult(task_name, "failed", 
                                      error=error_msg, elapsed_s=time.time() - attempt_start)
                print(f"  Retry {attempt + 2}/{max_retries + 1}: {error_msg[:100]}")
                time.sleep(1)
                
        return TaskResult(task_name, "failed", error="Max retries exhausted")
    
    def _execute_http(self, method, url):
        import urllib.request
        
        req = urllib.request.Request(url, method=method)
        if method == "POST":
            req.add_header('Content-Type', 'application/json')
            req.data = b'{"model":"qwen36","messages":[{"role":"user","content":"OK"}],"max_tokens":8}'
        
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read().decode())
        return json.dumps(data, indent=2)[:500]
    
    def run(self, source_text):
        ast = self.parse(source_text)
        
        print(f"NCS Engine starting — {len(ast['tasks'])} tasks, {len(ast['chain_order'])} chain links")
        
        for task_info in ast["chain_order"]:
            task_name = task_info["name"]
            optional = task_info.get("optional", False)
            
            if task_name not in ast["tasks"]:
                print(f"Warning: Task '{task_name}' not found, skipping")
                continue
                
            task_def = ast["tasks"][task_name]
            print(f"\n>>> Executing: {task_name}")
            
            result = self.execute_command(task_def)
            self.results[task_name] = result
            
            print(f"    Status: {result.status} | Elapsed: {result.elapsed_s:.2f}s")
            if result.error:
                print(f"    Error: {result.error[:200]}")
                
        return self.results


def main():
    if len(sys.argv) < 2:
        print("Usage: ncs_engine.py <script.ncs>")
        sys.exit(1)
    
    script_path = sys.argv[1]
    with open(script_path, "r") as f:
        source = f.read()
    
    engine = NCSEngine(telemetry_endpoint=None)
    results = engine.run(source)
    
    print("\n=== Execution Summary ===")
    total = len(results)
    successes = sum(1 for r in results.values() if r.status == "success")
    failures = sum(1 for r in results.values() if r.status == "failed")
    timed_outs = sum(1 for r in results.values() if r.status == "timed_out")
    
    print(f"{successes}/{total} succeeded | {failures} failed | {timed_outs} timed out")
    print(f"Total elapsed: {time.time() - engine.start_time:.2f}s")
    
    os._exit(0 if failures == 0 and timed_outs == 0 else 1)


if __name__ == "__main__":
    main()
