from django.shortcuts import render
from django.http import JsonResponse, Http404, QueryDict
from rest_framework import generics, permissions
from .serializers import *
from .models import *
from .permissions import IsOwner

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

# This handles the available pipelines
from .pipeline_administrator import get_available_pipelines

from . import views
import json
import requests

from django.conf import settings

from rest_framework.renderers import TemplateHTMLRenderer
from fabric import Connection

# For converting FITS images to JPEG
import matplotlib
matplotlib.use('Agg')
import aplpy

# For benchmarking
import time

import re

# Put this on for authentications
authentication_on = False

class PipelineSchemasView(APIView):
    def get(self, request, format=None):
        response_dict = {}
        for p in get_available_pipelines():
            response_dict.update( get_available_pipelines()[p].give_config() )
        serializer = PipelinesSerializer({"pipelineschemas":response_dict})
        return Response(serializer.data)


####
### Sessions (w/ staging)
class CreateSessionsView(APIView):

    # This function checks if the given pipeline name and config are
    # valid
    def check_pipeline_config(self, pipeline, config):

        if pipeline in get_available_pipelines().keys():
            if set(config.keys()) == set(get_available_pipelines()[pipeline].give_argument_names()):
                return True
            else:
                return False
        else:
            return False

    def get(self, request, format=None):
        sessions = Session.objects.all()
        serializer = SessionSerializer(sessions, many=True)
        return Response(serializer.data)

    """
        Stage target observation
    """
    def stage_observation(self, observation, **kargs):
        webhook = "http://localhost:8000/sessions"
        tarfiles = observation.split("|")
        srmuris = [] #tarfiles[:20] # testing
        for tfile in tarfiles:
            if re.search('SB0[0|1]', tfile):
                srmuris.append(tfile)
        url = '/stage'
        headers = {
            'Content-Type': 'application/json',
        }
    
        data = {
            "id": "staging",
            "cmd": {
                "type": "stage",
                "subtype": "lofar",
                "src": {
                    "type": "srm",
                    "paths": srmuris
                },
                "credentials": {}
            },
#            "webhook": {"method": "post", "url": webhook, "headers": {}},
            "options": {},
        }
    
        #    print(kargs)
        for kw in kargs:
            if kw == "staging":
                url = kargs[kw]["url"] + url
                data["cmd"]["credentials"]["lofarUsername"] = kargs[kw]["login"]
                data["cmd"]["credentials"]["lofarPassword"] = kargs[kw]["pwd"]
        reqData = json.dumps(data)
        print("===REQ URL=", url)
        print("===REQ DATA=", reqData)
        res = requests.post(url, headers=headers, data=reqData)
        print(res)
        res_data = json.loads(res.content.decode("utf8"))
        print("Your staging request ID is ", str(res_data["requestId"]))
        return res_data["requestId"]

            
    def post(self, request, format=None):

        serializer = SessionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            print('===Session data from api.views.py')
            id_session = serializer.data["id"]
            print(id_session)
            current_session = Session.objects.get(pk=id_session)

            pipeline_configured = self.check_pipeline_config(current_session.pipeline, current_session.config)
            if pipeline_configured:

                ## The pipeline is executed here
                pipeline_res = \
                    get_available_pipelines()[current_session.pipeline].run_pipeline(current_session.observation, current_session.observation2, **current_session.config)

#                print(pipeline_res.content) # = b'{"id": "staging", "requestId": 58241}'
#                res_data = json.loads(pipeline_res.content.decode("utf8"))
##                current_session.pipeline_version = get_available_pipelines()[current_session.pipeline].give_version()
#                current_session.stage_reqid = res_data['requestId']
#                current_session.stage2_reqid = self.stage_observation(current_session.observation2, **current_session.config)
                current_session.save()
#                #                res_data = json.loads(current_session.pipeline_response.content.decode("utf8"))
                new_ser = SessionSerializer(current_session)
                return Response(new_ser.data, status=status.HTTP_201_CREATED)
            else:
                current_session.delete()
                return Response("Pipeline unknown or pipeline wrongly configured. Nothing was done", \
                                status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)




#### Staging version
class SessionView(APIView):
    renderer_classes = [TemplateHTMLRenderer]
    template_name = 'api/session_detail.html'

    """
        Get staging status
    """
    def get_staging_state(self, session, reqid):
        staging_state = ""
        url = session.config["staging"]["url"] + '/status'
        headers = {
            'Content-Type': 'application/json'
        }
        #        print('=SessionView::get_object() pp cfg: ', session.config)
        data = {
            "cmd": {
                "requestId": reqid,
                "credentials": {
                    "lofarUsername": session.config["staging"]["login"],
                    "lofarPassword": session.config["staging"]["pwd"]
                }
            }
        }
        print("=SessionView::get_staging_state() req data", data)
        res = requests.post(url, headers=headers, data=json.dumps(data))
        if res.status_code == requests.codes.ok:
            print("=SessionView::get_staging_state() res raw data", res.content)
            res_data = json.loads(res.content.decode("utf8"))
            print("=SessionView::get_staging_state() res json", res_data)
            staging_id = str(reqid)
            if res_data:
                staging_state = res_data[staging_id]["status"]
                print("=SessionView::get_staging_state() staging status: ", staging_state)
        return staging_state


    """
        Retrieve, update or delete a session instance.
    """
    def get_object(self, pk):
        session = None
        try:
            session = Session.objects.get(pk=pk)
        except Session.DoesNotExist:
            raise Http404
        staging_state = self.get_staging_state(session, session.stage_reqid)
        staging2_state = self.get_staging_state(session, session.stage2_reqid)
        if (staging_state == "completed" or not staging_state) and (staging2_state == "completed" or not staging2_state):
            session.staging = "completed"
#            session.status = "Transferring"
#            session.pipeline_response = "StagingDone"
            session.save()
        return session


    """
        Do transfer to HPC when staging completes
    """
    def transfer_data(self, session, isCal=True):
        print("=SessionView::transfer_data() staging complete, start transferring ...")
#        srmuris = ["srm://srm.grid.sara.nl:8443/pnfs/grid.sara.nl/data/lofar/ops/projects/lofarschool/246403/L246403_SAP000_SB000_uv.MS_7d4aa18f.tar"]
        tarfiles = session.observation.split("|") if isCal else session.observation2.split("|")
        srmuris = [] #tarfiles[:20] # testing
        for tfile in tarfiles:
            if re.search('SB0[0|1]', tfile):
                srmuris.append(tfile)

        headers = {
            'Content-Type': 'application/json',
        }
        hpc_cfg = session.config["hpc"]
        url = hpc_cfg["url"] + "/download"
        print("=SessionView::transfer_data() url: ", url)
        data = {
            "id": "das5test",
            "cmd": {
                "src": {
                    "paths": srmuris
                },
                "dest": {
                    "host": hpc_cfg["headnode"],
                    "path": hpc_cfg["path"]
                },
                "credentials": {
                    "certificate": hpc_cfg["srmcert"],
                    "username": hpc_cfg["login"],
                    "password": hpc_cfg["pwd"]
                },
                "options": {
                    "partitions": 2,
                    "parallelism": 2
                }
            }
        }
        print("=SessionView::transfer_data() payload: ", data)
        res = requests.post(url, headers=headers, data=json.dumps(data))
        print("=SessionView::transfer_data() res raw: ", res.content)
        print("=SessionView::transfer_data() res status_code: ", res.status_code)
        if res.status_code == requests.codes.ok or res.status_code == 202:
            print("=SessionView::transfer_data() res raw2: ", res.content)
            res_data = json.loads(res.content.decode("utf8"))
            print("=SessionView::transfer_data() res json: ", res_data)
            if isCal:
                session.transfer_id = res_data['identifier']
            else:
                session.transfer2_id = res_data['identifier']
            session.save()


    """
        Checks whether transfer has completed
    """
    def is_transfer_complete(self, session, tid):
        print("=SessionView::is_transfer_complete() pp_resp: ", tid)
        url = session.config["hpc"]["url"] + "/status/" + str(tid)
        headers = {
            'Content-Type': 'application/json'
        }
        res = requests.get(url, headers=headers)
        print("=SessionView::is_transfer_complete() res raw: ", res.content)
        if res.status_code == requests.codes.ok:
            print("=SessionView::is_transfer_complete() res raw2: ", res.content)
            res_data = json.loads(res.content.decode("utf8"))
            print("=SessionView::is_transfer_complete() res json: ", res_data)
            print("=SessionView::is_transfer_complete() id:", res_data['identifier'], "\tstatus:", res_data['status'])
            if int(tid) == int(res_data['identifier']) and "complete" == res_data['status'].strip():
#                session.status = "TransferDone"
#                session.save()
                return True
        return False

    
    """
        Checks whether all transfers have completed
        """
    def all_transfer_done(self, session):
        print("=SessionView::all_transfer_done()")
        if self.is_transfer_complete(session, session.transfer_id) and self.is_transfer_complete(session, session.transfer2_id):
            session.status = "TransferDone"
            session.save()
            return True
        return False



    """
        Send request to Xenon-flow to start SLURM job(s) on HPC
    """
    def start_computations(self, session):
        url = '/jobs'
        headers = {
            'Content-Type': 'application/json',
        }
        cfg = session.config
        hpc = cfg["hpc"]
        oneTar = session.observation.split("|")[0]
        oneMS = oneTar.split("/")[-1]
        obsid = oneMS.split("_")[0][1:]
        print("===obsid: ", obsid)
        oneTar = session.observation2.split("|")[0]
        oneMS = oneTar.split("/")[-1]
        obsid2 = oneMS.split("_")[0][1:]
        print("===obsid2: ", obsid2)
        data = {
            "input": {
                "calms": obsid,
                "tarms": obsid2,
#                "templatedir": hpc["templatedir"],
                "factordir": hpc["factordir"],
#                "prefactor": hpc["prefactor"],
                "workdir": hpc["workdir"],
                "datadir": hpc["datadir"],
                "container": hpc["container"],
                "binddir": hpc["binddir"]
#                "WMS": hpc["WMS"]
            }
        }
        url = cfg["hpc"]["xenon"] + url
        headers["api-key"] = cfg["hpc"]["apikey"]
        data["name"] = cfg["workflow"]
        data["workflow"] = cfg["cwl"]

        res = requests.post(url, headers=headers, data=json.dumps(data))
        print("===xenon job req res: ", res)
        res_data = json.loads(res.content.decode("utf8"))
    #    print("===xenon job id: ", res_data["id"])
        res_val = res_data["id"]
        return res_val


    """
        Checks whether job has completed successfully
    """
    def is_job_done(self, session):
        print('=SessionView::is_job_done() pp res: ', session.pipeline_response)
        url = 'http://localhost:8443/jobs/' + session.pipeline_response
        cfg = session.config
        headers = {
            'Content-Type': 'application/json',
            'api-key': cfg["hpc"]["apikey"]
        }
        data = {}
        print("SessionView::is_job_done url=", url)
        print("SessionView::is_job_done header=", headers)
        res = requests.get(url, headers=headers, data=json.dumps(data))
        print(res.content)
        if res.content != b'':
            res_data = json.loads(res.content.decode("utf8"))
            session.status = res_data['state']
            print('===session status', session.status)
            print(res_data)
        else:
            session.status == "Success"
#            session.pipeline_response = "JobDone"
        session.save()
        if session.status == "Success":
#            session.save()
            return True
        return False


    """
        Make a series of IEE API calls to start the computations on HPC
    """
    def start_iee_computations(self, session):
        cfg = session.config
        headers = {
#            'Content-Type': 'application/json',
#            'Authorization': 'Bearer {}'.format(cfg["hpc"]["apikey"])
            'Authorization': 'Bearer eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJuYW1lIjoiU291bGV5IE1hZG91Z291IiwiZW1haWwiOiJzLm1hZG91Z291QGVzY2llbmNlY2VudGVyLm5sIiwic3ViIjoiNSIsImlzcyI6IklFRSIsImlhdCI6MTU5NzczMDUyOCwibmJmIjoxNTk3NzMwNTI3LCJleHAiOjE1OTc3MzQxMjh9.6pJ-S2rrWQUKmDmSjatPzYETgCJGw3yjSc4tk7Vkz0tMPn5cWpx0mvePZ4zuWCHFW2jFCdWR7RM5FBtKThqCoA'
        }
        hpc = cfg["hpc"]
        oneTar = session.observation.split("|")[0]
        oneMS = oneTar.split("/")[-1]
        obsid = oneMS.split("_")[0][1:]
        print("===obsid: ", obsid)
        oneTar = session.observation2.split("|")[0]
        oneMS = oneTar.split("/")[-1]
        obsid2 = oneMS.split("_")[0][1:]
        print("===obsid2: ", obsid2)
        data = {
            "steps": [
                      {
                      "step_name": "directory_build_step",
                      "parameters": {}
                      },
                      {
                      "step_name": "staging_in_step",
                      "parameters": {
                        "compute_site_name" : "Cyfronet: Prometheus",
                        "src_path" : "/testing_data_backup"
                        }
                      },
                      {
                      "step_name": "lofar_step",
                      "parameters": {
                        "container_name" : hpc["container"],
                        "container_tag" : "latest",
                        "compute_site_name" : hpc["compute_site"],
                        "nodes" : "1",
                        "cpus" : "24",
                        "partition" : "plgrid",
                        "calms" : obsid,
                        "tarms" : obsid2,
                        "datadir" : hpc["datadir"],
                        "factordir" : hpc["factordir"],
                        "workdir" : hpc["workdir"]
                        }
                      },
                      {
                      "step_name": "staging_out_step",
                      "parameters": {
                        "compute_site_name" : "Cyfronet: Prometheus",
                        "dest_path" : "/LOFAR_results"
                        }
                      },
                      {
                      "step_name": "clean_up_step",
                      "parameters": {}
                      }
                    ]
        }
        url = cfg["hpc"]["serviceurl"]
#        headers["Authorization:"] = " Bearer " + cfg["hpc"]["apikey"]
        print("req data:", data)
        print("req header:", headers)
        res = requests.post(url, headers=headers, data=json.dumps(data))
        ritems = res.text.split()
        print("===IEE job req res: ", ritems[-1])
#        ritems = res.text.split()
#        res_data = json.loads(res.content.decode("utf8"))
    #    print("===xenon job id: ", res_data["id"])
#        res_val = res_data["id"]
        return ritems[-1]


    """
        Checks whether job has completed successfully
    """
    def is_iee_done(self, session):
        print('=SessionView::is_iee_done() pp res: ', session.pipeline_response)
        cfg = session.config
        url = cfg["hpc"]["serviceurl"] + '/' + session.pipeline_response
        headers = {
#            'Content-Type': 'application/json',
#            'Authorization': 'Bearer ' + cfg["hpc"]["apikey"]
#            'Authorization': 'Bearer {}'.format(cfg["hpc"]["apikey"])
            'Authorization': 'Bearer eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJuYW1lIjoiU291bGV5IE1hZG91Z291IiwiZW1haWwiOiJzLm1hZG91Z291QGVzY2llbmNlY2VudGVyLm5sIiwic3ViIjoiNSIsImlzcyI6IklFRSIsImlhdCI6MTU5NzczMDUyOCwibmJmIjoxNTk3NzMwNTI3LCJleHAiOjE1OTc3MzQxMjh9.6pJ-S2rrWQUKmDmSjatPzYETgCJGw3yjSc4tk7Vkz0tMPn5cWpx0mvePZ4zuWCHFW2jFCdWR7RM5FBtKThqCoA'
        }
        data = {}
        print("SessionView::is_job_done url=", url)
        print("SessionView::is_job_done header=", headers)
        res = requests.get(url, headers=headers, data=json.dumps(data))
        print(res.content)
        if res.content != b'':
            res_data = json.loads(res.content.decode("utf8"))
            session.status = res_data['lofar_step']
            print('===session status', session.status)
            print(res_data)
        else:
            session.status == "finished"
#            session.pipeline_response = "JobDone"
        session.save()
        if session.status == "finished":
#            session.save()
            return True
        return False


    """
        Convert fetched FITS images into JPEG for browsing
    """
    def fetch_convert(self, session, base, raw=False):
        fits_base = base + str(session.id) + '.fits'
        local_fits = settings.MEDIA_ROOT + '/' + fits_base
        remote_fits = '/var/scratch/madougou/LOFAR/test/factor/results/fieldmosaic/field/*' + base + '.fits'
        if raw:
            remote_fits = '/var/scratch/madougou/LOFAR/PROCESS/imguncal/' + base + '.fits'
        xenon_cr = 'madougou@fs0.das5.cs.vu.nl'
        reslog = Connection(xenon_cr).get(remote=remote_fits, local=local_fits)
        print("Downloaded {0.local} from {0.remote}".format(reslog))
        fig = aplpy.FITSFigure(local_fits)
        fig.show_colorscale(cmap='gist_heat')
        fig.tick_labels.hide()
        fig.ticks.hide()
        fig.save(local_fits.replace('.fits', '.jpeg'))
        return fits_base.replace('.fits', '.jpeg')


    """
        Fetch results after job has completed successfully
    """
    def postprocess(self, session):
        session.di_fits = settings.MEDIA_URL + self.fetch_convert(session, 'wsclean_image_full-image.correct_mosaic.pbcor')
#        session.rw_fits = settings.MEDIA_URL + self.fetch_convert(session, 'P23-uncal-image', True)
        session.save()


    """
        Handles HTTP GET method
    """
    def get(self, request, pk, format=None):
        session = self.get_object(pk)
        print("SessionView::get() session.staging={0}\t session.status={1}".format(session.staging, session.status))
        if session.staging == "completed" and session.status != "Success":
            if session.status != "Running" and session.status != "Transferring":
                session.status = "Transferring"
                self.transfer_data(session)
                self.transfer_data(session, False)
                session.save()
            elif session.status == "Transferring":
                if self.all_transfer_done(session):
                    if session.pipeline == "UC2FACTOR":
                        session.pipeline_response = self.start_computations(session)
                    else:
                        session.pipeline_response = self.start_iee_computations(session)
                    session.status = "Running"
                    session.save()
            else:
                if session.pipeline == "UC2FACTOR":
                    if self.is_job_done(session):
                        self.postprocess(session)
                else:
                    if self.is_iee_done(session):
                        self.postprocess(session)
##SM: for testing only
#        if session.staging == "completed" and session.status == "Running":
#            if session.pipeline == "UC2FACTOR":
#                session.pipeline_response = self.start_computations(session)
#            else:
#                session.pipeline_response = self.start_iee_computations(session)
#            session.status = "Running"
#            session.save()
        serializer = SessionSerializer(session)
        return Response({'serializer': serializer, 'session': session})


