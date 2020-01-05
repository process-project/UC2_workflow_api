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

#from .consumers import jobState
#import tempfile
#from PIL import Image

from django.conf import settings

from rest_framework.renderers import TemplateHTMLRenderer
from fabric import Connection

# For converting FITS images to JPEG
import matplotlib
matplotlib.use('Agg')
import aplpy
# For benchmarking
import time

# Put this on for authentications
authentication_on = False
initState = ''

class PipelineSchemasView(APIView):
    def get(self, request, format=None):
        response_dict = {}
        for p in get_available_pipelines():
            response_dict.update( get_available_pipelines()[p].give_config() )
        serializer = PipelinesSerializer({"pipelineschemas":response_dict})
        return Response(serializer.data)


class TransferView(APIView):
    def get(self, request, reqid, format=None):
        print("===TransferView::get data=", request.data, "param=", reqid)
        return Response(request.data)
    
    def post(self, request, reqid, format=None):
        print("===TransferView::post data=", request.data, "param=", reqid)
        return Response(request.data)

class StageView(APIView):
    def get(self, request, format=None):
        print("===WebhookView::get data=", request.data)
        return Response(request.data)
    
    def post(self, request, format=None):
        print("===WebhookView::post data=", request.data)
        return Response(request.data)

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
                    get_available_pipelines()[current_session.pipeline].run_pipeline(current_session.observation, **current_session.config)

#                print('===Session data from api.views.py')
                print(pipeline_res.content) # = b'{"id": "staging", "requestId": 58241}'
                res_data = json.loads(pipeline_res.content.decode("utf8"))
#                current_session.stageid = res_data['id']
                current_session.pipeline_version = get_available_pipelines()[current_session.pipeline].give_version()
                current_session.stage_reqid = res_data['requestId']
                #                current_session.status = "started"
                current_session.save()
                #                res_data = json.loads(current_session.pipeline_response.content.decode("utf8"))
                #                global initState
                #                initState = res_data['state']
                #                print('===api.views initState=', initState)
                new_ser = SessionSerializer(current_session)
                return Response(new_ser.data, status=status.HTTP_201_CREATED)
            else:
                current_session.delete()
                return Response("Pipeline unknown or pipeline wrongly configured. Nothing was done", \
                                status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)




##
# Sessions: used to work before staging
#class CreateSessionsView(APIView):
#
#    # This function checks if the given pipeline name and config are
#    # valid
#    def check_pipeline_config(self, pipeline, config):
#
#        if pipeline in get_available_pipelines().keys():
#            if set(config.keys()) == set(get_available_pipelines()[pipeline].give_argument_names()):
#                return True
#            else:
#                return False
#        else:
#            return False
#
#    def get(self, request, format=None):
#        sessions = Session.objects.all()
#        serializer = SessionSerializer(sessions, many=True)
#        return Response(serializer.data)
#
#    def post(self, request, format=None):
#
#        serializer = SessionSerializer(data=request.data)
#        if serializer.is_valid():
#            serializer.save()
#            id_session = serializer.data["id"]
#
#            current_session = Session.objects.get(pk=id_session)
#
#            pipeline_configured = self.check_pipeline_config(current_session.pipeline, current_session.config)
#            if pipeline_configured:
##                for i in range(32): #SM benchmarking
#                ## The pipeline is executed here
#                pipeline_res = \
#                get_available_pipelines()[current_session.pipeline].run_pipeline(current_session.observation, **current_session.config)
##                    time.sleep(1)
#
#                print('===Session data from api.views.py')
#                print(pipeline_res.content) # = b'{"id": "staging", "requestId": 58241}'
#                res_data = json.loads(pipeline_res.content.decode("utf8"))
#                current_session.pipeline_response = res_data['id']
#                current_session.pipeline_version = get_available_pipelines()[current_session.pipeline].give_version()
##                current_session.status = res_data['state']
#                current_session.status = "Staging"
#                current_session.save()
#                new_ser = SessionSerializer(current_session)
#                return Response(new_ser.data, status=status.HTTP_201_CREATED)
#            else:
#                current_session.delete()
#                return Response("Pipeline unknown or pipeline wrongly configured. Nothing was done", \
#                                status=status.HTTP_400_BAD_REQUEST)
#
#        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)




class SessionDetailsView(generics.RetrieveUpdateDestroyAPIView):
    """This handles the http GET, PUT and DELETE requests"""

    queryset = Session.objects.all()
    serializer_class = SessionSerializer
    # if authentication_on:
    #   permission_classes= (permissions.IsAuthenticated, IsOwner)

class SessionDetails(APIView):
    """
        Retrieve, update or delete a session instance.
        """
    def get_object(self, request, pk):
        session = None
        try:
            session = Session.objects.get(pk=pk)
#            return Session.objects.get(pk=pk)
        except Session.DoesNotExist:
            raise Http404
        # Update status from Xenon-flow server
        print('=SessionDetails::get_object() pp res: ', session.pipeline_response)
        url = 'http://localhost:8443/jobs/' + session.pipeline_response
        headers = {
            'Content-Type': 'application/json',
            'api-key': 'in1uP28Y1Et9YGp95VLYzhm5Jgd5M1r0CKI7326RHwbVcHGa'
        }
        data = {}
        res = requests.get(url, headers=headers, data=json.dumps(data))
#        print(res.content)
        res_data = json.loads(res.content.decode("utf8"))
        session.status = res_data['state']
        
#        image_name = settings.MEDIA_ROOT + '/P23wsclean_' + str(session.id) + '.jpg'
#        files = {'di_image': open(image_name, 'rb'),}
#        res = requests.put(request.build_absolute_uri() + 'di_image', files=files) # Method not allowed

#        if session.status == 'Success':
#        with tempfile.NamedTemporaryFile(suffix='.jpg') as fp:
#            image = Image.new('RGB', (100, 200))
#            image.save(fp)
#            fp.seek(0)
##            session.di_image =  list(image.getdata())
#            session.di_image =  fp

        session.save()
        return session


    def get(self, request, pk, format=None):
        session = self.get_object(request, pk)
        serializer = SessionSerializer(session)
        return Response(serializer.data)

#    def put(self, request, pk, format=None):
#        session = self.get_object(pk)
#        serializer = SessionSerializer(session, data=request.data)
#        if serializer.is_valid():
#            serializer.save()
#            return Response(serializer.data)
#        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        session = self.get_object(request, pk)
        session.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

### Old (before staging) working version
#class SessionView(APIView):
#    renderer_classes = [TemplateHTMLRenderer]
#    template_name = 'api/session_detail.html'
#
#    """
#        Retrieve, update or delete a session instance.
#    """
#    def get_object(self, pk):
#        session = None
#        try:
#            session = Session.objects.get(pk=pk)
#        except Session.DoesNotExist:
#            raise Http404
#        # Update status from Xenon-flow server
#        print('=SessionDetails::get_object() pp res: ', session.pipeline_response)
#        url = 'http://localhost:8443/jobs/' + session.pipeline_response
#        headers = {
#            'Content-Type': 'application/json',
#            'api-key': 'in1uP28Y1Et9YGp95VLYzhm5Jgd5M1r0CKI7326RHwbVcHGa'
#        }
#        data = {}
#        res = requests.get(url, headers=headers, data=json.dumps(data))
#        #        print(res.content)
#        res_data = json.loads(res.content.decode("utf8"))
#        session.status = res_data['state']
#        print('===session status', session.status)
#        if session.status == 'Success': # and session.di_fits == '':
#            fits_base = 'P23wsclean' + str(session.id) + '.fits'
#            local_fits = settings.MEDIA_ROOT + '/' + fits_base
#            remote_fits = '/var/scratch/madougou/LOFAR/prefactor_output/P23-wsclean-image.fits'
#            xenon_cr = 'madougou@fs0.das5.cs.vu.nl'
#            reslog = Connection(xenon_cr).get(remote=remote_fits, local=local_fits)
#            print("Downloaded {0.local} from {0.remote}".format(reslog))
#            fig = aplpy.FITSFigure(local_fits)
#            fig.show_colorscale(cmap='gist_heat')
#            fig.tick_labels.hide()
#            fig.ticks.hide()
#            fig.save(local_fits.replace('.fits', '.jpeg'))
#            session.di_fits = settings.MEDIA_URL +fits_base.replace('.fits', '.jpeg')
#            # Same thing for uncalibrated image
#            fits_base = 'P23uncal' + str(session.id) + '.fits'
#            local_fits = settings.MEDIA_ROOT + '/' + fits_base
#            remote_fits = '/var/scratch/madougou/LOFAR/PROCESS/imguncal/P23-uncal-image.fits'
#            xenon_cr = 'madougou@fs0.das5.cs.vu.nl'
#            reslog = Connection(xenon_cr).get(remote=remote_fits, local=local_fits)
#            print("Downloaded {0.local} from {0.remote}".format(reslog))
#            fig = aplpy.FITSFigure(local_fits)
#            fig.show_colorscale(cmap='gist_heat')
#            fig.tick_labels.hide()
#            fig.ticks.hide()
#            fig.save(local_fits.replace('.fits', '.jpeg'))
#            session.rw_fits = settings.MEDIA_URL +fits_base.replace('.fits', '.jpeg')
#
#        session.save()
#        return session
#
#
#    def get(self, request, pk, format=None):
#        session = self.get_object(pk)
#        serializer = SessionSerializer(session)
#        return Response({'serializer': serializer, 'session': session})



#### Staging version
class SessionView(APIView):
    renderer_classes = [TemplateHTMLRenderer]
    template_name = 'api/session_detail.html'

    """
        Get staging status
    """
    def get_staging_state(self, session):
        staging_state = ""
        url = session.config["staging"]["url"] + '/status'
        headers = {
            'Content-Type': 'application/json'
        }
        #        print('=SessionView::get_object() pp cfg: ', session.config)
        data = {
            "cmd": {
                "requestId": session.stage_reqid,
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
            staging_id = str(session.stage_reqid)
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
        staging_state = self.get_staging_state(session)
        if staging_state == "completed" or not staging_state:
            session.staging = "completed"
#            session.status = "Transferring"
#            session.pipeline_response = "StagingDone"
            session.save()
        return session


    """
        Do transfer to HPC when staging completes
    """
    def transfer_data(self, session):
        print("=SessionView::transfer_data() staging complete, start transferring ...")
        webhook = "http://localhost:8000/transfer/" #+ str(session.stage_reqid)
#        webhook = "http://d627e9bd.ngrok.io"
        srmuris = ["srm://srm.grid.sara.nl:8443/pnfs/grid.sara.nl/data/lofar/ops/projects/lofarschool/246403/L246403_SAP000_SB000_uv.MS_7d4aa18f.tar"]
#        tarfiles = session.observation.split("|")
#        srmuris = [ tarfiles[0] ] # testing
        url = 'http://145.100.130.145:32015/execute'
        headers = {
            'Content-Type': 'application/json',
        }
        hpc_cfg = session.config["hpc"]
        data = {
            "id": "transfer",
            "cmd": {
                "type": "copy",
                "subtype": "srm2hpc",
                "src": {
                    "type": "srm",
                    "paths": srmuris
                },
                "dest": {
                    "type": "hpc",
                    "host": hpc_cfg["headnode"],
                    "path": hpc_cfg["path"]
                },
                "credentials": {
                    "srmCertificate": hpc_cfg["srmcert"],
                    "hpcUsername": hpc_cfg["login"],
                    "hpcPassword": hpc_cfg["pwd"]
                }
            },
            "webhook": {
                "method": "post",
                "url": webhook,
                "headers": headers
            },
            "options": {}
        }
        res = requests.post(url, headers=headers, data=json.dumps(data))
        if res.status_code == requests.codes.ok:
            print("=SessionView::transfer_data() res raw: ", res.content)
            res_data = json.loads(res.content.decode("utf8"))
            print("=SessionView::transfer_data() res json: ", res_data)


    """
        Checks whether transfer has completed
    """
    def is_transfer_complete(self, session):
        print("=SessionView::is_transfer_complete() ...")
        url = "http://localhost:8000/transfer/" #+ str(session.stage_reqid)
#        url = "http://d627e9bd.ngrok.io"
        headers = {
            'Content-Type': 'application/json'
        }
        data = {}
        #        print("=SessionView::is_transfer_complete() req data", data)
        res = requests.post(url, headers={}, data=json.dumps(data))
        print("=SessionView::is_transfer_complete(): res raw => ", res.content)
#        if res.content == b'':
#            session.status = "Waiting"
##            session.pipeline_response = "TransferDone"
#            session.save()
#            return True
#        return False
        if res.status_code == requests.codes.ok or res.content == b'':
#            if res.content == b'':
            session.status = "Waiting"
            session.save()
            return True
#        if res.status_code == requests.codes.ok or res.content == b'':
#            if res.content != b'':
#                res_data = json.loads(res.content.decode("utf8"))
#                print("=SessionView::is_transfer_complete(): res json => ", res_data)
#                srmuris = session.observation.split("|")
##            if res_data and set(res_data["surls"]) == set(srmuris):
#                if res_data and res_data["surls"] == srmuris[0]:
#                    session.status = "Waiting"
#                    session.save()
#                    return True
        return False


    """
        Send request to Xenon-flow to start SLURM job(s) on HPC
    """
    def start_computation(self, session):
        url = '/jobs'
        headers = {
            'Content-Type': 'application/json',
        }
        data = {
            "input": {}
        }
        cfg = session.config
        url = cfg["hpc"]["xenon"] + url
        headers["api-key"] = cfg["hpc"]["apikey"]
        data["name"] = cfg["workflow"]
        data["workflow"] = cfg["cwl"]

        res = requests.post(url, headers=headers, data=json.dumps(data))
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
        Convert fetched FITS images into JPEG for browsing
    """
    def fetch_convert(self, session, base, raw=False):
        fits_base = base + str(session.id) + '.fits'
        local_fits = settings.MEDIA_ROOT + '/' + fits_base
        remote_fits = '/var/scratch/madougou/LOFAR/prefactor_output/' + base + '.fits'
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
        session.di_fits = settings.MEDIA_URL + self.fetch_convert(session, 'P23-wsclean-image')
        session.rw_fits = settings.MEDIA_URL + self.fetch_convert(session, 'P23-uncal-image', True)
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
                session.save()
            elif session.status == "Transferring":
                if self.is_transfer_complete(session):
#            if session.status == "Waiting":
                    session.pipeline_response = self.start_computation(session)
                    session.status = "Running"
                    session.save()
            else:
                if self.is_job_done(session):
                    self.postprocess(session)
#            elif self.is_transfer_complete(session):
#                if session.status == "Waiting":
#                    session.pipeline_response = self.start_computation(session)
#                    session.status = "Running"
#                    session.save()
#                elif self.is_job_done(session):
#                    self.postprocess(session)
        serializer = SessionSerializer(session)
        return Response({'serializer': serializer, 'session': session})


