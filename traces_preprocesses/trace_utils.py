# -*- coding: utf-8 -*-
import re
import json
import time
import requests
import numpy as np
from copy import deepcopy
import warnings
import paramiko
import pickle
import os
# from traces_preprocess import query
# import query
import hashlib

warnings.filterwarnings("ignore")
root_index = 'root'
PRIME_NUMBER = 53
operation_template = {
    "duration": [],
    "operationName": "",
    "podName": "",
    "occurrence": 0,
    "children": []
}
path_fn = 'path_list.pkl'
svc_dependencies = 'svc_pod_link.pkl'
svc_pod_link = dict()

"""
    Weave the trace through traversing the span list. We define path as request path. Traces belong to the same path as 
    their service-level topology are the same.
    At the same time, aggregate all the same path and record all latency and occurrence between two operations. 
    :arg
        span list: the query result of the last minute, which is ordered by traceid and startTime
    :return
        path list: the weighted path
        trace list (to del): the whole trace list during the duration 
"""

'''
a trace is a collections of operations that represents a unique transaction handled by an application and its 
constituent services. 
A span represents a single operation within a trace
'''


# return a list which contains all different operations in a span list
def get_operation_list(span_list):
    operation_list = []

    for doc in span_list:
        doc = doc['_source']

        # hipstershop.CurrencyService/Convert 使用 / 划分取最后一个词为operation_name
        operation_name = doc['operationName']
        operation_name = operation_name.split('/')[-1]

        # Currencyservice_Convert
        operation = doc['process']['serviceName'] + '_' + operation_name
        if operation not in operation_list:
            operation_list.append(operation)

    return operation_list


def path_aggregate(span_list, path_list):
    if len(span_list) == 0:
        print("Error. Span_list is empty.")
    last_traceid = span_list[0]['_source']['traceID']
    trace = {}
    trace_list = {}
    normal_trace = True
    # print(span_list)
    temp_docs = []  # 记录了normal_trace为false的span
    for doc in span_list:
        doc = doc['_source']
        current_traceid = doc['traceID']
        # print(current_traceid)
        # import pdb;pdb.set_trace()
        if last_traceid == current_traceid: 
            # If the last traceID is equal to current traceID, they belong to the same trace
            normal_trace = get_span_element(doc, trace, normal_trace)
            if not normal_trace:
                temp_docs.append(doc)
                normal_trace = True
            # print(normal_trace)
        elif last_traceid != current_traceid and len(trace) > 0:
            # import pdb; pdb.set_trace()
            # if the last traceID is different from current traceID, and the last trace is not empty
            for temp_doc in temp_docs:
                normal_trace = get_span_element(temp_doc, trace, normal_trace)
            temp_docs = []
            if check_dirty_data(trace, normal_trace):
                if 'root_span' not in trace:
                    trace['root_span'] = find_root_span(list(trace.keys())[0], trace)
                trace_list[last_traceid] = trace
                # using hashcode to make tree comparison efficiently and then aggregate paths
                # print(trace)
                add_to_path(trace, path_list, last_traceid)
                # print(current_traceid, last_traceid, path_list)
            # initiate a new trace
            normal_trace = True
            last_traceid = current_traceid
            trace = {}
            normal_trace = get_span_element(doc, trace, normal_trace)
            if normal_trace == False:
                temp_docs.append(doc)
                normal_trace = True

    # process the final trace
    # import pdb; pdb.set_trace()
    if len(trace) > 1:
        for temp_doc in temp_docs:
            normal_trace = get_span_element(temp_doc, trace, normal_trace)
        temp_docs = []
        # import pdb; pdb.set_trace()
        if check_dirty_data(trace, normal_trace):
            if 'root_span' not in trace:
                trace['root_span'] = find_root_span(list(trace.keys())[0], trace)
            trace_list[last_traceid] = trace
            add_to_path(trace, path_list, current_traceid)
    return path_list, trace_list


'''
    Find the root spanid of given trace
    :arg
        spanid: from the node labeling spanid
        trace: trace data
    :return 
        root_span: root span id
'''


def find_root_span(spanid, trace): 
    if trace[spanid]['parent'] in trace:
        return find_root_span(trace[spanid]['parent'], trace)
    else:
        return spanid


'''
    Find the same path in path list
    :arg
        hashcode: hashcode of this trace path
        path_list: the list containing all paths
    :return
        NULL
'''
def add_to_path(trace, path_list,trace_ID):
    hashcode = get_trace_hash(trace)
    # if path already exists the trace template, just add the operation duration
    if hashcode in path_list:
        path = path_list[hashcode]
        for spanid, item in trace.items():
            if spanid != 'root_span':
                path[item['operation']]['duration'].append(item['duration'])
        path_list[hashcode] = path
    # if path does not exist, then initiate a new path and append to path_list
    else:
        path = init_path(trace)
        path_list[trace_ID] = path


'''
    Init a new path
    :arg 
        trace: trace data
    :return 
        path: a path instance of this trace
'''


def init_path(trace):
    root_spanid = trace['root_span']
    root_span = trace[root_spanid]
    path = dict()
    # import pdb; pdb.set_trace()
    for spanid, span in trace.items():
        if spanid is 'root_span':
            root_spanid = trace['root_span']
        else:
            # record the dependency between service and podname 
            # refresh_svc_pod(span)
            operation_name = span['operation']
            if operation_name in path:
                path[operation_name]['duration'].append(span['duration'])
                path[operation_name]['occurrence'] += 1
                path[operation_name]['operationName'] = operation_name
            else:
                operation = deepcopy(operation_template)
                operation['duration'].append(span['duration'])
                operation['operationName'] = operation_name
                operation['podName'] = span['podName']
                operation['occurrence'] = 1
                for child in span['childSpans']:
                    operation['children'].append(trace[child]['operation'])
                path[operation_name] = operation
    return path


def refresh_svc_pod(span):
    podname = get_podname(span)
    svc = span['process']['serviceName']
    if podname not in svc_pod_link:
        svc_pod_link[podname] = svc


'''
    Check if there exists dirty data in this trace
    :arg 
        trace
    :return
        is healthy or not
'''


def check_dirty_data(trace, normal_trace):
    if normal_trace is False:
        return False
    for spanid, data in trace.items():
        if spanid == 'root_span':
            continue
        if data['parent'] == root_index and data['duration'] > 1000000:
            print("Filter dirty data because duration > 1000ms.")
            # print(trace)
            return False
        if data['parent'] == "":
            print("Filter dirty data because span has empty parent.")
            # print(trace)
            return False                    
    return True
                       

"""
    Get a simplified copy of span
    :arg 
        doc: the document of span
        trace: the whole list of trace
        normal_trace: record the trace is normal or not
    :return
        a simplified copy of whole span
"""


def get_span_element(doc, trace, normal_trace):
    # import pdb; pdb.set_trace()
    span_simplified = {
        'parent': '',  # parent span
        'podName': '', # podname
        'operation': '',  # current servicename_operation
        'duration': 0,  # duration of current operation
        'childSpans': [] # child spans
    }

    spanid = doc['spanID']
    span_simplified['duration'] = doc['duration']
    span_simplified['podName'] = get_podname(doc)
    operation_name = doc['operationName']
    operation_name = operation_name.split('/')[-1]
    operation_name = doc['process']['serviceName'] + '_' + operation_name
    span_simplified['operation'] = operation_name

    # find parent id
    if is_root_index(doc):
        # import pdb;pdb.set_trace()
        span_simplified['parent'] = root_index
        for tag in doc["tags"]:
            if tag["key"] == "http.target":
                span_simplified["target"] = tag["value"]
            if tag["key"] == "http.method":
                span_simplified["method"] = tag["value"]
        trace['root_span'] = spanid  # 存储trace的根节点(根span)
    else:
        #  如果当前的span不是根节点，且其不存在references（就是在此span之前的operations，我们认为当前的不是normal_trace
        if len(doc['references']) == 0:
            normal_trace = False
            # print("1")
        else:
            parentId = doc['references'][0]['spanID']
            span_simplified['parent'] = parentId
            if parentId in trace:
                # 父节点spanID已存储
                trace[parentId]['childSpans'].append(spanid)
                trace[parentId]['duration'] -= span_simplified['duration']
            else:
                # 父节点应在此前已追踪，不存在则不是normal_trace
                normal_trace = False
                # temp_span[spanid] = span_simplified
                # print("2")
    if normal_trace:
        trace[spanid] = span_simplified
    return normal_trace


def get_podname(span):
    for item in span['process']['tags']:
        if item['key'] == 'name':
            return item['value']
    if 'tags' in span:
        for item in span['tags']:
            if item['key'] == 'name':
                return item['value']


"""
    check if the span is the root index
    :arg 
        doc: the document of span
    :return
        True if the span.kind is server as well as its serviceName is frontend

        tags: [{"key": "span.kind",
            "type": "string",
            "value": "server"}]
"""


def is_root_index(doc):
    for tag in doc['tags']:
        if tag['key'] == "span.kind":
            if tag['value'] != 'server':
                return False
            else:
                break
    if doc['process']['serviceName'] == 'frontend':
        return True
    else:
        return False


'''
    Get the hash code of span
    :arg
        span
    :return
        the hash code of span
'''


def get_span_hash(span, trace, level):
    hashcode = int(hashlib.sha256(span['podName'].encode('utf-8')).hexdigest(), 16) % 10**8 + level * PRIME_NUMBER
    for child in span['childSpans']:
        hashcode += get_span_hash(trace[child], trace, level + 1)
    return hashcode


def get_trace_hash(trace):
    root_span = trace['root_span']
    return get_span_hash(trace[root_span], trace, 1)


def str2f(datetime):
    timeArray = time.strptime(datetime, "%Y-%m-%d %H:%M:%S")
    ts = int(time.mktime(timeArray)) * 1000
    # print(ts)
    return ts
