# -*- coding: utf-8 -*
import requests
import random
url = "http://localhost:50364"
products = [
    '0PUK6V6EV0',
    '1YMWWN1N4O',
    '2ZYFJ3GM2N',
    '66VCHSJNUP',
    '6E92ZMYYFZ',
    '9SIQT8TOJO',
    'L9ECAV7KIM',
    'LS4PSXUNUM',
    'OLJCESPC7Z']


def index_req():
    r = requests.get(url+"/")
    return r


def setCurrency_req():
    currencies = ["EUR", "USD", "JPY", "CAD"]
    r = requests.post(url+"/setCurrency", {"currency_code": random.choice(currencies)})
    return r


def browseProduct_req():
    r = requests.get(url+"/product/"+random.choice(products))
    return r


def viewCart_req():
    r = requests.get(url+"/cart")
    return r


def addToCart_req():
    product = random.choice(products)
    r1 = requests.get(url+"/product/" + product)
    if r1.status_code == 200:
        r2 = requests.post(url+"/cart", {
            'product_id': product,
            'quantity': random.choice([1,2,3,4,5,10])})
        return r2
    return r1


def checkout_req():
    r1 = addToCart_req()
    if r1.status_code == 200:
        r2 = requests.post(url+"/cart/checkout", {
            'email': 'someone@example.com',
            'street_address': '1600 Amphitheatre Parkway',
            'zip_code': '94043',
            'city': 'Mountain View',
            'state': 'CA',
            'country': 'United States',
            'credit_card_number': '4432-8015-6152-0454',
            'credit_card_expiration_month': '1',
            'credit_card_expiration_year': '2039',
            'credit_card_cvv': '672',
        })
        return r2
    return r1

# def test_case(test_case_name = "index"):
#     if test_case_name == "index":
#         return "/", "GET"
#     # if test_case_name == "setCurrency":#两个请求，产生两条trace
#     #     return setCurrency_req()
#     if test_case_name == "browseProduct":
#         return "/product/","GET"
#     if test_case_name == "viewCart":
#         return "/cart", "GET"
#     if test_case_name == "addToCart":#两个请求，产生两条trace
#         return "/cart", "POST"
#     if test_case_name == "checkout":
#         return "/cart/checkout", "POST"

def test_case(req_name = "index"):
    if req_name == "index":
        return index_req()
    if req_name == "setCurrency":  # 两个请求，产生两条trace
        return setCurrency_req()
    if req_name == "browseProduct":
        return browseProduct_req()
    if req_name == "viewCart":
        return viewCart_req()
    if req_name == "addToCart":  # 两个请求，产生两条trace
        return addToCart_req()
    if req_name == "checkout":
        return checkout_req()

# print(index_req(url).status_code)
# print(setCurrency_req(url).status_code)
# print(addToCart_req(url))