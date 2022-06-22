  # -*- coding: utf-8 -*
from traces_preprocesses.query import *
from send_reqs.reqs import *
from traces_preprocesses.trace_utils import str2f,path_aggregate
from utils.general_util import * 
from utils.z3_solver import *
from pagerank import get_pagerank_svc_scores
import time
from datetime import timedelta, datetime
import os
import json
import copy
from image_map import *
import logging
 # get new execution path and travese it to new clause
def get_pod_status(pod_name):
    status_command = "kubectl get pod -n hipster | grep %s | awk '{print $3}'" % (pod_name)
    status = os.popen(status_command).read().strip()
    return status
def wait_until_not_running(pod_name):
    while True:
        status = get_pod_status(pod_name)
        if status != "Running":
            break
def wait_until_recover(pod_name):
    while True:
        status = get_pod_status(pod_name)
        if status == "Running":
            break

def getNewClause(test_case_name, recorded_traceid):
    test_case_response = test_case(test_case_name)
    time.sleep(15)
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()) 
    traces = collect_trace(ts)
    svc_paths = extract_pod_path(traces,recorded_traceid)
    print(recorded_traceid)
    print(svc_paths)
    formulas = path_to_cnf(svc_paths)
    print_formulas(formulas)
    return formulas

def fault_injection(pod_name):
    fault_cmd = "/opt/chaosblade/blade c k8s pod-pod fail --namespace hipster --kubeconfig ~/.kube/config --names " + pod_name
    print(fault_cmd)
    if get_pod_status(pod_name) != "Running":
        import pdb; pdb.set_trace()
    wait_until_recover(pod_name)
    f = os.popen(fault_cmd)
    return_str = f.read()
    return_json = json.loads(return_str)
    print(return_json)
    svc = pod_name.split("-")[0]
    if svc[-1].isdigit():
        svc = svc[:-1]
    double_fault_cmd = "kubectl patch pod {} -n {} -p \'{{\"spec\":{{\"containers\":[{{\"name\": \"{}\",\"image\": \"{}\"}}]}}}}\'".format(pod_name, "hipster", "server",image_map[svc]+"-fault-injection")
    f1 = os.popen(double_fault_cmd)
    wait_until_not_running(pod_name)
    if return_json["code"] == 200:
        return True, return_json["result"]
    else:
        return False, _

def recover(blade_id):
    query_cmd = "/opt/chaosblade/blade q k8s create " + blade_id + " --kubeconfig ~/.kube/config "
    
    f = os.popen(query_cmd)
    return_str = f.read()
    return_json = json.loads(return_str)
    if return_json["code"] == 200:
        pod = (return_json["result"]["statuses"][0]["identifier"]).split("/")[2]
        svc = pod.split("-")[0]
        if svc[-1].isdigit():
            svc = svc[:-1]
        recover_cmd1 = "kubectl patch pod {} -n {} -p \'{{\"spec\":{{\"containers\":[{{\"name\": \"{}\",\"image\": \"{}\"}}]}}}}\'".format(pod, "hipster", "server",image_map[svc])
        recover_cmd2 = "kubectl patch pod {} -n {} -p \'{{\"spec\":{{\"containers\":[{{\"name\": \"{}\",\"image\": \"{}\"}}]}}}}\'".format(pod, "hipster", "istio-proxy",image_map["istio-proxy"])
        f1 = os.popen(recover_cmd1)
        f2 = os.popen(recover_cmd2)
        print(query_cmd, " ", pod)
        wait_until_recover(pod)
        # print(recover_cmd1)
        # print(recover_cmd2)
        # print(f1,f2)
        return True
    return False

def restoreStep(blade_ids):
    if isinstance(blade_ids,list):
        for blade_id in blade_ids:
            recover(blade_id)
    else:
        recover(blade_ids)
    time.sleep(0.5)

def verifyCorrectness(test_case_name,recorded_traceid):#adservice need more verify
    #特殊查询一下adservice所有pod的状态
    adservice_pod_query = "kubectl get pod -n hipster |grep adservice |awk '{ print $3 }'"
    query_res = os.popen(adservice_pod_query)
    status = query_res.read()
    adservice_flag = False
    if "\n" in status:
        for line in status.strip("\n").split("\n"):
            if line == "Running":
                adservice_flag = True
                break
        if adservice_flag == False:
            print("adservice unHealthy")
            return False
                
    try :
        time.sleep(2)
        test_case_response = test_case(test_case_name)
        time.sleep(15)
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()) 
        traces = collect_trace(ts)
        svc_paths = extract_pod_path(traces,recorded_traceid)
        print(recorded_traceid)
        print(svc_paths)
        if test_case_response.status_code == 200:
            # print(test_case_response.text)
            return True
        return False
    except:
        return False

def forwardStep(test_case_name, base_triedHypotheses, hypothesis,recorded_traceid):
    print(hypothesis)
    blade_ids = []
    for sub_hypo in hypothesis:
        if sub_hypo not in base_triedHypotheses:
            inject_flag, blade_id = fault_injection(sub_hypo)
            if sub_hypo.split("-")[0][:-1] == "adservice":
                print("adservice : ", sub_hypo)
                # time.sleep(8) #wait until adservice down
            if inject_flag == True:
                blade_ids.append(blade_id)
    correctness = verifyCorrectness(test_case_name,recorded_traceid)
    return correctness, blade_ids

def backwardStep(test_case_name, formulas, triedHypotheses, recorded_traceid):
    newClause = getNewClause(test_case_name, recorded_traceid) # get new execution path and travese it to new clause
    for clause in newClause:
        if clause not in formulas:
            formulas.append(clause)
    starttime = datetime.now()
    print("SAT Solving.....")
    print(formulas)
    solver,myvars = get_cnf_solver(formulas)
    hypotheses = get_incomplete_hypotheses(solver,triedHypotheses)
    hypotheses = remove_redundant_hypotheses(hypotheses,formulas)
    print(hypotheses)
    endtime = datetime.now()
    return hypotheses,starttime,endtime

def sorted_with_pagerank(to_sort_hypotheses, page_rank_scores):
    hypotheses_scores = []
    for sub_hypothesis in to_sort_hypotheses:
        print(sub_hypothesis)
        if len(sub_hypothesis) == 1 or isinstance(sub_hypothesis,str) == True:
            if isinstance(sub_hypothesis,str) == True:
                pod = sub_hypothesis
            else:
                pod = sub_hypothesis[0]
            svc = pod.split("-")[0]
            if svc != "frontend":
                svc = svc[:-1]
            pod_score = page_rank_scores[svc]
            hypotheses_scores.append((sub_hypothesis, pod_score))
        else:
            sum_score = 0
            for pod in sub_hypothesis:
                svc = pod.split("-")[0]
                if svc != "frontend":
                    svc = svc[:-1]
                pod_score = page_rank_scores[svc]
                sum_score = sum_score + pod_score
            hypotheses_scores.append((sub_hypothesis, sum_score/len(sub_hypothesis)))
    L1 = sorted(hypotheses_scores, key = lambda x:x[0])
    L2 = sorted(L1, key = lambda x:x[1], reverse = True)
    sorted_hypotheses = []
    for item in L2:
        sorted_hypotheses.append(item[0])
    return sorted_hypotheses

def evaluator(test_case_name, total_triedHypotheses, hypothesis, formulas, solutions, recorded_traceid, PR_scores):
    correctness, blade_ids = forwardStep(test_case_name, [], hypothesis,recorded_traceid)
    
    if correctness == True or len(hypothesis) == 0:
        # print("tried:----",triedHypotheses)
        hypotheses,starttime,endtime = backwardStep(test_case_name, formulas,[] + hypothesis, recorded_traceid)
        sorted_hypotheses = sorted_with_pagerank(hypotheses, PR_scores)
        # hypotheses_queue = Hypotheses_to_queue(hypotheses, )
        
        print("SAT Solving Cost:" + str((endtime - starttime).seconds) + " Seconds")
        if len(hypotheses) != 0:
            backup_hypotheses = [[[], sorted_hypotheses]]
            res_solutions,triedHypotheses = evaluateHypotheses(test_case_name, total_triedHypotheses, backup_hypotheses, formulas,solutions, recorded_traceid, PR_scores)
            print("SAT Solving Cost:" + str((endtime - starttime).seconds) + " Seconds")
            return res_solutions
        else:
            return []
    else:
        return []

def evaluateHypotheses(test_case_name,  total_triedHypotheses, hypotheses,formulas,solutions,  recorded_traceid, PR_scores):
    if len(hypotheses) == 0:
        return solutions, total_triedHypotheses
    parent_index = -1
    while len(hypotheses) > 0:
        parent_index = parent_index + 1
        # import pdb; pdb.set_trace()
        to_inject_hypotheses = hypotheses[0]
        hypotheses.pop(0)
        base_tried_hypotheses = to_inject_hypotheses[0]
        base_blade_ids = []
        #pre_judge
        should_be_inject = False
        for index in range(len(to_inject_hypotheses[1])):

            hypothesis = to_inject_hypotheses[1][index]
            validate_solution_flags = False
            for solution in solutions:
                if set(solution) <= set(sorted_with_pagerank(base_tried_hypotheses + hypothesis, PR_scores)):
                    validate_solution_flags = True
                    break
            # (not total_triedHypotheses or hypothesis not in total_triedHypotheses)  and
            if sorted_with_pagerank(base_tried_hypotheses + hypothesis, PR_scores) not in total_triedHypotheses and (set(hypothesis)<set(base_tried_hypotheses)) == False and validate_solution_flags == False:
                should_be_inject = True
                break
        if should_be_inject == False:
            continue
        for pod in base_tried_hypotheses:
            inject_flag, blade_id = fault_injection(pod)
            base_blade_ids.append(blade_id)
        
        for index in range(len(to_inject_hypotheses[1])):
            hypothesis = to_inject_hypotheses[1][index]
            validate_solution_flags = False
            for solution in solutions:
                if set(solution) <= set(sorted_with_pagerank(base_tried_hypotheses + hypothesis, PR_scores)):
                    validate_solution_flags = True
                    break
            # (not total_triedHypotheses or hypothesis not in total_triedHypotheses)  and
            if sorted_with_pagerank(base_tried_hypotheses + hypothesis, PR_scores) not in total_triedHypotheses and (set(hypothesis)<set(base_tried_hypotheses)) == False and validate_solution_flags == False:
                correctness, blade_ids = forwardStep(test_case_name, base_tried_hypotheses, hypothesis,recorded_traceid)
                # blade_ids.append(blade_id)
                if correctness == True:
                    next_hypotheses,starttime,endtime = backwardStep(test_case_name, formulas,base_tried_hypotheses + hypothesis, recorded_traceid)
                    next_based_tried_hypotheses = sorted_with_pagerank(list(set(base_tried_hypotheses + hypothesis)), PR_scores)
                    total_triedHypotheses.append(sorted_with_pagerank(list(set(base_tried_hypotheses + hypothesis)), PR_scores))
                    hypotheses.append([next_based_tried_hypotheses,sorted_with_pagerank(next_hypotheses,PR_scores)])
                    print_str = "{}-{}. {} {}: {}".format(parent_index,index,base_tried_hypotheses,hypothesis, "False")
                    logger.info((print_str))
                else:
                    print_str = "{}-{}. {} {}: {}".format(parent_index,index,base_tried_hypotheses, hypothesis,"True")
                    logger.info((print_str))
                    total_triedHypotheses.append(sorted_with_pagerank(list(set(base_tried_hypotheses + hypothesis)), PR_scores))
                    solutions.append(sorted_with_pagerank(list(set(base_tried_hypotheses + hypothesis)), PR_scores))
                restoreStep(blade_ids)
        restoreStep(base_blade_ids)
    return solutions, total_triedHypotheses


def concreteEvaluator(test_case_name, hypothesis, formulas, recorded_traceid, PR_scores):
    if len(hypothesis) == 0:
        solutions = []
        base_triedHypotheses = []
        total_triedHypotheses = []
        blades_ids = []
        solutions = evaluator(test_case_name, total_triedHypotheses, hypothesis, formulas, solutions, recorded_traceid, PR_scores)
        return solutions, total_triedHypotheses


def Evaluate(recorded_traceid,  PR_scores, test_case_name = "index", inject_flag = True):
    # test_case_response = test_case(test_case_name)
    # time.sleep(15)
    # ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()) 
    # traces = collect_trace(ts)
    # svc_paths = extract_pod_path(traces,recorded_traceid)
    # print(svc_paths)
    # formulas = path_to_cnf(svc_paths)
    # print_formulas(formulas)
    formulas = []
    if inject_flag == True:
        return concreteEvaluator(test_case_name, [], formulas, recorded_traceid, PR_scores)
    else:
        backwardStep(test_case_name, formulas, [], recorded_traceid)
        return None, None


def test():
    # test_case_response = index_req()
    # time.sleep(13) # wait for complete trace
    # ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime() ) 
    # traces = collect_trace(ts)
    # recorded_traceid = []
    # # traces = {1096809653L: {u'frontend_ListProducts': {'duration': [2568], 'podName': u'frontend-56489fb989-zmr4d', 'operationName': u'frontend_ListProducts', 'children': [u'productcatalogservice_ListProducts'], 'occurrence': 1}, u'productcatalogservice_ListProducts': {'duration': [54], 'podName': u'productcatalogservice1-55fcc699c6-kns9d', 'operationName': u'productcatalogservice_ListProducts', 'children': [], 'occurrence': 1}, u'currencyservice_GetSupportedCurrencies': {'duration': [232], 'podName': u'currencyservice1-64cc786bb8-9q22s', 'operationName': u'currencyservice_GetSupportedCurrencies', 'children': [], 'occurrence': 1}, u'frontend_Recv.': {'duration': [1248], 'podName': u'frontend-56489fb989-zmr4d', 'operationName': u'frontend_Recv.', 'children': [u'frontend_GetSupportedCurrencies', u'frontend_ListProducts', u'frontend_GetCart', u'frontend_Convert', u'frontend_Convert', u'frontend_Convert', u'frontend_Convert', u'frontend_Convert', u'frontend_Convert', u'frontend_Convert', u'frontend_Convert', u'frontend_Convert', u'frontend_GetAds'], 'occurrence': 1}, u'frontend_Convert': {'duration': [3483, 3183, 2985, 3066, 3202, 3548, 3696, 3079, 3303], 'podName': u'frontend-56489fb989-zmr4d', 'operationName': u'frontend_Convert', 'children': [u'currencyservice_Convert'], 'occurrence': 9}, u'frontend_GetSupportedCurrencies': {'duration': [3887], 'podName': u'frontend-56489fb989-zmr4d', 'operationName': u'frontend_GetSupportedCurrencies', 'children': [u'currencyservice_GetSupportedCurrencies'], 'occurrence': 1}, u'adservice_getads': {'duration': [76], 'podName': u'adservice1-7bfc6777b5-p6gpf', 'operationName': u'adservice_getads', 'children': [], 'occurrence': 1}, u'frontend_GetCart': {'duration': [2632], 'podName': u'frontend-56489fb989-zmr4d', 'operationName': u'frontend_GetCart', 'children': [], 'occurrence': 1}, u'frontend_GetAds': {'duration': [7450], 'podName': u'frontend-56489fb989-zmr4d', 'operationName': u'frontend_GetAds', 'children': [u'adservice_getads'], 'occurrence': 1}, u'currencyservice_Convert': {'duration': [216, 187, 195, 191, 189, 194, 216, 185, 210], 'podName': u'currencyservice1-64cc786bb8-9q22s', 'operationName': u'currencyservice_Convert', 'children': [], 'occurrence': 9}}}
    # svc_paths = extract_pod_path(traces,recorded_traceid)
    # formulas = path_to_cnf(svc_paths)
    # print(formulas)
    # print_formulas(formulas)
    # print(verifyCorrectness("index"))
    test_case_name = "index"
    recorded_traceid = []
    # getNewClause(test_case_name, recorded_traceid)
    page_rank_scores = get_pagerank_svc_scores()
    solutions, triedHypotheses = Evaluate(recorded_traceid, page_rank_scores, test_case_name , True)
    return solutions, triedHypotheses
    # print(forwardStep(test_case_name, ["productcatalogservice1-55fcc699c6-v726g"]))
logger = logging.getLogger(__name__)
log_path = "./logs/BFS_PR_" + datetime.now().strftime("%Y-%m-%d-%H:%M:%S") + "LDFI solve logs"
file_handler = logging.FileHandler(log_path)
formatter = logging.Formatter("%(asctime)s\t%(message)s", datefmt="%Y-%m-%d %H:%M:%S")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.setLevel(logging.INFO)
global_index = 0
solutions, triedHypotheses = test()
import pdb; pdb.set_trace()
logger.info((solutions))
logger.info((triedHypotheses))
solution_path = "./solutions/" + datetime.now().strftime("%Y-%m-%d-%H:%M:%S") + "_solutions.txt"
with open(solution_path,'w') as f:
    for item in solutions:
        temp = ' '.join(map(lambda x:str(x),item))
        f.write(temp+'\n')
# print(test_case("setCurrency"))