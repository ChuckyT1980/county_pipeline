import sys
import json
from analysis.query_plane import QueryPlane

def coerce_arg(arg: str):
    if arg.isdigit():
        return int(arg)
    try:
        return float(arg)
    except ValueError:
        return arg

def load_registry():
    import os
    registry_path = os.path.join("analysis", "command_registry.json")
    with open(registry_path, "r") as f:
        return json.load(f)

def resolve_command(registry, domain, action, version_override=None):
    command_key = f"{domain}.{action}"
    if command_key not in registry:
        raise ValueError(f"Unknown command namespace: {command_key}")
        
    versions = registry[command_key]
    
    if version_override:
        if version_override not in versions:
            raise ValueError(f"Version {version_override} not found for command {command_key}")
        target_version = version_override
    else:
        # Find latest stable
        stable_versions = [v for v, meta in versions.items() if meta.get("stable") is True]
        if not stable_versions:
            raise ValueError(f"No stable version found for command {command_key}")
        target_version = sorted(stable_versions, reverse=True)[0] # e.g. v2 over v1
        
    meta = versions[target_version]
    if meta.get("status") == "deprecated":
        # Log to stderr to not corrupt json stdout
        print(f"[WARNING] Command {command_key} {target_version} is deprecated: {meta.get('notes', '')}", file=sys.stderr)
        
    return meta

def main():
    args_list = sys.argv[1:]
    
    if len(args_list) >= 4 and args_list[0] == "compat" and args_list[1] == "compare":
        # query compat compare <command> <v1> <v2>
        from analysis.sct_engine import CompatibilityAnalyzer
        analyzer = CompatibilityAnalyzer()
        try:
            result = analyzer.compare(args_list[2], args_list[3], args_list[4])
            print(json.dumps(result, indent=2))
        except Exception as e:
            print(json.dumps({"error": str(e)}, indent=2))
        sys.exit(0)
        
    version = None
    if len(args_list) >= 2 and args_list[0] == "--version":
        version = args_list[1]
        args_list = args_list[2:]
        
    if len(args_list) < 2:
        print(json.dumps({"error": "Usage: python query.py [--version v1] <domain> <action> [args...]\n   or: python query.py compat compare <command> <v1> <v2>"}), indent=2)
        sys.exit(1)
        
    domain = args_list[0]
    action = args_list[1]
    raw_args = args_list[2:]
    args = [coerce_arg(a) for a in raw_args]
    
    registry = load_registry()
    try:
        cmd_meta = resolve_command(registry, domain, action, version)
    except ValueError as e:
        print(json.dumps({"error": str(e)}), indent=2)
        sys.exit(1)
        
    query = QueryPlane()
    
    # Resolve function: "drift.over_time"
    func_path = cmd_meta["function"].split(".")
    obj = query
    for attr in func_path:
        obj = getattr(obj, attr)
    func = obj
    
    try:
        result = func(*args)
        print(json.dumps(result, indent=2))
    except TypeError as e:
        print(json.dumps({"error": f"Invalid arguments for {domain} {action}: {str(e)}"}, indent=2))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2))
        sys.exit(1)

if __name__ == "__main__":
    main()
