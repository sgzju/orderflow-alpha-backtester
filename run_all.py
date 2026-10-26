"""Full pipeline: download -> features -> research -> sweep -> execution study -> report."""
import subprocess
import sys

STEPS = ["ofalpha.data", "ofalpha.features", "ofalpha.research",
         "ofalpha.sweep --bench", "ofalpha.execution", "ofalpha.report"]

if __name__ == "__main__":
    for step in STEPS:
        print(f"\n=== {step} ===", flush=True)
        subprocess.run([sys.executable, "-m", *step.split()], check=True)
