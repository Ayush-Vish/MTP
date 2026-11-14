"""Drop-in Gurobi-compatible wrapper around PySCIPOpt.

This module provides a ``gurobipy``-like API so that the 5Guard algorithm
files (iar.py, opt.py, dtr.py, rnr.py, cis.py, nis.py) can run without
modification against the open-source SCIP solver, bypassing the Gurobi
license model-size limit.
"""

from __future__ import annotations

import os
from pathlib import Path
from pyscipopt import Model as _SCIPModel
from pyscipopt import quicksum as _scip_quicksum


# ─── GRB constants ────────────────────────────────────────────────────────────

class _GRB:
    """Mimics ``gurobipy.GRB``."""
    BINARY      = "B"
    CONTINUOUS  = "C"
    INTEGER     = "I"
    MAXIMIZE    = "maximize"
    MINIMIZE    = "minimize"
    OPTIMAL     = 2          # Gurobi status code for optimal
    INFEASIBLE  = 3
    INF_OR_UNBD = 4
    UNBOUNDED   = 5
    TIME_LIMIT  = 9

GRB = _GRB()


# ─── Variable wrapper ─────────────────────────────────────────────────────────

class _VarProxy:
    """Wraps a PySCIPOpt variable to provide Gurobi-compatible attributes."""

    def __init__(self, scip_var, model_ref: "SCIPModel"):
        self._var = scip_var
        self._model = model_ref

    # --- Arithmetic forwarding ---
    def __add__(self, other):
        other_v = _unwrap(other)
        return _ExprProxy(self._var + other_v, self._model)

    def __radd__(self, other):
        other_v = _unwrap(other)
        return _ExprProxy(other_v + self._var, self._model)

    def __sub__(self, other):
        other_v = _unwrap(other)
        return _ExprProxy(self._var - other_v, self._model)

    def __rsub__(self, other):
        other_v = _unwrap(other)
        return _ExprProxy(other_v - self._var, self._model)

    def __mul__(self, other):
        other_v = _unwrap(other)
        return _ExprProxy(self._var * other_v, self._model)

    def __rmul__(self, other):
        other_v = _unwrap(other)
        return _ExprProxy(other_v * self._var, self._model)

    def __truediv__(self, other):
        other_v = _unwrap(other)
        return _ExprProxy(self._var / other_v, self._model)

    def __neg__(self):
        return _ExprProxy(-self._var, self._model)

    # --- Comparison (for constraints) ---
    def __le__(self, other):
        other_v = _unwrap(other)
        return _ConstrExpr(self._var <= other_v)

    def __ge__(self, other):
        other_v = _unwrap(other)
        return _ConstrExpr(self._var >= other_v)

    def __eq__(self, other):
        other_v = _unwrap(other)
        return _ConstrExpr(self._var == other_v)

    # --- Solution value (Gurobi case-insensitivity: .X and .x) ---
    @property
    def X(self) -> float:
        try:
            return float(self._model._scip.getVal(self._var))
        except Exception:
            return 0.0

    @property
    def x(self) -> float:
        return self.X

    # --- Variable name (Gurobi case-insensitivity: .VarName, .varName, .name) ---
    @property
    def VarName(self) -> str:
        return self._var.name

    @property
    def varName(self) -> str:
        return self._var.name

    @property
    def name(self) -> str:
        return self._var.name

    @property
    def lb(self):
        try:
            return self._var.getLbOriginal()
        except Exception:
            return 0.0

    @property
    def ub(self):
        try:
            return self._var.getUbOriginal()
        except Exception:
            return None

    def __repr__(self):
        return f"VarProxy({self._var.name})"


# ─── Expression wrapper ───────────────────────────────────────────────────────

class _ExprProxy:
    """Wraps a PySCIPOpt expression so chaining and comparisons work seamlessly."""

    def __init__(self, expr, model_ref: "SCIPModel"):
        self._expr = expr
        self._model = model_ref

    def __add__(self, other):
        other_e = _unwrap(other)
        return _ExprProxy(self._expr + other_e, self._model)

    def __radd__(self, other):
        other_e = _unwrap(other)
        return _ExprProxy(other_e + self._expr, self._model)

    def __sub__(self, other):
        other_e = _unwrap(other)
        return _ExprProxy(self._expr - other_e, self._model)

    def __rsub__(self, other):
        other_e = _unwrap(other)
        return _ExprProxy(other_e - self._expr, self._model)

    def __mul__(self, other):
        other_e = _unwrap(other)
        return _ExprProxy(self._expr * other_e, self._model)

    def __rmul__(self, other):
        other_e = _unwrap(other)
        return _ExprProxy(other_e * self._expr, self._model)

    def __truediv__(self, other):
        other_e = _unwrap(other)
        return _ExprProxy(self._expr / other_e, self._model)

    def __neg__(self):
        return _ExprProxy(-self._expr, self._model)

    def __le__(self, other):
        other_e = _unwrap(other)
        return _ConstrExpr(self._expr <= other_e)

    def __ge__(self, other):
        other_e = _unwrap(other)
        return _ConstrExpr(self._expr >= other_e)

    def __eq__(self, other):
        other_e = _unwrap(other)
        return _ConstrExpr(self._expr == other_e)

    def getValue(self) -> float:
        try:
            return float(self._model._scip.getVal(self._expr))
        except Exception:
            return 0.0

    def __repr__(self):
        return f"ExprProxy({self._expr})"


class _ConstrExpr:
    """Holds a constraint expression ready to be added to the model."""
    def __init__(self, cons_expr):
        self._cons = cons_expr


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _unwrap(obj):
    """Extract the raw SCIP object from our wrappers."""
    if isinstance(obj, _VarProxy):
        return obj._var
    if isinstance(obj, _ExprProxy):
        return obj._expr
    if isinstance(obj, _ConstrExpr):
        return obj._cons
    return obj


def quicksum(iterable):
    """Drop-in for ``gp.quicksum`` — unwraps proxies and returns ``_ExprProxy``."""
    items = list(iterable)
    if not items:
        return 0.0
    unwrapped = [_unwrap(x) for x in items]
    model = None
    for x in items:
        if hasattr(x, "_model") and x._model is not None:
            model = x._model
            break
    scip_expr = _scip_quicksum(unwrapped)
    return _ExprProxy(scip_expr, model)


# ─── Model wrapper ────────────────────────────────────────────────────────────

class SCIPModel:
    """Gurobi-compatible Model backed by SCIP."""

    def __init__(self, name: str = ""):
        self._scip = _SCIPModel(name)
        self._scip.hideOutput()
        try:
            self._scip.setParam("limits/time", 15.0)
        except Exception:
            pass
        self._vars_by_name: dict[str, _VarProxy] = {}
        self._cons_by_name: dict[str, object] = {}
        self._status_code = 0

    def _ensure_problem_stage(self):
        """Reset SCIP stage back to problem building if it was already solved."""
        try:
            if self._scip.getStage() > 1:
                self._scip.freeTransform()
        except Exception:
            pass

    # --- Variable management ---

    def addVar(self, lb=0.0, ub=None, obj=0.0, vtype="C", name=""):
        self._ensure_problem_stage()
        if ub is None:
            if vtype == "B":
                ub = 1.0
            else:
                ub = None
        scip_var = self._scip.addVar(name=name, vtype=vtype, lb=lb, ub=ub, obj=obj)
        proxy = _VarProxy(scip_var, self)
        if name:
            self._vars_by_name[name] = proxy
        return proxy

    def getVarByName(self, name: str) -> _VarProxy | None:
        if name in self._vars_by_name:
            return self._vars_by_name[name]
        for v in self._scip.getVars():
            if v.name == name:
                p = _VarProxy(v, self)
                self._vars_by_name[name] = p
                return p
        return None

    def getVars(self) -> list[_VarProxy]:
        scip_vars = self._scip.getVars()
        proxies = []
        for v in scip_vars:
            if v.name in self._vars_by_name:
                proxies.append(self._vars_by_name[v.name])
            else:
                p = _VarProxy(v, self)
                if v.name:
                    self._vars_by_name[v.name] = p
                proxies.append(p)
        return proxies

    # --- Constraint management ---

    def addConstr(self, constr, name=""):
        self._ensure_problem_stage()
        cons_raw = _unwrap(constr)
        if isinstance(cons_raw, bool) or cons_raw is None:
            return None
        try:
            scip_cons = self._scip.addCons(cons_raw, name=name)
        except (AssertionError, TypeError):
            return None
        if name:
            self._cons_by_name[name] = scip_cons
        return scip_cons

    def getConstrByName(self, name: str):
        if name in self._cons_by_name:
            return self._cons_by_name[name]
        for c in self._scip.getConss():
            if c.name == name:
                self._cons_by_name[name] = c
                return c
        return None

    def remove(self, constr):
        if constr is not None:
            self._ensure_problem_stage()
            try:
                self._scip.delCons(constr)
            except Exception:
                pass
            if hasattr(constr, "name") and constr.name in self._cons_by_name:
                del self._cons_by_name[constr.name]

    # --- Objective ---

    def setObjective(self, expr, sense=None):
        self._ensure_problem_stage()
        raw = _unwrap(expr)
        if sense in (GRB.MAXIMIZE, "maximize", -1):
            sense_str = "maximize"
        else:
            sense_str = "minimize"
        self._scip.setObjective(raw, sense_str)

    @property
    def objVal(self) -> float:
        try:
            return float(self._scip.getObjVal())
        except Exception:
            return 0.0

    @property
    def ObjVal(self) -> float:
        return self.objVal

    # --- Solve ---

    def optimize(self):
        self._scip.optimize()
        scip_status = self._scip.getStatus()
        if scip_status == "optimal":
            self._status_code = _GRB.OPTIMAL
        elif scip_status == "infeasible":
            self._status_code = _GRB.INFEASIBLE
        elif scip_status == "unbounded":
            self._status_code = _GRB.UNBOUNDED
        elif scip_status == "timelimit":
            self._status_code = _GRB.TIME_LIMIT
        else:
            self._status_code = _GRB.INFEASIBLE

    @property
    def status(self):
        return self._status_code

    # --- Parameters ---

    def setParam(self, name, value):
        param_map = {
            "Threads": "lp/threads",
            "OutputFlag": None,
            "TimeLimit": "limits/time",
            "MIPGap": "limits/gap",
        }
        scip_name = param_map.get(name, name)
        if scip_name is None:
            if name == "OutputFlag" and value == 0:
                self._scip.hideOutput()
            return
        try:
            self._scip.setParam(scip_name, value)
        except Exception:
            pass

    # --- Model I/O ---

    def write(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        try:
            self._scip.writeProblem(path)
        except Exception:
            lp_path = Path(path).with_suffix(".lp")
            self._scip.writeProblem(str(lp_path))

    def update(self):
        pass


# ─── Module-level Gurobi-compatible API ───────────────────────────────────────

def Model(name: str = "") -> SCIPModel:
    return SCIPModel(name)


def read(path: str) -> SCIPModel:
    m = SCIPModel()
    m._scip = _SCIPModel()
    m._scip.hideOutput()
    try:
        m._scip.setParam("limits/time", 15.0)
    except Exception:
        pass
    m._scip.readProblem(path)
    for v in m._scip.getVars():
        proxy = _VarProxy(v, m)
        if v.name:
            m._vars_by_name[v.name] = proxy
    for c in m._scip.getConss():
        if c.name:
            m._cons_by_name[c.name] = c
    return m


def setParam(name, value):
    if name == "OutputFlag" and value == 0:
        pass
