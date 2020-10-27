# UC2 LOFAR workflow REST API

This project has been forked from [ESOC](https://github.com/EOSC-LOFAR/lofar_workflow_api).

This is an experiment to see if we can make the LOFAR data more accessible.
This is a django REST api using the django rest_framework. 

## Get it working

* Download this repo
* Create a venv in which you want to do your things (using python3) or use conda
* Install django (e.g. pip install django)
* Install the rest_framework (e.g. pip install djangorestframework)
* Install all the pipelines (as of 27OCT20 this is: https://github.com/process-project/UC2_pipeline and https://github.com/process-project/LOFAR_IEE_pipeline)
* Navigate to the folder containing the manage.py
* Start your local host: `python3 manage.py runserver`
* You can now send http requests to the localhost:8000. For example in your browser: `localhost:8000/sessions/`

# Install

Requirements:
- git
- pipenv, https://docs.pipenv.org/

Run the following commands to install
```
git clone https://github.com/process-project/UC2_workflow_api.git
cd UC2_workflow_api
pipenv install
pipenv shell
cd lofar_workflow_api/
```

# Run

Start web service with following command:
```
python3 manage.py runserver
```

Goto http://localhost:8000/sessions

## Follow an example

Check out the jupyter notebook: example_for_lofar_pilot_REST_api.ipynb. 

## Current models in the api

* Session: a session that will run a pipeline on an observation
* pipelineschemas: this gives you a list with implemented pipelines and configuration schemas.
* A post of a session using the request package could look like this:
```python
	data = {
			"email": "jdoe@process.eu",
			"description": "Add your description to figure out later what this is.",
			"pipeline" : "UC2_pipeline",
			"config": {
                "staging": {"url": "some_url", "login": "jdoe", "pwd": "jdoepass"},                          
                "hpc": {"headnode": "fs0", "path": "some_path", "url": "some_url"}
            },
			"cwl": "uc2.cwl",
        }
    
	response = s.post('http://localhost:8000/sessions/', data=data)
```
* You can do a get to pipelineschemas to get a json with pipelines and their schemas like this: 
```python
	response = s.get('http://localhost:8000/pipelineschemas/')
	response_data = response.json()
	pp.pprint(response_data)

```


## Adding your own pipeline

Please follow the intructions at the pipeline template python package: https://github.com/EOSC-LOFAR/LOFAR_pipeline_template
