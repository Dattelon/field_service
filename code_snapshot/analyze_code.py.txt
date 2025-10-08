import os
from pathlib import Path

project_root = Path(r"C:\ProjectF\field-service")
py_files = [f for f in project_root.rglob("*.py") if "__pycache__" not in str(f)]

print(f"Python файлов: {len(py_files)}")
print(f"\nТоп-10 самых больших:")
sizes = [(f.stat().st_size, f.relative_to(project_root)) for f in py_files]
for size, path in sorted(sizes, reverse=True)[:10]:
    print(f"  {size:>6} bytes - {path}")
