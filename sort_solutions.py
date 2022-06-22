from logging import addLevelName
from pagerank import get_pagerank_svc_scores
from numpy import *
def sort_solutions(solutions, svc_scores,aggregation_method = "Max"):
    def get_pod_svc():
        if pod.split("-")[0] == "frontend":
            return "frontend"
        else:
            return pod.split("-")[0][:-1]
    solutions_scores = {}
    for solution in solutions:
        scores_list = []
        for pod in solution.split(","):
            svc_name = get_pod_svc()
            scores_list.append(svc_scores[svc_name])
        if aggregation_method == "Max":
            max_scores = max(scores_list)
        elif aggregation_method == "Average":
            max_scores = mean(scores_list)
        solutions_scores[solution] = max_scores

    return list(sorted(solutions_scores.items(), key = lambda x: x[1], reverse= True))[:]
def read_solutions(filename):
    solutions = []
    with open(filename, "r") as f:
        for line in f.readlines():
            line = line.strip("\n")
            solution = line.split(" ")
            solution_len = len(solution)
            solution_str = solution[0]
            for i in range(1,solution_len):
                solution_str = solution_str + "," + solution[i]
            solutions.append(solution_str)
    return solutions
svc_scores = get_pagerank_svc_scores()
solutions = read_solutions("solutions/2021-09-29-07:05:37_solutions.txt")
print(sort_solutions(solutions,svc_scores,aggregation_method="Average"))