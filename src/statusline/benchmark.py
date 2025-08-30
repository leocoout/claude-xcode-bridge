#!/usr/bin/env python3
"""
Benchmark script to compare old vs new DerivedData path finding methods
"""

import time
import os
import subprocess

def benchmark_old_method(project_path):
    """Old method using xcodebuild -showBuildSettings"""
    start = time.time()
    try:
        # Simulate the old method
        cmd = [
            'xcodebuild',
            '-project', project_path,
            '-scheme', 'ExampleApp',
            '-showBuildSettings',
            '-json'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        elapsed = time.time() - start
        return elapsed, result.returncode == 0
    except Exception as e:
        return time.time() - start, False

def benchmark_new_method(project_path):
    """New method using direct scanning"""
    start = time.time()
    try:
        # Import the new scanning function
        import sys
        sys.path.insert(0, os.path.dirname(__file__))
        from xcode_statusline import scan_derived_data_for_project
        
        result = scan_derived_data_for_project(project_path)
        elapsed = time.time() - start
        return elapsed, result is not None
    except Exception as e:
        return time.time() - start, False

if __name__ == "__main__":
    # Use a known project path
    project_path = "/Users/bytedance/Apple-Music-Lyric-Animation/Apple Music.xcodeproj"
    print(f"Testing with: {project_path}")
    
    # Benchmark old method (simulated)
    old_time, old_success = benchmark_old_method(project_path)
    
    # Benchmark new method
    new_time, new_success = benchmark_new_method(project_path)
    
    print(f"Old method (xcodebuild): {old_time:.2f}s, Success: {old_success}")
    print(f"New method (scanning): {new_time:.2f}s, Success: {new_success}")
    
    if old_time > 0:
        speedup = old_time / new_time if new_time > 0 else float('inf')
        print(f"Speedup: {speedup:.1f}x faster")