  # -*- coding: utf-8 -*
'''
    Collect traces data for one minute before the input timestamp
    args:
        timestamp: timestamp
    return:
        path_list: compressed trace data in operation-grained. It is a dict structure, key is the path hashcode and the value is the dict of the path.
'''
import sys
sys.path.append("..")
from traces_preprocesses.trace_utils import *
from traces_preprocesses.query import *
import time
from datetime import timedelta, datetime


def filter_trace(target, method, path_list, trace_list):
    filter_traceids = []
    for trace_key, trace_value in trace_list.items():
        root_span = trace_value["root_span"]
        trace_target = trace_value[root_span]["target"]
        trace_method = trace_value[root_span]["method"]
        if target == trace_target and method == trace_method:
            filter_traceids.append(trace_key)
        elif target == "/product/" and target == trace_target[:9] and method == trace_method:
            filter_traceids.append(trace_key)
    new_trace_list = {filter_traceid: trace_list[filter_traceid] for filter_traceid in filter_traceids}
    new_path_list = {filter_traceid: path_list[filter_traceid] for filter_traceid in filter_traceids}
    return new_path_list,new_trace_list


def collect_trace(timestamp):
    endTime = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
    startTime = endTime - timedelta(minutes=1)
    startTime = datetime.strftime(startTime,  "%Y-%m-%d %H:%M:%S")
    endTime = datetime.strftime(endTime, "%Y-%m-%d %H:%M:%S")
    path_list = dict()
    # import pdb; pdb.set_trace()
    span_list = get_span(start=str2f(startTime), end=str2f(endTime))
    # print(span_list)
    if len(span_list) > 0:
        path_list, trace_list = path_aggregate(span_list, path_list)
    # print(path_list)
    # print("trace_list: ", trace_list)
        return path_list, trace_list
    else:
        return [], []

def dfs_pod_path(trace, path, sub_path = [],  root_span = u"frontend_Recv.",):
    # import pdb; pdb.set_trace()
    root_span_children = trace[root_span]["children"]
    root_span_pod = trace[root_span]["podName"]
    if root_span_pod.split("_")[0] not in sub_path:
        sub_path = sub_path + [root_span_pod]  # sub_path???????????????podName???list
    # print(root_span, root_span_children)
    if root_span_children == []:
        if sub_path not in path:
            path.append(sub_path)
    for children in root_span_children:
        # print(children)
        dfs_pod_path(trace, path, sub_path, root_span=children)


def extract_pod_path(traces, recorded_traceid):
    svc_paths = []  # ???????????????trace_id???path?????????
    # import pdb; pdb.set_trace()
    for traceid, trace in traces.items():
        if traceid not in recorded_traceid:
            recorded_traceid.append(traceid)
            path = []  # ???????????????trace_id???????????????sub_path?????????
            dfs_pod_path(trace, path)
            svc_paths.append(path)
    return svc_paths


def path_to_cnf(svc_paths):
    cnf_formulas = []
    for path in svc_paths:
        formula = []
        for sub_path in path:
            for item in sub_path:
                if item not in formula:
                    formula.append(item)
        cnf_formulas.append(formula)
    return cnf_formulas

def print_formulas(formulas):
    disjunction_symbol = " ??? "
    conjunction_symbol = " ??? "
    temp_formula = []
    for formula in formulas:
        temp_formula.append("("+ disjunction_symbol.join([str(clause) for clause in formula])+")")
    print(conjunction_symbol.join(temp_formula))


'''
   Query the pagerank graph
   :arg
       trace_list: anormaly_traceid_list or normaly_traceid_list
       span_list:  ???????????????????????? span_list
   
   :return
       operation_operation ??????????????? Call graph
       operation_operation[operation_name] = [operation_name1 , operation_name1 ] 
       operation_trace ??????trace???????????????operation, ????????? coverage graph
       operation_trace[traceid] = [operation_name1 , operation_name2]
       trace_operation ?????? operation?????????trace ?????????, ????????? coverage graph
       trace_operation[operation_name] = [traceid1, traceid2]  
       
       pr_trace: ??????trace id ???????????????operation????????????
       pr_trace[traceid] = [operation_name1 , operation_name2]
'''


def get_pagerank_operation_graph(trace_list, span_list):
    # ????????????????????????
    template = {
        'parent': '',  # parent span
        'operation': '',  # current servicename_operation
    }
    if len(trace_list) > 0:
        traceid = trace_list[0]
    else:
        traceid = span_list[0]
    filter_data = {}
    temp = {}

    def server_client_determined():
        """
        :return span.kind
        tags: [{"key": "span.kind",
            "type": "string",
            "value": "server"}]
        """
        for tag in doc['tags']:
            if tag['key'] == "span.kind":
                return tag['value']

    def get_operation_name():
        """
        ??????pod_name??? tags ???????????????process???tags???
        "process": {"tags": [{"key": "name",
                    "type": "string",
                    "value": "frontend-7dbb469cd9-lkv68"}]}
        "tags" : [{"key" : "name",
              "type" : "string",
              "value" : "adservice-7688bd74f6-7qkvl"}]
        operation = pod_name + operation_name
        :return operation
        """
        pod_name = ""
        for tag in doc['process']['tags']:
            if tag['key'] == "name":
                pod_name = tag['value']
        for tag in doc['tags']:
            if tag['key'] == "name":
                pod_name = tag['value']
        operation = pod_name + "_" + doc['operationName']
        return operation
        # return pod_name
    operation_operation = {}
    operation_trace = {}
    trace_operation = {}
    pr_trace = {}
    for doc in span_list:
        doc = doc['_source']
        operation_name = get_operation_name()
        if doc['traceID'] in trace_list:
            if traceid == doc['traceID']:
                # print(doc,"....")
                # ?????????doc???traceid?????????doc???traceid???????????????trace
                spanid = doc['spanID']
                temp[spanid] = deepcopy(template)
                temp[spanid]['operation'] = get_operation_name()
                if len(doc['references']) > 0:
                    parentId = doc['references'][0]['spanID']
                    temp[spanid]['parent'] = parentId
                if server_client_determined() == 'server' and doc['process']['serviceName'] == "frontend":
                    temp[spanid]['parent'] = root_index
                # print(temp[spanid])
            elif traceid != doc['traceID'] and len(temp) > 0:
                # ???????????????trace???????????????trace?????????1?????????????????????????????????????????????????????????trace??????
                filter_data[traceid] = temp
                traceid = doc['traceID']
                spanid = doc['spanID']
                temp = {}
                temp[spanid] = deepcopy(template)
                temp[spanid]['operation'] = get_operation_name()
                if len(doc['references']) > 0:
                    parentId = doc['references'][0]['spanID']
                    temp[spanid]['parent'] = parentId
                if server_client_determined() == 'server' and doc['process']['serviceName'] == "frontend":
                    temp[spanid]['parent'] = root_index
            # ?????????????????? trace
            if len(temp) > 1:
                filter_data[traceid] = temp
            # operation_trace??????trace???????????????operation
            # trace_operation??????operation?????????trace?????????
            """
            operation_operation ???????????????(??????)
            operation_operation[operation_name] = [operation_name1 , operation_name1 ] 
            operation_trace ??????trace???????????????operation????????????
            operation_trace[traceid] = [operation_name1 , operation_name1]
            trace_operation ?????? operation?????????trace ?????????????????????
            trace_operation[operation_name] = [traceid1, traceid2]
            """
            if operation_name not in operation_operation:
                operation_operation[operation_name] = []
                trace_operation[operation_name] = []
            if doc['traceID'] not in operation_trace:
                operation_trace[doc['traceID']] = []
                pr_trace[doc['traceID']] = []
            pr_trace[doc['traceID']].append(operation_name)
            if operation_name not in operation_trace[doc['traceID']]:
                operation_trace[doc['traceID']].append(operation_name)
            if doc['traceID'] not in trace_operation[operation_name]:
                trace_operation[operation_name].append(doc['traceID'])
    # operation_operation???????????????
    for traceid in filter_data:
        single_trace = filter_data[traceid]
        if traceid in trace_list:
            for spanid in single_trace:
                parent_id = single_trace[spanid]["parent"]
                if parent_id != "":
                    if parent_id != root_index:
                        if single_trace[spanid]["operation"] not in operation_operation[single_trace[parent_id]["operation"]]:
                            operation_operation[single_trace[parent_id]["operation"]].append(single_trace[spanid]["operation"])
    return operation_operation, operation_trace, trace_operation, pr_trace


def get_pagerank_graph(trace_list, span_list):
    template = {
        'parent': '',  # parent span
        'pod': '',  # current servicename_operation
    }
    if len(trace_list) > 0:
        traceid = trace_list[0]
    else:
        traceid = span_list[0]
    filter_data = {}
    temp = {}
    def server_client_determined():
        """
        :return span.kind
        tags: [{"key": "span.kind",
            "type": "string",
            "value": "server"}]
        """
        for tag in doc['tags']:
            if tag['key'] == "span.kind":
                return tag['value']
    def get_pod_name():
        """
        ??????pod_name??? tags ???????????????process???tags???
        "process": {"tags": [{"key": "name",
                    "type": "string",
                    "value": "frontend-7dbb469cd9-lkv68"}]}
        "tags" : [{"key" : "name",
              "type" : "string",
              "value" : "adservice-7688bd74f6-7qkvl"}]
        operation = pod_name + operation_name
        :return operation
        """
        pod_name = ""
        for tag in doc['process']['tags']:
            if tag['key'] == "name":
                pod_name = tag['value']
        for tag in doc['tags']:
            if tag['key'] == "name":
                pod_name = tag['value']
        return pod_name
    pod_pod = {}  # ????????????pod?????????????????????pod???????????????????????????pod??????pod??????(???pod?????????pod????????????????????????)
    pod_trace = {}  # ????????????trace_ID?????????????????????trace_ID???????????????????????????ID???????????????pod_name???set
    trace_pod = {}  # ????????????pod_name?????????????????????pod_name???????????????????????????pod??????????????????trace_ID???set
    pr_trace = {}  # ????????????trace_ID?????????????????????trace_ID???????????????????????????ID???????????????pod_name???list???pod_name??????span_list??????span????????????

    for doc in span_list:
        doc = doc["_source"]
        pod_name = get_pod_name()
        if doc["traceID"] in trace_list:
            if traceid == doc["traceID"]:
                spanid = doc["spanID"]
                temp[spanid] = deepcopy(template)
                temp[spanid]['pod'] = get_pod_name()

                if len(doc['references']) > 0:
                    parentId = doc['references'][0]['spanID']
                    temp[spanid]['parent'] = parentId
                if server_client_determined() == 'server' and doc['process']['serviceName'] == "frontend":
                    temp[spanid]['parent'] = root_index
            elif traceid != doc['traceID'] and len(temp) > 0:
                # ???????????????trace???????????????trace?????????1?????????????????????????????????????????????????????????trace??????
                # print(traceid,doc["traceID"])
                filter_data[traceid] = temp
                traceid = doc['traceID']
                spanid = doc['spanID']
                temp = {}
                temp[spanid] = deepcopy(template)
                temp[spanid]['pod'] = get_pod_name()
                if len(doc['references']) > 0:
                    parentId = doc['references'][0]['spanID']
                    temp[spanid]['parent'] = parentId
                if server_client_determined() == 'server' and doc['process']['serviceName'] == "frontend":
                    temp[spanid]['parent'] = root_index
            # ?????????????????? trace
            if len(temp) > 1:
                filter_data[traceid] = temp
            # print(filter_data)
            if pod_name not in pod_pod:
                pod_pod[pod_name] = []
                trace_pod[pod_name] = []
            if doc["traceID"] not in pod_trace:
                pod_trace[doc["traceID"]] = []
                pr_trace[doc["traceID"]] = []
            pr_trace[doc["traceID"]].append(pod_name)

            if pod_name not in pod_trace[doc["traceID"]]:
                pod_trace[doc["traceID"]].append(pod_name)
            if doc["traceID"] not in trace_pod[pod_name]:
                trace_pod[pod_name].append(doc["traceID"])
    for traceid in filter_data:
        single_trace = filter_data[traceid]
        if traceid in trace_list:
            for spanid in single_trace:
                parent_id = single_trace[spanid]["parent"] 
                if parent_id != "":
                    if parent_id != root_index:
                        if single_trace[spanid]["pod"] not in pod_pod[single_trace[parent_id]["pod"]]:
                            if single_trace[spanid]["pod"] != single_trace[parent_id]["pod"]:
                                pod_pod[single_trace[parent_id]["pod"]].append(single_trace[spanid]["pod"])
    return pod_pod, pod_trace, trace_pod, pr_trace
# for span in span_list:
#     print(span["_source"]["traceID"])
# # # print(span_list[0])
# path_list, trace_list = path_aggregate(span_list, path_list)
# print(path_list)
# print(path_list.keys())
# recorded_traceid = []
# # # print(path_list[593410274L].keys())
# paths = extract_pod_path({417741518L:path_list[417741518L]},recorded_traceid)
# print(path_to_cnf(paths))
# print(paths)