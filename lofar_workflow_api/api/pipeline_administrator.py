#import LRT

#def get_available_pipelines():
#    return {LRT.give_name(): LRT}

import LGPPP_LOFAR_pipeline
import PREFACTOR_LOFAR_pipeline
 
def get_available_pipelines():
    return {LGPPP_LOFAR_pipeline.give_name(): LGPPP_LOFAR_pipeline,
		PREFACTOR_LOFAR_pipeline.give_name(): PREFACTOR_LOFAR_pipeline}

