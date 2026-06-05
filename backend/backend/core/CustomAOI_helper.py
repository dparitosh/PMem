
############### This file is a helper file to use AOI wrapper. Please don't edit or modify this code.
# Author : Naynesh Shah (185021)
# Copyright: Tata Consulancy Services Ltd
#############

import importlib.util
import sys

def InitAOI(callerName, uid, pwd, llmModel, deploymentName, embModel, embDeploymentName):
    """Initialize AOI and return a secure LLM wrapper object."""
    # Path to the compiled .pyc file
    version= f"{sys.version_info.major}{sys.version_info.minor}"
    if version == "312":
       compiled_module_path = 'lib/CustomAOI.cpython-312.pyc'
    elif version == "313":
        compiled_module_path = 'lib/CustomAOI.cpython-313.pyc'
    else:
        compiled_module_path = 'lib/CustomAOI.cpython-311.pyc'


    # Load the compiled module
    spec = importlib.util.spec_from_file_location("CustomAOI.py", compiled_module_path)
    your_script = importlib.util.module_from_spec(spec)
    sys.modules["CustomAOI.py"] = your_script
    spec.loader.exec_module(your_script)

    # Now you can use the classes and functions from your_script
    obj = your_script
    # Call InitOpenAI and return the secure wrapper
    secure_wrapper = obj.InitOpenAI(callerName, uid, pwd, llmModel, deploymentName, embModel, embDeploymentName)
    return secure_wrapper
