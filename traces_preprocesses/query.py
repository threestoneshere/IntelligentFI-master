# -*- coding: utf-8 -*-
import re
import json
import time
import requests
import numpy as np
from copy import deepcopy
import warnings
import paramiko

warnings.filterwarnings("ignore")

es_url = 'http://elastic:kOrgK7PIHc46n697bT9z333O@localhost:52625'

'''
  Query all the span of single traceID from  elasticsearch.
  :arg 
      traceid
  :return
   span list of that tracid    
'''

def get_single_trace_span(traceid):
    based_api = es_url + "jaeger-span-*/span/_search?filter_path=hits.hits._source"
    headers = {"Content-Type": "application/json"}
    query_data = {
        "from": 0,
        "size": 5000,
        "query": {
            "bool": {
                "must": [
                    # {"match": {"parentId": traceid}},
                    {"match": {"traceID": traceid}}
                ],
            }
        },
        "sort": {
            "startTime": {
                "order": "asc"
            }
        }
    }

    data = requests.post(based_api, json=query_data, headers=headers).json()
    return data['hits']['hits']


'''
  Query the initial trace data from elasticsearch by scroll(1 min)
  :arg
      date: format 2020-08-14 or 2020-08-*
      start: the timestamp of start time (ms)
      end:  the timestamp of end time (ms)
  :return
      all span between start time and end time except jaeger-query service 
'''


def get_span(start=None, end=None):
    # print('Start: %d, end: %d' % (start, end))
    scroll_api = es_url + "/jaeger-span-*/_search?scroll=1m"
    based_api = es_url + "/_search/scroll?filter_path=hits.hits._source"
    headers = {"Content-Type": "application/json"}

    # 过滤掉 jaeger-query 的 trace
    # 按 traceID 升序排列，按startTime升序排列
    query_data = {
        "size": 10000,
        "query": {
            "bool": {
                "must_not": [
                    {
                        "terms": {
                            "process.serviceName": [
                                "jaeger-query"
                            ]}
                    }
                ],
                "filter": {
                    "range": {
                        "startTimeMillis": {
                            "lte": str(end),
                            "gte": str(start)
                        }
                    }
                }
            }
        },
        "sort": {
            "traceID": {
                "order": "asc"
            },
            "startTime": {
                "order": "asc"
            }
        }
    }
    data = requests.post(scroll_api, json=query_data, headers=headers).json()

    # 如果 query 失败重复query
    for i in range(10):
        if '_scroll_id' not in data:
            print("query error, restart query scroll")
            time.sleep(10)
            data = requests.post(scroll_api, json=query_data, headers=headers).json()
        else:
            break

    scroll_data = {
        "scroll": "1m",
        "scroll": data['_scroll_id']
    }
    span_list = []
    while 'hits' in data and len(data['hits']['hits']) > 0:
        span_list += data['hits']['hits']
        data = requests.post(based_api, json=scroll_data, headers=headers).json()
        # if 'hits' in data:
        #     print(len(data['hits']['hits']), len(span_list))

    # print('\nSpan Length:', len(span_list))
    return span_list
