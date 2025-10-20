"""
Быстрый запуск UI тестов
Удобный wrapper для pytest с логированием
"""

import sys
import subprocess
from pathlib import Path

def run_tests(test_file: str = None, verbose: bool = True, show_logs: bool = True):
    """Запустить UI тесты"""
    
    base_path = Path(__file__).parent
    
    if test_file:
        test_path = base_path / test_file
    else:
        test_path = base_path / "test_master_onboarding.py"
    
    cmd = ["pytest", str(test_path)]
    
    if verbose:
        cmd.append("-v")
    
    if show_logs:
        cmd.append("-s")
    
    print("=" * 60)
    print(f"  Запуск UI тестов: {test_path.name}")
    print("=" * 60)
    print()
    print(f"Команда: {' '.join(cmd)}")
    print()
    
    result = subprocess.run(cmd, cwd=Path(__file__).parent.parent.parent)
    
    return result.returncode


if __name__ == "__main__":
    test_file = sys.argv[1] if len(sys.argv) > 1 else None
    exit_code = run_tests(test_file)
    sys.exit(exit_code)
