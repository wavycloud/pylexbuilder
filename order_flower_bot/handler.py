import logging
import os
import sys

# Must do this first! (insert packages into root)
root = os.environ.get("LAMBDA_TASK_ROOT")
if root:
    packages = os.path.join(root, 'packages')
    logging.info("Inserting {} to path".format(packages))
    sys.path.insert(0, packages)


import pylexo

def index(event, context):
    event = pylexo.LexInputEvent(event)
    response = pylexo.DelegateIntentOutputResponse()
    response.update_from_input(event)
    return response.to_dict()
