import ast
import os
from typing import Dict, Any, List

class CodebaseMapmaker:
    def __init__(self, base_dir: str):
        self.base_dir = os.path.abspath(base_dir)
        self.repo_map: Dict[str, Any] = {}

    def get_local_module_path(self, current_file: str, module_name: str) -> str | None:
        """Resolves an import module name to a local file path if it exists."""
        current_dir = os.path.dirname(os.path.abspath(current_file))
        
        possible_paths = [
            os.path.join(current_dir, f"{module_name}.py"),
            os.path.join(self.base_dir, f"{module_name}.py")
        ]
        
        dot_path = os.path.join(self.base_dir, "..", module_name.replace(".", "/") + ".py")
        possible_paths.append(os.path.abspath(dot_path))

        for path in possible_paths:
            if os.path.exists(path) and path.startswith(self.base_dir):
                return path
        return None

    def parse_file(self, file_path: str) -> Dict[str, Any]:
        """Extracts functions and local imports from a single file using AST."""
        rel_path = os.path.relpath(file_path, self.base_dir)
        
        if rel_path in self.repo_map:
            return self.repo_map[rel_path]

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
            tree = ast.parse(source)
        except Exception as e:
            return {"error": f"Failed to parse: {str(e)}"}

        functions: List[str] = []
        local_imports: List[str] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                functions.append(node.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    local_imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                local_imports.append(node.module)

        resolved_local_imports = []
        for imp in local_imports:
            resolved_path = self.get_local_module_path(file_path, imp)
            if resolved_path:
                resolved_rel_path = os.path.relpath(resolved_path, self.base_dir)
                resolved_local_imports.append(resolved_rel_path)

        self.repo_map[rel_path] = {
            "functions": functions,
            "local_imports": list(set(resolved_local_imports))
        }

        for imported_file in resolved_local_imports:
            full_imported_path = os.path.join(self.base_dir, imported_file)
            self.parse_file(full_imported_path)

        return self.repo_map[rel_path]

    def build_map(self, entry_file_rel_path: str) -> Dict[str, Any]:
        """Entry point to map the codebase starting from a specific file."""
        full_entry_path = os.path.abspath(os.path.join(self.base_dir, entry_file_rel_path))
        if not os.path.exists(full_entry_path):
            raise FileNotFoundError(f"Entry file not found: {full_entry_path}")
            
        self.parse_file(full_entry_path)
        return self.repo_map

if __name__ == "__main__":
    target_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../sandbox/mock_target"))
    mapmaker = CodebaseMapmaker(base_dir=target_dir)
    codebase_map = mapmaker.build_map("main.py")
    
    import json
    print(json.dumps(codebase_map, indent=2))
