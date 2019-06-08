# coding=utf-8

import requests
import json
import unicodedata
from subprocess import Popen, PIPE
import time
import networkx as nx
from sys import exit

def getResponse(url,choice):

	response = requests.get(url)

	if(response.ok):
		jData = json.loads(response.content)  #json的string转化为Python的dict
		if(choice=="deviceInfo"):
			deviceInformation(jData)  #device数据转化
		elif(choice=="findSwitchLinks"):
			findSwitchLinks(jData,switch[h2])
		elif(choice=="linkTX"):
			linkTX(jData,portKey)

	else:
		response.raise_for_status()



# Parses JSON Data To Find Switch Connected To H4
#格式转化
def deviceInformation(data):
	global switch     #存储IP的dpid
	global deviceMAC  #存储IP的mac地址 模式为deviceMAC[ip] = mac
	global hostPorts  #存储IP的ip::port

	switchDPID = ""
	for i in data:  # 遍历各个与主机相关的交换机信息 
		if(i['ipv4']): #ipv4不为空
			ip = i['ipv4'][0].encode('ascii','ignore') #使用ASCII编码，遇到错误忽略
			mac = i['mac'][0].encode('ascii','ignore')
			deviceMAC[ip] = mac  #IP的mac地址
			for j in i['attachmentPoint']:  #attachment表示与IP主机相连的交换机dpid与端口
				for key in j: 
					temp = key.encode('ascii','ignore')
					if(temp=="switchDPID"):
						switchDPID = j[key].encode('ascii','ignore')
						switch[ip] = switchDPID 
					elif(temp=="port"):
						portNumber = j[key]
						switchShort = switchDPID.split(":")[7]
						hostPorts[ip+ "::" + switchShort] = str(portNumber)   
   

# Finding Switch Links Of Common Switch Of H3, H4

def findSwitchLinks(data,s):
	global switchLinks
	global linkPorts
	global G

	links=[]
	for i in data:
		src = i['src-switch'].encode('ascii','ignore')
		dst = i['dst-switch'].encode('ascii','ignore')

		srcPort = str(i['src-port'])
		dstPort = str(i['dst-port'])

		srcTemp = src.split(":")[7]
		dstTemp = dst.split(":")[7]

		G.add_edge(int(srcTemp,16), int(dstTemp,16))

		tempSrcToDst = srcTemp + "::" + dstTemp
		tempDstToSrc = dstTemp + "::" + srcTemp

		portSrcToDst = str(srcPort) + "::" + str(dstPort)
		portDstToSrc = str(dstPort) + "::" + str(srcPort)

		linkPorts[tempSrcToDst] = portSrcToDst
		linkPorts[tempDstToSrc] = portDstToSrc

		if (src==s):
			links.append(dst)
		elif (dst==s):
			links.append(src)
		else:
			continue

	switchID = s.split(":")[7]
	switchLinks[switchID]=links         

# Finds The Path To A Switch

def findSwitchRoute():
	pathKey = ""
	nodeList = []
	src = int(switch[h1].split(":",7)[7],16)
	dst = int(switch[h5].split(":",7)[7],16)
	print src
	print dst
	for currentPath in nx.all_shortest_paths(G, source=src, target=dst, weight=None):  #得到一些最短路
		for node in currentPath:  #最短路中一个节点

			tmp = ""
			if node < 17:
				pathKey = pathKey + "0" + str(hex(node)).split("x",1)[1] + "::"
				tmp = "00:00:00:00:00:00:00:0" + str(hex(node)).split("x",1)[1]  #hex代表16进制 tmp代表了一个交换机
			else:
				pathKey = pathKey + str(hex(node)).split("x",1)[1] + "::"
				tmp = "00:00:00:00:00:00:00:" + str(hex(node)).split("x",1)[1]
			nodeList.append(tmp)  #在节点中添加一个交换机

		pathKey=pathKey.strip("::")  #string.strip("#") 除去string首尾的#字符 pathkey变为交换机的末节点
		path[pathKey] = nodeList  #path 代表交换机路径  以末节点代表dpid组成字典
		pathKey = ""
		nodeList = []

	print path


# Computes Link TX

def linkTX(data,key):
	global cost
	port = linkPorts[key]
	port = port.split("::")[0]
	for i in data:
		if i['port']==port:
			cost = cost + (int)(i['bits-per-second-tx'])




# Method To Compute Link Cost
#计算负载的函数
def getLinkCost():
	global portKey
	global cost

	for key in path:  #path中的节点 一个key {0x：dpid}
		start = switch[h1]
		src = switch[h1]
		srcShortID = src.split(":")[7]
		mid = path[key][1].split(":")[7]
		for link in path[key]:
			temp = link.split(":")[7]

			if srcShortID==temp:
				continue
			else:
				portKey = srcShortID + "::" + temp
				stats = "http://localhost:8080/wm/statistics/bandwidth/" + src + "/0/json"
				getResponse(stats,"linkTX")
				srcShortID = temp
				src = link
		portKey = start.split(":")[7] + "::" + mid + "::" + switch[h5].split(":")[7]
		finalLinkTX[portKey] = cost
		cost = 0
		portKey = ""


def systemCommand(cmd):
	terminalProcess = Popen(cmd, stdout=PIPE, stderr=PIPE, shell=True)
	terminalOutput, stderr = terminalProcess.communicate()
	print "\n***", terminalOutput, "\n"



def flowRule(currentNode, flowCount, inPort, outPort, staticFlowURL):
	flow = {
		'switch':"00:00:00:00:00:00:00:" + currentNode,
	    "name":"flow" + str(flowCount),
	    "cookie":"0",
	    "priority":"32768",
	    "in_port":inPort,
		"eth_type": "0x0800",
		"ipv4_src": h1,
		"ipv4_dst": h5,
		"eth_src": deviceMAC[h1],
		"eth_dst": deviceMAC[h5],
	    "active":"true",
	    "actions":"output=" + outPort
	}

	jsonData = json.dumps(flow)

	cmd = "curl -X POST -d \'" + jsonData + "\' " + staticFlowURL

	systemCommand(cmd)

	flowCount = flowCount + 1

	flow = {
		'switch':"00:00:00:00:00:00:00:" + currentNode,
	    "name":"flow" + str(flowCount),
	    "cookie":"0",
	    "priority":"32768",
	    "in_port":outPort,
		"eth_type": "0x0800",
		"ipv4_src": h5,
		"ipv4_dst": h1,
		"eth_src": deviceMAC[h5],
		"eth_dst": deviceMAC[h1],
	    "active":"true",
	    "actions":"output=" + inPort
	}

	jsonData = json.dumps(flow)

	cmd = "curl -X POST -d \'" + jsonData + "\' " + staticFlowURL

	systemCommand(cmd)
    

def addFlow():
	print "KAAM CHALU HAI"

	# Deleting Flow
	#cmd = "curl -X DELETE -d \'{\"name\":\"flow1\"}\' http://127.0.0.1:8080/wm/staticflowpusher/json"
	#systemCommand(cmd)

	#cmd = "curl -X DELETE -d \'{\"name\":\"flow2\"}\' http://127.0.0.1:8080/wm/staticflowpusher/json"
	#systemCommand(cmd)

	flowCount = 1
	staticFlowURL = "http://127.0.0.1:8080/wm/staticflowpusher/json"

	shortestPath = min(finalLinkTX, key=finalLinkTX.get)
	print "\n\nShortest Path: ",shortestPath


	currentNode = shortestPath.split("::",2)[0]
	nextNode = shortestPath.split("::")[1]

	# Port Computation

	port = linkPorts[currentNode+"::"+nextNode]
	outPort = port.split("::")[0]
	inPort = hostPorts[h2+"::"+switch[h2].split(":")[7]]

	flowRule(currentNode,flowCount,inPort,outPort,staticFlowURL)

	flowCount = flowCount + 2


	bestPath = path[shortestPath]
	previousNode = currentNode

	for currentNode in range(0,len(bestPath)):
		if previousNode == bestPath[currentNode].split(":")[7]:
			continue
		else:
			port = linkPorts[bestPath[currentNode].split(":")[7]+"::"+previousNode]
			inPort = port.split("::")[0]
			outPort = ""
			if(currentNode+1<len(bestPath) and bestPath[currentNode]==bestPath[currentNode+1]):
				currentNode = currentNode + 1
				continue
			elif(currentNode+1<len(bestPath)):
				port = linkPorts[bestPath[currentNode].split(":")[7]+"::"+bestPath[currentNode+1].split(":")[7]]
				outPort = port.split("::")[0]
			elif(bestPath[currentNode]==bestPath[-1]):
				outPort = str(hostPorts[h1+"::"+switch[h1].split(":")[7]])

			flowRule(bestPath[currentNode].split(":")[7],flowCount,str(inPort),str(outPort),staticFlowURL)
			flowCount = flowCount + 2
			previousNode = bestPath[currentNode].split(":")[7]

# Method To Perform Load Balancing
def loadbalance():
	linkURL = "http://localhost:8080/wm/topology/links/json"
	getResponse(linkURL,"findSwitchLinks")  #得到节点的链接

	findSwitchRoute()
	getLinkCost()
	addFlow()

					

# Main

# Stores h1-h5 
global h1,h2,h3,h4,h5

h1 = "10.0.0.1"
h2 = "10.0.0.2"
h3 = "10.0.0.3"
h3 = "10.0.0.4"
h3 = "10.0.0.5"




while True:

	# Stores Info About Switch
	switch = {} #字典

	# Mac of H3 And H4
	deviceMAC = {}

	# Stores Host Switch Ports
	hostPorts = {}

	# Stores Switch To Switch Path
	path = {}

	# Switch Links

	switchLinks = {}

	# Stores Link Ports
	linkPorts = {}

	# Stores Final Link Rates
	finalLinkTX = {}

	# Store Port Key For Finding Link Rates
	portKey = ""

	# Stores Link Cost
	# Graph
	G = nx.Graph()  #创建一个没有节点和边的空图
	cost = 0


	#打开数据获取的功能
	enableStats = "http://localhost:8080/wm/statistics/config/enable/json"  
	requests.put(enableStats)

	# 与主机相连的交换机信息
	deviceInfo = "http://localhost:8080/wm/device/"
	getResponse(deviceInfo,"deviceInfo")

	# Load Balancing
	loadbalance()


	time.sleep(60)


