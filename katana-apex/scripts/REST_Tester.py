#!/usr/bin/env python
# encoding: utf-8
import json
import time
import requests

from flask import Flask
from flask import request
from flask import jsonify

app = Flask(__name__)
@app.route('/')
def index():
    time.sleep(5)
    return json.dumps({
                        "nameSpace": "apex.event.context",
                        "name": "Context_Trigger",
                        "version": "0.0.1",
                        "source": "External",
                        "target": "APEX",
                        "report": "This is a Context Event"
                        }
)
    
@app.route('/api/slice/1234', methods=['PUT'])
def testStateOne():
    time.sleep(5)
    print("State One has been Triggered")
    return json.dumps({"response" : "State One success"})

@app.route('/api/slice/1234/restart', methods=['POST'])
def testStateTwo():
    time.sleep(5)
    print("State Two has been Triggered")
    return json.dumps({"response" : "State Two success"})
    
@app.route('/api/slice/1234', methods=['POST'])
def testStateThree():
    time.sleep(5)
    print("State Three has been Triggered")
    return json.dumps({"response" : "State Three success"})
  
@app.route('/RESTIssuer', methods=['GET', 'POST', 'PUT', 'DELETE']) 
def RESTIssuer():
    message = request.get_json()
    
    path = "http://" + message["path"]
    method = message["method"]
    body = message["body"]
    
    print("Path = " , path)
    print("Method = " , method)
    print("Body = " , body)
    headers = {'Content-Type': 'application/json'}
    
    if(method == "get"):
        response = requests.get(path, data=json.dumps(body))
        print("GET Called")
    if(method == "post"):
        response = requests.post(path, data=json.dumps(body))
        print("POST Called")
    if(method == "put"):
        response = requests.put(path, body)
        print("PUT Called")
    if(method == "delete"):
        response = requests.post(path)
        print("DELETE Called")

    print("Response = " , response)
    print("Response = " , response.text)

    return 'POST RECEIVED'

app.run(debug=True,host="0.0.0.0")
