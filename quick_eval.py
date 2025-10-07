# quick_eval.py
import subprocess, re, sys

def run_once():
    out = subprocess.check_output([sys.executable, "driver.py"], text=True)
    single = len(re.findall(r"kills exactly one test", out))
    two_or_more = len(re.findall(r"kills [2-9] tests", out))
    zero  = len(re.findall(r"kills no tests", out))
    killed = set(re.findall(r"\+ (.+)", out))  # distinct tests killed
    return single, two_or_more, zero, killed

singles = multi = zeros = 0
allk = set()
runs = 5  # 5×10 mutants ≈ 50, like the autograder
for _ in range(runs):
    s, m, z, k = run_once()
    singles += s; multi += m; zeros += z; allk |= k

print(f"≈{runs*10} mutants: single={singles}, multi={multi}, zero={zeros}")
print("Distinct tests killed:", ", ".join(sorted(allk)))
