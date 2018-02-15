import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from pprint import pformat

import boto3
from troposphere import Join, Ref, AWS_REGION, AWS_ACCOUNT_ID


def get_kwargs(checksum):
    kwargs = {}
    if checksum:
        kwargs['checksum'] = checksum

    return kwargs


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
s3 = boto3.client('s3')
""" :type : pyboto3.s3"""
cloudformation = boto3.client('cloudformation')
""" :type : pyboto3.cloudformation"""


def makedirs(path):
    if not os.path.exists(path):
        os.makedirs(path)


def create_api_endpoint_url(rest_api, stage_name):
    """
    :type rest_api: str
    :type stage_name: str
    :return: Join
    """
    return Join("", ["https://", Ref(rest_api), ".execute-api.", Ref(AWS_REGION), ".amazonaws.com/",
                     stage_name])


def hashfile(path):
    import base64
    base64.b64encode(open(path, 'rb').read())
    sha256 = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            data = f.read()
            if not data:
                break
            sha256.update(data)
    return base64.b64encode(sha256.digest())


def normalize_arcname(arcname):
    arcname = os.path.normpath(os.path.splitdrive(arcname)[1])
    while arcname[0] in (os.sep, os.altsep):
        arcname = arcname[1:]
    return arcname


def zipdir(directory_path):
    tempdir = tempfile.gettempdir()
    file_name = '{}.zip'.format(os.path.basename(directory_path))
    dist_file_path = os.path.join(tempdir, file_name)
    logger.debug("zipping {} to {}".format(directory_path, dist_file_path))
    with zipfile.ZipFile(dist_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # ziph is zipfile handle
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                filepath = os.path.join(root, file)
                filepath_in_zip = normalize_arcname(os.path.join(root.replace(directory_path, ''), file))
                info = zipfile.ZipInfo(filepath_in_zip)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 0
                with open(filepath, 'rb') as fp_byte:
                    zipf.writestr(info, fp_byte.read())
                    # logger.debug("writing {} as {}".format(filepath, filepath_in_zip))
                    # zipf.write(filepath, filepath_in_zip)
        return dist_file_path


def object_exists_in_s3(bucket, key):
    s3 = boto3.resource('s3')
    import botocore.exceptions
    try:
        s3.Object(bucket, key).load()
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == "404":
            return False
        else:
            raise
    else:
        return True


def zipdir_and_upload_to_s3(directory_path, bucket_name):
    import base64
    zip_filepath = zipdir(directory_path)
    sha256 = hashfile(zip_filepath)
    dir_name = os.path.basename(directory_path)
    s3_filename = '{}_{}.zip'.format(dir_name, base64.urlsafe_b64encode(sha256))
    zip_dirpath = os.path.dirname(zip_filepath)
    zip_filepath_sha256 = os.path.join(zip_dirpath, s3_filename)

    if object_exists_in_s3(bucket_name, s3_filename):
        logging.info(
            "Skipping upload '{}' because file already exists in s3 bucket '{}'".format(s3_filename, bucket_name))
        return s3_filename, sha256
    else:
        import shutil
        shutil.move(zip_filepath, zip_filepath_sha256)
        logger.info("Uploading '{}' to S3 Bucket '{}' as {}".format(zip_filepath_sha256, bucket_name, s3_filename))
        # noinspection PyArgumentList
        s3.upload_file(zip_filepath_sha256, bucket_name, s3_filename)
        logger.debug('sha256 of {} is {}'.format(zip_filepath_sha256, sha256))
        logger.debug('S3 key of {} is {}'.format(zip_filepath_sha256, s3_filename))
        return s3_filename, sha256


def get_bucket_keys_list(bucket_name):
    response = s3.list_objects(Bucket=bucket_name)
    return [val.get('Key') for val in response.get('Contents', [])]


def zip_file(file_path):
    file_name = os.path.basename(file_path)
    tempdir = tempfile.gettempdir()
    temp_zip_path = os.path.join(tempdir, '{}.zip'.format(file_name))
    logger.debug("Zipping {} into {} ".format(file_path, temp_zip_path))
    zipf = zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED)
    zipf.write(file_path, os.path.basename(file_path))
    zipf.close()
    return temp_zip_path


def zip_and_upload_file_to(bucket_name, file_path):
    file_name = os.path.basename(file_path)
    temp_zip_path = zip_file(file_path)
    sha256 = hashfile(temp_zip_path)
    logger.debug('sha256 of {} is {}'.format(temp_zip_path, sha256))
    s3_file_name = '{}_{}.zip'.format(file_name, sha256)
    # noinspection PyArgumentList
    s3.upload_file(temp_zip_path, bucket_name, s3_file_name)
    return s3_file_name, sha256


def run_once(function):
    from functools import wraps
    cache = {}

    @wraps(function)
    def wrapper(*args, **kwargs):
        key = '{}-{}-{}'.format(id(function), str(args), str(kwargs))
        try:
            val = cache[key]
            if val == 'EXECUTING':
                raise Exception("Infinite loop might happen")
            return val
        except KeyError as e:
            cache[key] = 'EXECUTING'
            ret_val = function(*args, **kwargs)
            cache[key] = ret_val
            return ret_val

    return wrapper


def get_stacks_by(var='StackName'):
    StackStatusFilter = [
        'CREATE_IN_PROGRESS', 'CREATE_FAILED', 'CREATE_COMPLETE', 'ROLLBACK_IN_PROGRESS', 'ROLLBACK_FAILED',
        'ROLLBACK_COMPLETE', 'DELETE_IN_PROGRESS', 'DELETE_FAILED', 'DELETE_COMPLETE', 'UPDATE_IN_PROGRESS',
        'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS', 'UPDATE_COMPLETE', 'UPDATE_ROLLBACK_IN_PROGRESS',
        'UPDATE_ROLLBACK_FAILED', 'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS', 'UPDATE_ROLLBACK_COMPLETE',
    ]
    StackStatusFilter.remove('DELETE_COMPLETE')
    stacks = cloudformation.list_stacks(StackStatusFilter=StackStatusFilter)
    stacks = [stack.get(var) for stack in stacks.get('StackSummaries')]
    return stacks


def changset_is_empty(changeset_description):
    status = changeset_description.get('StatusReason', '')
    if re.search(r"The submitted information didn't contain changes", status, re.IGNORECASE):
        return True
    else:
        return False


def changeset_is_pending(changeset_description):
    status = changeset_description.get('Status')
    if changset_is_empty(changeset_description):
        return False
    elif re.search(r'FAILED', status, re.IGNORECASE):
        raise Exception("Changest has a failure")
    elif re.search(r'CREATE_PENDING|CREATE_IN_PROGRESS', status, re.IGNORECASE):
        return True
    else:
        return False


def changeset_has_delete(changeset_description):
    for change in changeset_description.get('Changes'):
        resource_change = change.get('ResourceChange')
        if resource_change:
            action = resource_change.get('Action')
            replacement = resource_change.get('Replacement')
            if replacement == 'True':
                return True
            if action == 'Remove':
                return True
    else:
        return False


def deploy_template(template):
    """

    :type template: WavycloudStack
    :return: cloudformation waiter object
    """
    stack_name = template.stack_name
    logger.debug(pformat(get_stacks_by()))
    logger.debug(pformat(json.loads(template.to_json())))
    policy = template.get_template_policy()
    cloudformation.validate_template(TemplateBody=template.to_json())
    if stack_name in get_stacks_by():
        logger.info("Updating Stack: {}".format(stack_name))
        changeset_name = 'changeset-{}'.format(time.strftime("%Y-%m-%dT%H-%M-%S"))
        cloudformation.create_change_set(StackName=stack_name,
                                         TemplateBody=template.to_json(),
                                         ChangeSetName=changeset_name, Capabilities=['CAPABILITY_IAM'],
                                         Parameters=template.get_secret_params())
        changeset_description = cloudformation.describe_change_set(ChangeSetName=changeset_name, StackName=stack_name)
        while changeset_is_pending(changeset_description):
            changeset_description = cloudformation.describe_change_set(ChangeSetName=changeset_name,
                                                                       StackName=stack_name)

        if changeset_has_delete(changeset_description):
            raise Exception("Changeset '{}' has Remove action. Please review and execute change manually")
        elif not changset_is_empty(changeset_description):
            cloudformation.execute_change_set(ChangeSetName=changeset_name, StackName=stack_name)

        return cloudformation.get_waiter('stack_update_complete')
    else:
        logger.info("Creating Stack: {}".format(stack_name))
        cloudformation.create_stack(StackName=stack_name, TemplateBody=template.to_json(),
                                    Capabilities=['CAPABILITY_IAM'], StackPolicyBody=policy,
                                    Parameters=template.get_secret_params())
        return cloudformation.get_waiter('stack_create_complete')


def get_env_bat_code(**kwargs):
    code = ''
    for key, val in kwargs.items():
        code += 'set {}={}{}'.format(key, val, os.linesep)
    return code


def get_env_js_code(**kwargs):
    code = ''
    code += 'var {}="{}";{}'.format('Region', kwargs['Region'], os.linesep)
    code += 'var {}="{}";{}'.format('IdentityPoolId', kwargs[environment.SignupIdentityPoolId], os.linesep)
    code += 'var {}="{}";{}'.format('UserPoolId', kwargs[environment.SignupUserPoolId], os.linesep)
    code += 'var {}="{}";{}'.format('UserPoolClientId', kwargs[environment.SignupUserPoolClientId], os.linesep)
    return code


def get_env_python_code(**kwargs):
    code = 'import os' + os.linesep
    for key, val in kwargs.items():
        code += '{} = os.environ["{}"] = {}{}'.format(key, key, repr(val), os.linesep)
    return code


def generate_bat_env(filepath, **kwargs):
    code = get_env_bat_code(**kwargs)
    with open(filepath, 'w') as s:
        s.write(code)


def generate_js_env(filepath, **kwargs):
    code = get_env_js_code(**kwargs)
    with open(filepath, 'w') as s:
        s.write(code)


def generate_json_env(filepath, **kwargs):
    with open(filepath, 'w') as s:
        s.write(json.dumps(kwargs, indent=4))


def generate_python_env(filepath, **kwargs):
    code = get_env_python_code(**kwargs)
    with open(filepath, 'w') as s:
        s.write(code)


def get_stack_output_dict(stack_name):
    response = cloudformation.describe_stacks(StackName=stack_name)
    outputs = response['Stacks'][0]['Outputs']
    return {output.get('OutputKey'): output.get('OutputValue') for output in outputs}


def generate_env_files(stack_name, stage_name):
    stack_output = get_stack_output_dict(stack_name)
    config_path = os.path.join(os.path.dirname(__file__), '..', 'website_react', 'config.js')
    generate_config(config_path, **stack_output)
    py_path = os.path.join(os.path.dirname(__file__), '..', 'tests', 'env.py')
    generate_python_env(py_path, **stack_output)


def get_secret_path(stage):
    path = os.path.join(os.path.dirname(__file__), '..', 'secret_keys', '{}.py'.format(stage))
    if not os.path.exists(path):
        raise Exception("{} doesn't exist".format(path))
    else:
        return path


def create_bucket_url(bucket):
    """
    :type bucket: Bucket
    :return: Join
    """
    return Join("", ['http://', Ref(bucket), ".s3-website-", Ref(AWS_REGION), ".amazonaws.com/"])


def create_website_bucket_domain_name(bucket):
    """
    :type bucket: Bucket
    :return: Join
    """
    return Join("", [Ref(bucket), ".s3-website-", Ref(AWS_REGION), ".amazonaws.com"])


def get_branch_name():
    import subprocess
    out, err = subprocess.Popen('git rev-parse --abbrev-ref HEAD', stdout=subprocess.PIPE, shell=True).communicate()
    if err:
        raise Exception("Couldn't find branch name")
    else:
        return out.strip()


def get_arn(resource, resource_type=None, suffix=None):
    import troposphere.sns
    resource_type = resource_type or type(resource)
    suffix = suffix or []
    if not isinstance(suffix, list):
        suffix = [suffix]
    if resource_type == troposphere.sns.Topic or resource_type == 'sns':
        service = 'sns'
        return Join("",
                    ['arn:aws:', service, ':', Ref(AWS_REGION), ':', Ref(AWS_ACCOUNT_ID), ':', Ref(resource)] + suffix)
    elif resource_type == troposphere.s3.Bucket or resource_type == 's3':
        service = 's3'
        return Join("", ['arn:aws:', service, ':::', Ref(resource)] + suffix)
    elif resource_type == troposphere.dynamodb.Table or resource_type == 'dynamodb':
        service = 'dynamodb'
        return Join("", ['arn:aws:', service, ':', Ref(AWS_REGION), ':', Ref(AWS_ACCOUNT_ID), ':table/',
                         Ref(resource)] + suffix)
    elif resource_type == 'execute-api':
        service = 'execute-api'
        return Join("",
                    ['arn:aws:', service, ':', Ref(AWS_REGION), ':', Ref(AWS_ACCOUNT_ID), ':', Ref(resource)] + suffix)
    elif resource_type == troposphere.apigateway.RestApi or resource_type == 'apigateway':
        service = 'apigateway'
    else:
        raise Exception("Cannot get ARN for resource specified")
    return Join("", ['arn:aws:', service, ':', Ref(AWS_REGION), ':', Ref(AWS_ACCOUNT_ID), ':', Ref(resource)] + suffix)


def call(cmd):
    logger.info("Executing '{}'".format(cmd))
    returncode = subprocess.call(cmd, shell=True)
    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, cmd)


def install_packages(directory, packages_directory):
    import tempfile
    from distutils.dir_util import mkpath
    requirements = os.path.join(directory, 'requirements.txt')
    if not os.path.exists(requirements):
        logging.info("Package {} has no requirements.txt. Skipping pacakges install".format(directory))
        return
    cache_dir = os.path.join(tempfile.gettempdir(), 'pip_cache')
    mkpath(cache_dir)
    current_cwd = os.getcwd()
    logging.info("current working directory: {}".format(current_cwd))
    try:
        logging.info("Changing current working directory to: {}".format(directory))
        os.chdir(directory)
        call('pip install -r {} -t {} --cache-dir {} --ignore-installed --upgrade'.format(requirements,
                                                                                          packages_directory,
                                                                                          cache_dir))
    finally:
        logging.info("Reverting current working directory to: {}".format(current_cwd))
        os.chdir(current_cwd)


def remove_pycs(directory):
    import os
    import fnmatch
    for root, dirnames, filenames in os.walk(directory):
        for filename in fnmatch.filter(filenames, '*.pyc'):
            filepath = os.path.join(root, filename)
            os.unlink(filepath)


def remove_dist_and_egg(directory):
    import os
    for file in os.listdir(directory):
        if file.endswith('egg-info') or file.endswith('.dist-info'):
            shutil.rmtree(os.path.join(directory, file))


def prepare_python_package(directory, subfolder='packages'):
    if subfolder:
        packages_directory = os.path.join(directory, subfolder)
        # shutil.rmtree(packages_directory, ignore_errors=True)
    else:
        packages_directory = directory
    install_packages(directory, packages_directory)
    # remove_dist_and_egg(packages_directory)
    remove_pycs(directory)


def get_account_number():
    return boto3.client('sts').get_caller_identity().get('Account')


def remove_duplicates(seq):
    # https://stackoverflow.com/questions/480214/how-do-you-remove-duplicates-from-a-list-in-whilst-preserving-order
    seen = set()
    seen_add = seen.add
    return [x for x in seq if not (x in seen or seen_add(x))]


def upload_lambda(bucket_name, target_dir):
    prepare_python_package(target_dir)
    s3.create_bucket(Bucket=bucket_name)
    file_name, sha256 = zipdir_and_upload_to_s3(target_dir, bucket_name=bucket_name)
    return file_name
