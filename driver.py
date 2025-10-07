import importlib.util
import importlib.machinery
from func_timeout import func_timeout, FunctionTimedOut
import time
import ast
import astor
import mutate
import copy
import random


# Each test includes the function to call and the two arguments to pass in.
# The correct answer (oracle) is given by what subject.py returns. 
# An exact output match is required to pass the test. 
tests = [   ("f01",5,0) ,
            ("f02",3,4) ,
            ("f03",7,8) ,
            ("f04",1,1) ,
            ("f05",7,8) ,
            ("f06",13,2) ,
            ("f06",2,13) ,
            ("f07",3,4) ,
            ("f07",-1,-2) ,
            ("f08",0,0) ,
            ("f09",3,2) ,
            ("f10",[8,6,7,5,3,0,9],0) ,
         ]

subject_filename = "subject.py" 

# A test is "killed", in the terminology of mutation testing, if the mutant
# fails it (but the original passes it). 

# We desire mutants that are strong enough to kill one test, but not so strong
# that they kill all of the tests. We favor mutants that selectively kill just
# one test. This variable tracks all of the tests that are selectively
# killed by any student-produced mutant.
tests_selectively_killed = set()  

# This procedure runs all of the tests in the global "tests" list
# on a python file. The python file created by the student's "mutate.py".
def run_tests_on_python_file(name_of_python_file):
        global tests_selectively_killed

        # This bit of "systems magic" dynamically loads a given
        # python file (e.g., "03.py") at run-time. 
        def load_module(name_of_python_file):
                module_name = name_of_python_file 
                file_path = './' + name_of_python_file
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module

        mutant = load_module(name_of_python_file)
        original = load_module(subject_filename) 

        tests_killed = {}

        # For each test (function name, arguments, etc.) we run 
        # the mutant version of that function and the original
        # version of that function and compare the outputs. 
        for test in tests:
                (method,x,y) = copy.deepcopy(test)
                test_string = f"{method}({x},{y})"

                # This getattr() "systems magic" allows us to call a method
                # where the name is stored in a variable. 
                mutant_method = getattr(mutant, method)
                original_method = getattr(original, method)

                mutant_result = "impossible" 
                x1 = copy.deepcopy(x) 
                y1 = copy.deepcopy(y) 
                original_result = original_method(x1,y1) 
                try:
                        # This "systems magic" gives the code a timeout
                        # of 1 second. Mutants sometimes loop forever,
                        # so we need this timeout!
                        x2 = copy.deepcopy(x) 
                        y2 = copy.deepcopy(y) 
                        mutant_result = func_timeout(1, mutant_method, args=(x2,y2,))
                except Exception as e:
                        mutant_result = "exceptional_result" 
                except FunctionTimedOut as e:
                        mutant_result = "timed_out" 
                        
                # Debugging print statement, uncomment for tracing:
                # print(f"{method}({x},{y}) = {mutant_result} {original_result}")
                if mutant_result != original_result: 
                        tests_killed[test_string] = True 
                        # Debugging print statement, uncomment for tracing:
                        # print(f"FAILED: {name_of_python_file}: {method}({x},{y})") 

        # We desire mutants that are powerful enough to kill one test,
        # but not so powerful that they kill many tests.
        if len(tests_killed) == 1: 
                # This is a good result for the student!
                print(f"{name_of_python_file} kills exactly one test: {tests_killed}") 
                for test in list(tests_killed.keys()):
                        tests_selectively_killed.add(test)

        elif len(tests_killed) == 0:
            print(f"{name_of_python_file} kills no tests (too weak? inspect with: diff {name_of_python_file} no-mutations.py)")
        else:
            print(f"{name_of_python_file} kills {len(tests_killed)} tests (too strong? inspect with: diff {name_of_python_file} no-mutations.py)")

num_mutants = 10    

with open(subject_filename, 'r') as infile:
        original_code = infile.read()
tree = ast.parse(original_code) 

# To help students, we have the AST library print out
# an unmodified version of the proram as well. This
# makes it easy to use "diff" to see what the mutant changed.
with open("no-mutations.py", 'w') as outfile:
    outfile.write(astor.to_source(tree))

# Step 1. Use your mutate.py to create N mutants. 
print(f"using your mutate.py to create {num_mutants} mutants")
for i in range(num_mutants): 
    try:
        tree_copy = copy.deepcopy(tree) 
        random.seed(i) 
        mutated_tree = mutate.mutate(tree_copy)
        ast.fix_missing_locations(mutated_tree)
        output_file = f"{i}.py"
        with open(output_file, 'w') as outfile:
            outfile.write(astor.to_source(mutated_tree))
    except Exception as e:
        print(f"your mutate.py FAILED to create mutant {i}: {e}") 

# Step 2. Run each of your N mutants on the full test suite.
for i in range(num_mutants):
    try: 
        run_tests_on_python_file(f"{i}.py")
    except Exception as e:
        pass 

# Step 3. Report which tests were selectively killed. 
print("---") 

print(f"Your mutants selectively killed {len(tests_selectively_killed)} of the {len(tests)} tests!") 

for test in sorted(tests_selectively_killed):
        print(f"+ {test}") 
