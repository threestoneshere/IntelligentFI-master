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
    test_case_response = test_case(test_case_name)  # 测试请求能否正常执行
    time.sleep(15)
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()) 
    traces = collect_trace(ts)  # 获取一分钟前至今的所有trace信息并返回path_list
    svc_paths = extract_pod_path(traces, recorded_traceid)
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
    double_fault_cmd = "kubectl patch pod {} -n {} -p \'{{\"spec\":{{\"containers\":[{{\"name\": \"{}\",\"image\": \"{}\"}}]}}}}\'".format(pod_name, "hipster", "server", image_map[svc]+"-fault-injection")
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
    if isinstance(blade_ids, list):
        for blade_id in blade_ids:
            recover(blade_id)
    else:
        recover(blade_ids)
    time.sleep(0.5)


def verifyCorrectness(test_case_name, recorded_traceid):  # adservice need more verify
    # 特殊查询一下adservice所有pod的状态
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
                
    try:
        time.sleep(2)
        test_case_response = test_case(test_case_name)
        time.sleep(15)
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()) 
        traces = collect_trace(ts)
        svc_paths = extract_pod_path(traces, recorded_traceid)
        print(recorded_traceid)
        print(svc_paths)
        if test_case_response.status_code == 200:
            # print(test_case_response.text)
            return True
        return False
    except:
        return False


def forwardStep(test_case_name, base_triedHypotheses, hypothesis, recorded_traceid):
    print(hypothesis)
    blade_ids = []
    for sub_hypo in hypothesis:
        if sub_hypo not in base_triedHypotheses:
            inject_flag, blade_id = fault_injection(sub_hypo)
            if sub_hypo.split("-")[0][:-1] == "adservice":
                print("adservice : ", sub_hypo)
                # time.sleep(8)  # wait until adservice down
            if inject_flag == True:
                blade_ids.append(blade_id)  # 若故障注入成功则记录id
    correctness = verifyCorrectness(test_case_name, recorded_traceid)
    return correctness, blade_ids


def backwardStep(test_case_name, formulas, triedHypotheses, recorded_traceid):
    newClause = getNewClause(test_case_name, recorded_traceid)  # get new execution path and travese it to new clause
    for clause in newClause:
        if clause not in formulas:
            formulas.append(clause)
    starttime = datetime.now()
    print("SAT Solving.....")
    print(formulas)
    solver, myvars = get_cnf_solver(formulas)
    hypotheses = get_incomplete_hypotheses(solver, triedHypotheses)
    hypotheses = remove_redundant_hypotheses(hypotheses, formulas)
    print(hypotheses)
    endtime = datetime.now()
    return hypotheses, starttime, endtime


def evaluator(test_case_name, base_triedHypotheses, total_triedHypotheses, hypothesis, formulas, solutions, blades_ids, recorded_traceid, parent_index):  # parent index初始为0
    correctness, blade_ids = forwardStep(test_case_name, base_triedHypotheses, hypothesis, recorded_traceid)
    # import pdb; pdb.set_trace()
    if blades_ids == []:  # 第一次执行evaluator时blades_id为[]
        blades_ids = blade_ids
    elif len(blade_ids) == 1:
        blades_ids = blades_ids + blade_ids
    else:
        blades_ids.append(blade_ids)
    print(hypothesis, correctness, blade_ids, blades_ids, base_triedHypotheses, total_triedHypotheses)
    
    if correctness == True or len(hypothesis) == 0:
        # print("tried:----",triedHypotheses)
        hypotheses, starttime, endtime = backwardStep(test_case_name, formulas, base_triedHypotheses + hypothesis, recorded_traceid)
        global global_index
        print_str = "{}. {} {}: {}".format(global_index, parent_index, hypothesis, hypotheses)
        logger.info((print_str))
        global_index = global_index + 1
        print("SAT Solving Cost:" + str((endtime - starttime).seconds) + " Seconds")
        if len(hypotheses) != 0:
            # temp_triedHypotheses = copy.deepcopy(triedHypotheses)[-1]

            base_triedHypotheses = sorted(list(set(base_triedHypotheses + hypothesis)))  # base_triedHypothesis为已测试的有效注入
            res_solutions, triedHypotheses = evaluateHypotheses(test_case_name, base_triedHypotheses, total_triedHypotheses, hypotheses, formulas, solutions, blades_ids, recorded_traceid, global_index - 1)
            if len(blade_ids) == 1 and blade_ids[0] in blades_ids:
                restoreStep(blade_ids[0])
                blades_ids.remove(blade_ids[0])
            elif blade_ids in blades_ids:
                restoreStep(blade_ids)
                blades_ids.remove(blade_ids)
            else:
                import pdb; pdb.set_trace()
            print("SAT Solving Cost:" + str((endtime - starttime).seconds) + " Seconds")
            return res_solutions,blades_ids
        else:
            return [],blades_ids
    else:
        global global_index
        print_str = "{}. {} {}: {}".format(global_index,parent_index,hypothesis,"True")
        logger.info((print_str))
        global_index = global_index + 1
        total_triedHypotheses.append(sorted(list(set(base_triedHypotheses + hypothesis))))
        solutions.append(sorted(list(set(base_triedHypotheses + hypothesis))))
        # print("---------",triedHypotheses)
        # restoreStep(blades_ids[-1])
        # blades_ids = blades_ids[:-1]
        if len(blade_ids) == 1 and blade_ids[0] in blades_ids:
            restoreStep(blade_ids[0])
            blades_ids.remove(blade_ids[0])
        elif blade_ids in blades_ids:
            restoreStep(blade_ids)
            blades_ids.remove(blade_ids)
        else:
            import pdb; pdb.set_trace()

        return solutions,blades_ids


def evaluateHypotheses(test_case_name, base_triedHypotheses, total_triedHypotheses, hypotheses, formulas, solutions, blades_ids, recorded_traceid, parent_index):
    if len(hypotheses) == 0:
        return solutions, total_triedHypotheses
    for index in range(len(hypotheses)):
        temp_base_triedHypotheses = copy.deepcopy(base_triedHypotheses)
        hypothesis = hypotheses[index]
        # import pdb; pdb.set_trace()
        validate_solution_flags = False
        for solution in solutions:
            if set(solution) <= set(sorted(base_triedHypotheses + hypothesis)):  # 存在一个solution被base_triedHypotheses和hypothesis包含
                validate_solution_flags = True
                break
        if (not total_triedHypotheses or hypothesis not in total_triedHypotheses) and sorted(base_triedHypotheses + hypothesis) not in total_triedHypotheses and (set(hypothesis) < set(base_triedHypotheses)) == False and validate_solution_flags == False:
            print("tried:-+--", base_triedHypotheses)
            # temp_triedHypotheses = (triedHypotheses)
            sols, blades_ids = evaluator(test_case_name, temp_base_triedHypotheses, total_triedHypotheses, hypothesis ,formulas,solutions, blades_ids, recorded_traceid,parent_index)
            
            return evaluateHypotheses(test_case_name, base_triedHypotheses, total_triedHypotheses,  hypotheses[index+1:], formulas, sols, blades_ids, recorded_traceid,parent_index)
        else:
            return evaluateHypotheses(test_case_name, base_triedHypotheses, total_triedHypotheses,  hypotheses[index+1:], formulas, solutions, blades_ids, recorded_traceid,parent_index)


def concreteEvaluator(test_case_name, hypothesis, formulas, recorded_traceid):  # hypothesis初始为[]
    if len(hypothesis) == 0:
        solutions = []
        base_triedHypotheses = []
        total_triedHypotheses = []
        blades_ids = []
        solutions, _ = evaluator(test_case_name, base_triedHypotheses, total_triedHypotheses, hypothesis, formulas, solutions, blades_ids, recorded_traceid, 0)
        return solutions, total_triedHypotheses


def Evaluate(recorded_traceid, test_case_name = "index", inject_flag = True):
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
        return concreteEvaluator(test_case_name, [], formulas, recorded_traceid)
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
    solutions, triedHypotheses = Evaluate(recorded_traceid, test_case_name, True)
    return solutions, triedHypotheses
    # print(forwardStep(test_case_name, ["productcatalogservice1-55fcc699c6-v726g"]))
logger = logging.getLogger(__name__)
log_path = "./logs/DFS_" + datetime.now().strftime("%Y-%m-%d-%H:%M:%S") + "LDFI solve logs"
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