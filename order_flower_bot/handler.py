import logging
import os
import sys

# Must do this first! (insert packages into root)
root = os.environ.get("LAMBDA_TASK_ROOT")
if root:
    packages = os.path.join(root, 'packages')
    logging.info("Inserting {} to path".format(packages))
    sys.path.insert(0, packages)


def index(event, context):
    pass
