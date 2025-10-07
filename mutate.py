# mutate.py — EECS 481 HW3
# Returns a mutated AST for driver.py to write out.
# Implements: comparison negation, binop swaps (+<->-, *<->//), safe deletion (stmt->Pass).
import ast
import random

# ----- Operator maps (required baseline) -----
CMP_NEGATION = {
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Lt: ast.GtE,
    ast.LtE: ast.Gt,
    ast.Gt: ast.LtE,
    ast.GtE: ast.Lt,
}

BIN_SWAP = {
    ast.Add: ast.Sub,        # + -> -
    ast.Sub: ast.Add,        # - -> +
    ast.Mult: ast.FloorDiv,  # * -> //
    ast.FloorDiv: ast.Mult,  # // -> *
}

# ----- Utilities -----
def names_defined_by_assign_stmt(node):
    """Collect variable names defined by an assignment-like statement."""
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
    Pass 1: count mutation sites and record 'first definitions' of names,
    so we avoid deleting the first def (guardrail). Also track parents so
    we can avoid negating comparisons inside loops (too strong).
    """
    def __init__(self):
        self.cmp_sites = []      # (node, op_index) for Compare ops
        self._cmp_keys = set()   # {(id(node), op_index)} of eligible compares
        self.bin_sites = []      # BinOp nodes
        self.del_sites = []      # Assign/AnnAssign/AugAssign/Expr(Call) stmt nodes

        self._parents = {}       # child -> parent map for ancestry checks

        self.first_def_names = set()
        self._seen_any_def = set()

    # record parent pointers for ancestry checks
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

    def visit_Compare(self, node: ast.Compare):
        # Skip comparisons inside loops (heuristic to avoid over-strong mutants)
        if not self._is_under_loop(node):
            for i, op in enumerate(node.ops):
                if type(op) in CMP_NEGATION:
                    self.cmp_sites.append((node, i))
                    self._cmp_keys.add((id(node), i))
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp):
        if type(node.op) in BIN_SWAP:
            self.bin_sites.append(node)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
        self._maybe_record_first_defs(node)
        self.del_sites.append(node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign):
        self._maybe_record_first_defs(node)
        self.del_sites.append(node)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign):
        self._maybe_record_first_defs(node)
        self.del_sites.append(node)
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr):
        if isinstance(node.value, ast.Call):
            self.del_sites.append(node)
        self.generic_visit(node)

    def _maybe_record_first_defs(self, node):
        for name in names_defined_by_assign_stmt(node):
            if name not in self._seen_any_def:
                self._seen_any_def.add(name)
                self.first_def_names.add(name)


class Mutator(ast.NodeTransformer):
    """
    Pass 2: apply exactly the planned edits. We keep running indices
    in the same visitation order as CandidateCounter (for eligible sites only).
    """
    def __init__(self, plan, first_def_names, cmp_keys):
        super().__init__()
        self.plan = {k: set(v) for k, v in plan.items()}  # sets for O(1) lookups
        self.first_def_names = set(first_def_names)
        self.cmp_keys = set(cmp_keys)

        self.seen_cmp = 0
        self.seen_bin = 0
        self.seen_del = 0

    # ---- Compare ----
    def visit_Compare(self, node: ast.Compare):
        super().generic_visit(node)  # don't overwrite node
        for i, op in enumerate(list(node.ops)):
            if type(op) in CMP_NEGATION:
                eligible = (id(node), i) in self.cmp_keys
                if eligible:
                    if "cmp" in self.plan and self.seen_cmp in self.plan["cmp"]:
                        new_op = CMP_NEGATION[type(op)]()
                        node.ops[i] = ast.copy_location(new_op, op)
                    self.seen_cmp += 1
                # if not eligible, we neither mutate nor advance counter
        return node

    # ---- BinOp ----
    def visit_BinOp(self, node: ast.BinOp):
        super().generic_visit(node)
        if type(node.op) in BIN_SWAP:
            if "bin" in self.plan and self.seen_bin in self.plan["bin"]:
                node.op = BIN_SWAP[type(node.op)]()
            self.seen_bin += 1
        return node

    # ---- Deletion (safe): replace selected stmt with Pass() ----
    def _maybe_delete_stmt(self, node):
        selected = "del" in self.plan and self.seen_del in self.plan["del"]
        self.seen_del += 1
        if not selected:
            return node

        # Guardrail: don't delete first definitions
        if any(name in self.first_def_names for name in names_defined_by_assign_stmt(node)):
            return node

        return ast.copy_location(ast.Pass(), node)

    def visit_Assign(self, node: ast.Assign):
        super().generic_visit(node)
        return self._maybe_delete_stmt(node)

    def visit_AnnAssign(self, node: ast.AnnAssign):
        super().generic_visit(node)
        return self._maybe_delete_stmt(node)

    def visit_AugAssign(self, node: ast.AugAssign):
        super().generic_visit(node)
        return self._maybe_delete_stmt(node)

    def visit_Expr(self, node: ast.Expr):
        super().generic_visit(node)
        if isinstance(node.value, ast.Call):
            return self._maybe_delete_stmt(node)
        return node


def _choose_plan(counter: CandidateCounter) -> dict:
    """
    Decide what to mutate this run.
    Budget: exactly 1 mutation per mutant (selective-friendly).
    Weighted choice among available categories.
    """
    avail = {
        "cmp": len(counter.cmp_sites),
        "bin": len(counter.bin_sites),
        "del": len(counter.del_sites),
    }

    base_weights = {
        "cmp": 0.50,
        "bin": 0.45,  # mostly +<->- ; *<->// when present
        "del": 0.05,
    }

    kinds = [k for k, n in avail.items() if n > 0]
    if not kinds:
        return {}

    weights = [base_weights[k] for k in kinds]
    s = sum(weights)
    weights = [w / s for w in weights] if s > 0 else [1 / len(kinds)] * len(kinds)

    chosen_kind = random.choices(kinds, weights=weights, k=1)[0]

    # pick a single index in that category
    if chosen_kind == "cmp":
        return {"cmp": [random.randint(0, avail["cmp"] - 1)]}
    if chosen_kind == "bin":
        return {"bin": [random.randint(0, avail["bin"] - 1)]}
    return {"del": [random.randint(0, avail["del"] - 1)]}


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
