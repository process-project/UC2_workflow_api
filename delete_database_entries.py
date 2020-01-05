import requests
import lxml.html
import pprint

pp = pprint.PrettyPrinter(indent=4)


def delete_models(name):
	print("Deleting: "+name)
	ids = []
	with requests.Session() as s:
		response = s.get('http://localhost:8000/'+name+'/')
		for obs in response.json():
			ids.append(obs["id"])

	for i_id in ids:
		print(i_id)
		with requests.Session() as s:
			response = s.delete('http://localhost:8000/'+name+'/'+str(i_id)+'/', data={})

