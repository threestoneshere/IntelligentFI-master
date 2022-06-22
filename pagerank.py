  # -*- coding: utf-8 -*
from traces_preprocesses.query import *
from send_reqs.reqs import *
from traces_preprocesses.trace_utils import *
from utils.general_util import *
import time

def collect_page_rank_trace(timestamp):
    endTime = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")-timedelta(minutes=1)
    startTime = endTime - timedelta(minutes=5)
    startTime = datetime.strftime(startTime,  "%Y-%m-%d %H:%M:%S")
    endTime = datetime.strftime(endTime, "%Y-%m-%d %H:%M:%S")
    path_list = dict()
    # import pdb; pdb.set_trace()
    span_list = get_span(start=str2f(startTime), end=str2f(endTime))
    # print(len(span_list))
    # print(span_list)
    if len(span_list) > 0:
        path_list, trace_list = path_aggregate(span_list, path_list)
        return trace_list,span_list
    else:
        return [],[]

def trace_pagerank(pod_pod, pod_trace, trace_pod, pr_trace):
    pod_length = len(pod_pod)
    trace_length = len(pod_trace)
    p_ss = np.zeros((pod_length, pod_length), dtype=np.float32)
    p_sr = np.zeros((pod_length, trace_length), dtype=np.float32)
    p_rs = np.zeros((trace_length, pod_length), dtype=np.float32)
    # matrix = np.zeros((n, n), dtype=np.float32)
    pr = np.zeros((trace_length, 1), dtype=np.float32)
    node_list = []
    for key in pod_pod.keys():
        node_list.append(key)
    trace_list = []
    for key in pod_trace.keys():
        trace_list.append(key)
    # matrix方阵左上角node*node部分：
    for pod in pod_pod:
        child_num = len(pod_pod[pod])
        for child in pod_pod[pod]:
            p_ss[node_list.index(child)][node_list.index(pod)] = 1.0 / child_num
            # print(1.0 / child_num)
    # matrix方阵的右上方node*request部分
    for trace_id in pod_trace:
        child_num = len(pod_trace[trace_id])
        for child in pod_trace[trace_id]:
            p_sr[node_list.index(child)][trace_list.index(trace_id)] \
                = 1.0 / child_num
    # matrix方阵的左下方request*node部分
    for pod in trace_pod:
        child_num = len(trace_pod[pod])
        for child in trace_pod[pod]:
            p_rs[trace_list.index(child)][node_list.index(pod)] \
                = 1.0 / child_num
    # trace 种类统计
    kind_list = np.zeros(len(trace_list))
    p_srt = p_sr.T
    for i in range(len(trace_list)):
        index_list = [i]
        if kind_list[i] != 0:
            continue
        n = 0
        for j in range(i, len(trace_list)):
            if (p_srt[i] == p_srt[j]).all():
                index_list.append(j)
                n += 1
        for index in index_list:
            kind_list[index] = n
    num_sum_trace = 0
    kind_sum_trace = 0
    for trace_id in pr_trace:
        num_sum_trace += 1 / kind_list[trace_list.index(trace_id)]
    for trace_id in pr_trace:
        pr[trace_list.index(trace_id)] = 1 / kind_list[trace_list.index(trace_id)] / num_sum_trace
    
    result = pageRank(p_ss, p_sr, p_rs, pr, pod_length, trace_length)
    return result

def pageRank(p_ss, p_sr, p_rs, v, operation_length, trace_length, d=0.85, alpha=0.01):
    service_ranking_vector = np.ones((operation_length, 1)) / float(operation_length + trace_length)
    request_ranking_vector = np.ones((trace_length, 1)) / float(operation_length + trace_length)
    for i in range(25):
        updated_service_ranking_vector = d * (np.dot(p_sr, request_ranking_vector) + alpha * np.dot(p_ss, service_ranking_vector))
        updated_request_ranking_vector = d * np.dot(p_rs, service_ranking_vector) + (1.0 - d) * v
        service_ranking_vector = updated_service_ranking_vector / np.amax(updated_service_ranking_vector)
        request_ranking_vector = updated_request_ranking_vector / np.amax(updated_request_ranking_vector)
    normalized_service_ranking_vector = service_ranking_vector / np.amax(service_ranking_vector)
    return normalized_service_ranking_vector

def get_svc_scores(trace_pod,page_rank_scores):
    svc_scores = {}
    for i in range(len(trace_pod.keys())):
        pod_name = trace_pod.keys()[i]
        svc = pod_name.split("-")[0][:-1]
        if svc not in svc_scores.keys():
            if svc == "fronten":
                svc_scores[svc+"d"] = [page_rank_scores[i][0]]
            else:
                svc_scores[svc] = [page_rank_scores[i][0]]
        else:
            if svc == "fronten":
                svc_scores[svc+"d"].append(page_rank_scores[i][0])
            else:
                svc_scores[svc].append(page_rank_scores[i][0])
    for pod, scores in svc_scores.items():
        average = 0
        for score in scores:
            average = average+score
        average = average/len(scores)
        svc_scores[pod] = average

    return svc_scores
# ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()) 
# print(ts)
def get_pagerank_svc_scores():
    ts = "2021-10-29 13:27:04"
    recorded_traceid = []
    trace_list, span_list = collect_page_rank_trace(ts)
    # print(trace_list)
    pod_pod, pod_trace, trace_pod, pr_trace = get_pagerank_graph(trace_list.keys(),span_list)
    operation_operation, operation_trace, trace_operation, pr_trace = get_pagerank_operation_graph(trace_list.keys(), span_list)

    # print(pr_trace)
    pod_page_rank_scores = trace_pagerank(pod_pod, pod_trace, trace_pod, pr_trace)
    operation_page_rank_scores = trace_pagerank(operation_operation, operation_trace, trace_operation, pr_trace)
    # print("Page rank scores of pod aggregation : ")
    pod_svc_scores = get_svc_scores(trace_pod,pod_page_rank_scores)
    pod_svc_scores = sorted(pod_svc_scores.items(), key=lambda item:item[1],reverse=True)
    svc_scores = {}
    for item in pod_svc_scores:
        svc_scores[item[0]] = item[1]
    return svc_scores
    # print("Page rank scores of opeartions aggregation : ")
    # operation_svc_scores =  get_svc_scores(trace_operation,operation_page_rank_scores)
    # print(sorted(operation_svc_scores.items(), key=lambda item:item[1]))
# def sorted_with_pagerank(to_sort_hypotheses, page_rank_scores):
#     hypotheses_scores = []
#     for sub_hypothesis in to_sort_hypotheses:
#         if len(sub_hypothesis) ==1:
#             pod = sub_hypothesis[0]
#             svc = pod.split("-")[0]
#             if svc != "frontend":
#                 svc = svc[:-1]
#             pod_score = page_rank_scores[svc]
#             hypotheses_scores.append((sub_hypothesis, pod_score))
#         else:
#             sum_score = 0
#             for pod in sub_hypothesis:
#                 svc = pod.split("-")[0]
#                 if svc != "frontend":
#                     svc = svc[:-1]
#                 pod_score = page_rank_scores[svc]
#                 sum_score = sum_score + pod_score
#             hypotheses_scores.append((sub_hypothesis, sum_score/len(sub_hypothesis)))
#     L1 = sorted(hypotheses_scores, key = lambda x:x[0])
#     L2 = sorted(L1, key = lambda x:x[1], reverse = True)
#     sorted_hypotheses = []
#     for item in L2:
#         sorted_hypotheses.append(item[0])
#     return sorted_hypotheses
# page_rank_scores = get_pagerank_svc_scores()
# hypotheses = [['frontend-5f856b99f4-zkt6w'], ["currencyservice2-95878bfcc-vx7nl"] ,['currencyservice1-64cc786bb8-p528p'], ["cartservice2-655dcccf7-pdc2z"], ['cartservice1-d6c65dc54-kjnrg'], ['productcatalogservice1-55fcc699c6-nm27p'], ['adservice1-7bfc6777b5-l8fcw ','adservice2-6978b57b5d-mfrcn']]
# print(sorted_with_pagerank(hypotheses, page_rank_scores))