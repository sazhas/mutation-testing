# Returns a mutated AST for driver.py to write out.
# Implements: comparison negation, binop swaps (+<->-, *<->//), safe deletion (stmt->Pass).
# Extras for selectivity: AugAssign swaps, boolean flip in If/While tests, min<->max call swap.
import ast
import random

# ----- Operator maps -----
CMP_NEGATION = {
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Lt: ast.GtE,
    ast.LtE: ast.Gt,
    ast.Gt: ast.LtE,
    ast.GtE: ast.Lt,
}

# Core spec swaps (+<->-, *<->//)
BIN_SWAP = {
    ast.Add: ast.Sub,        # + -> -
    ast.Sub: ast.Add,        # - -> +
    ast.Mult: ast.FloorDiv,  # * -> //
    ast.FloorDiv: ast.Mult,  # // -> *
}

# Optional call-level swap (generic but helpful)
CALL_SWAP = {"min": "max", "max": "min"}

# ----- Utilities -----
def names_defined_by_assign_stmt(node):
    names = set()
    def collect_targets(t):
        if isinstance(t, ast.Name) and isinstance(t.ctx, ast.Store):
            names.add(t.id)
        elif isinstance(t, (ast.Tuple, ast.List)):
            for elt in t.elts:
                collect_targets(elt)
    if isinstance(node, ast.Assign):
        for tgt in node.targets:
            collect_targets(tgt)
    elif isinstance(node, ast.AnnAssign):
        collect_targets(node.target)
    elif isinstance(node, ast.AugAssign):
        collect_targets(node.target)
    return names


class CandidateCounter(ast.NodeVisitor):
    """
    Pass 1: collect eligible mutation sites, record first-def names,
    and track parents to avoid over-strong loop-comparison negations.
    """
    def __init__(self):
        # Sites (in visitation order)
        self.cmp_sites = []        # list[(Compare node, op_index)]
        self._cmp_keys = set()     # {(id(node), op_index)} to align indices in mutator
        self.bin_sites = []        # list[("binop", BinOp) or ("aug", AugAssign)]
        self.del_sites = []        # list[stmt nodes: Assign/AnnAssign/AugAssign/Expr(Call)]
        self.bool_sites = []       # list[("if", If) or ("while", While)] where test is True/False Constant
        self.call_sites = []       # list[Call] where callee is Name 'min' or 'max'

        self._parents = {}         # child -> parent
        self.first_def_names = set()
        self._seen_any_def = set()

    # parent tracking
    def generic_visit(self, node):
        for child in ast.iter_child_nodes(node):
            self._parents[child] = node
        super().generic_visit(node)

    def _is_under_loop(self, node):
        p = self._parents.get(node)
        while p:
            if isinstance(p, (ast.For, ast.While)):
                return True
            p = self._parents.get(p)
        return False

    # ---- sites ----
    def visit_Compare(self, node: ast.Compare):
        # Skip comparisons inside loops (heuristic to reduce over-strong mutants)
        if not self._is_under_loop(node):
            for i, op in enumerate(node.ops):
                if type(op) in CMP_NEGATION:
                    self.cmp_sites.append((node, i))
                    self._cmp_keys.add((id(node), i))
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp):
        if type(node.op) in BIN_SWAP:
            self.bin_sites.append(("binop", node))
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign):
        # aug-assign operator swap candidates (e.g., +=, -=, *=, //=)
        if type(node.op) in BIN_SWAP:
            self.bin_sites.append(("aug", node))
        # also deletable as a statement
        self._maybe_record_first_defs(node)
        self.del_sites.append(node)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
        self._maybe_record_first_defs(node)
        self.del_sites.append(node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign):
        self._maybe_record_first_defs(node)
        self.del_sites.append(node)
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr):
        if isinstance(node.value, ast.Call):
            self.del_sites.append(node)
        self.generic_visit(node)

    def visit_If(self, node: ast.If):
        # boolean flip candidate only if test is literal True/False
        if isinstance(node.test, ast.Constant) and isinstance(node.test.value, bool):
            self.bool_sites.append(("if", node))
        self.generic_visit(node)

    def visit_While(self, node: ast.While):
        if isinstance(node.test, ast.Constant) and isinstance(node.test.value, bool):
            self.bool_sites.append(("while", node))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # min <-> max swap
        f = node.func
        if isinstance(f, ast.Name) and f.id in CALL_SWAP:
            self.call_sites.append(node)
        self.generic_visit(node)

    def _maybe_record_first_defs(self, node):
        for name in names_defined_by_assign_stmt(node):
            if name not in self._seen_any_def:
                self._seen_any_def.add(name)
                self.first_def_names.add(name)


class Mutator(ast.NodeTransformer):
    """
    Pass 2: apply exactly the planned edits. We keep running indices
    in the same visitation order as CandidateCounter for each category.
    """
    def __init__(self, plan, first_def_names, cmp_keys):
        super().__init__()
        self.plan = {k: set(v) for k, v in plan.items()}
        self.first_def_names = set(first_def_names)
        self.cmp_keys = set(cmp_keys)

        self.seen_cmp = 0
        self.seen_bin = 0   # counts both BinOp and AugAssign eligible sites
        self.seen_del = 0
        self.seen_bool = 0
        self.seen_call = 0

    # ---- Compare ----
    def visit_Compare(self, node: ast.Compare):
        super().generic_visit(node)
        for i, op in enumerate(list(node.ops)):
            if type(op) in CMP_NEGATION:
                eligible = (id(node), i) in self.cmp_keys
                if eligible:
                    if "cmp" in self.plan and self.seen_cmp in self.plan["cmp"]:
                        new_op = CMP_NEGATION[type(op)]()
                        node.ops[i] = ast.copy_location(new_op, op)
                    self.seen_cmp += 1
        return node

    # ---- BinOp ----
    def visit_BinOp(self, node: ast.BinOp):
        super().generic_visit(node)
        if type(node.op) in BIN_SWAP:
            if "bin" in self.plan and self.seen_bin in self.plan["bin"]:
                node.op = BIN_SWAP[type(node.op)]()
            self.seen_bin += 1
        return node

    # ---- AugAssign treated as a bin-like site for swaps OR deletable stmt ----
    def visit_AugAssign(self, node: ast.AugAssign):
        super().generic_visit(node)
        changed = False
        if type(node.op) in BIN_SWAP:
            if "bin" in self.plan and self.seen_bin in self.plan["bin"]:
                node.op = BIN_SWAP[type(node.op)]()
                changed = True
            self.seen_bin += 1
        # deletion path (only if not already changed by bin plan)
        if not changed:
            return self._maybe_delete_stmt(node)
        return node

    # ---- Deletion (safe): replace selected stmt with Pass() ----
    def _maybe_delete_stmt(self, node):
        selected = "del" in self.plan and self.seen_del in self.plan["del"]
        self.seen_del += 1
        if not selected:
            return node
        if any(name in self.first_def_names for name in names_defined_by_assign_stmt(node)):
            return node
        return ast.copy_location(ast.Pass(), node)

    def visit_Assign(self, node: ast.Assign):
        super().generic_visit(node)
        return self._maybe_delete_stmt(node)

    def visit_AnnAssign(self, node: ast.AnnAssign):
        super().generic_visit(node)
        return self._maybe_delete_stmt(node)

    def visit_Expr(self, node: ast.Expr):
        super().generic_visit(node)
        if isinstance(node.value, ast.Call):
            return self._maybe_delete_stmt(node)
        return node

    # ---- Boolean flip on literal tests in If/While ----
    def visit_If(self, node: ast.If):
        super().generic_visit(node)
        if isinstance(node.test, ast.Constant) and isinstance(node.test.value, bool):
            if "bool" in self.plan and self.seen_bool in self.plan["bool"]:
                node.test = ast.copy_location(ast.Constant(value=not node.test.value), node.test)
            self.seen_bool += 1
        return node

    def visit_While(self, node: ast.While):
        super().generic_visit(node)
        if isinstance(node.test, ast.Constant) and isinstance(node.test.value, bool):
            if "bool" in self.plan and self.seen_bool in self.plan["bool"]:
                node.test = ast.copy_location(ast.Constant(value=not node.test.value), node.test)
            self.seen_bool += 1
        return node

    # ---- Call swap: min <-> max ----
    def visit_Call(self, node: ast.Call):
        super().generic_visit(node)
        f = node.func
        if isinstance(f, ast.Name) and f.id in CALL_SWAP:
            if "call" in self.plan and self.seen_call in self.plan["call"]:
                f.id = CALL_SWAP[f.id]
            self.seen_call += 1
        return node


def _choose_plan(counter: CandidateCounter) -> dict:
    """
    Decide what to mutate this run.
    Budget: exactly 1 mutation per mutant (selective-friendly).
    Weighted choice among available categories.
    """
    avail = {
        "cmp": len(counter.cmp_sites),
        "bin": len(counter.bin_sites),     # includes BinOp + AugAssign
        "del": len(counter.del_sites),
        "bool": len(counter.bool_sites),   # If/While literal test flips
        "call": len(counter.call_sites),   # min<->max swaps
    }

    # keep comparisons & binops dominant; extras are gentle spice
    base_weights = {
        "cmp":  0.44,
        "bin":  0.44,
        "del":  0.04,
        "bool": 0.04,
        "call": 0.04,
    }

    kinds = [k for k, n in avail.items() if n > 0]
    if not kinds:
        return {}

    weights = [base_weights[k] for k in kinds]
    s = sum(weights)
    weights = [w / s for w in weights] if s > 0 else [1 / len(kinds)] * len(kinds)

    chosen_kind = random.choices(kinds, weights=weights, k=1)[0]

    # pick a single index in that category
    n = avail[chosen_kind]
    idx = random.randint(0, n - 1)
    return {chosen_kind: [idx]}


def mutate(tree: ast.AST) -> ast.AST:
    """
    Required entry point. Given an AST, return a mutated AST.
    Driver sets the RNG seed; do NOT set it here.
    """
    # Pass 1
    counter = CandidateCounter()
    counter.visit(tree)

    plan = _choose_plan(counter)
    if not plan:
        return tree

    # Pass 2
    mutator = Mutator(plan,
                      first_def_names=counter.first_def_names,
                      cmp_keys=counter._cmp_keys)
    new_tree = mutator.visit(tree)
    ast.fix_missing_locations(new_tree)
    return new_tree
