#import LRT

#def get_available_pipelines():
#    return {LRT.give_name(): LRT}

import LGPPP_LOFAR_pipeline
import UC2_pipeline
 
def get_available_pipelines():
    return {LGPPP_LOFAR_pipeline.give_name(): LGPPP_LOFAR_pipeline,
		UC2_pipeline.give_name(): UC2_pipeline}

