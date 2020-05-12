#import LRT

#def get_available_pipelines():
#    return {LRT.give_name(): LRT}

import UC2_pipeline
import LOFAR_IEE_pipeline
 
def get_available_pipelines():
    return {UC2_pipeline.give_name(): UC2_pipeline,
		LOFAR_IEE_pipeline.give_name(): LOFAR_IEE_pipeline}

