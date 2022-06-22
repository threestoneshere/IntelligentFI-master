# -*- coding: utf-8 -*
from z3 import *
cnf = [[(u's1', u's2'), (u's2', u's6')], [(u's1', u's3'), (u's3', u's6')], [(u's1', u's4'), (u's4', u's6')], [(u's1', u's5'), (u's5', u's6')]]


def get_cnf_solver(cnf):
    s = Solver()
    formulas = []
    myvars = []  # 存储了cnf中不同traceid所共同包含的所有item
    for formula in cnf:
        clauses = []
        for clause in formula:
            clause_str = str(clause)
            clause_bool = Bool(clause_str)
            clauses.append(clause_bool)
            myvars.append(clause_bool)
        formulas.append(Or(clauses))
    s.add(formulas)
    return s, myvars


def get_incomplete_hypotheses(solver, triedHypotheses):
    # 存在新的执行路径，需要考虑在已注入故障的前提，加入新路径后如何求解
    # print(triedHypotheses)
    if triedHypotheses:
        for item in triedHypotheses:
            print(item)
            solver.add(Bool(item) == True)
    res = solver.check()
    solutions = []
    while res == sat:
        m = solver.model()
        solution = []
        for d in m.decls():
            if m[d] == True:
                solution.append(d.name())
        solutions.append(solution)
        block = []
        for var in m:
            block.append(var() != m[var])
        solver.add(Or(block))
        res = solver.check()
    for solution in solutions:
        if set(solution) > set(triedHypotheses):
            for hypothesis in triedHypotheses:
                solution.remove(hypothesis)
            # print(solution)
        else:
            print("----",solution)
    # import pdb; pdb.set_trace()
    return solutions


# 得到的可注入故障的解过多，废置
def get_all_hypotheses(solver, myvars):
    res = solver.check()
    solutions = []
    while res == sat:
        m = solver.model()
        block = []
        solution = []
        for var in myvars:
            v = m.evaluate(var, model_completion=True)  # model_completion=True表示必须给每一个元素制定具体值
            if v:
                solution.append(var)
            block.append(var != v)
        solutions.append(solution)
        solver.add(Or(block))
        res = solver.check()
    return solutions


def remove_redundant_hypotheses(hypotheses, formulas):
    # clauses_dict = 
    new_hypotheses = []
    str_formulas = []
    for formula in formulas:
        str_formulas.append(map(str, formula))
    formulas_len = len(str_formulas)
    hypo_formula_count = {}
    for hypothesis in hypotheses:
        for i in range(formulas_len):
            hypo_formula_count[i] = 0
        for sub_hypo in hypothesis:
            for i in range(formulas_len):
                formula = str_formulas[i]
                if sub_hypo in formula:
                    hypo_formula_count[i] = hypo_formula_count[i] + 1
        add_flag = True
        for key, value in hypo_formula_count.items():
            if value > 1:
                add_flag = False
                break
        if add_flag:
            new_hypotheses.append(hypothesis)
    return new_hypotheses
