import inspect
import logging
import os
import subprocess
import time
from pprint import pformat

import boto3
from botocore.exceptions import ClientError
from schematics import types, models
from troposphere import AWS_REGION, AWS_ACCOUNT_ID, Ref

from . import utils

lex_model = boto3.client('lex-models')
""" :type : pyboto3.lexmodelbuildingservice """


class BaseModel(models.Model):
    def __init__(self, *args, **kwargs):
        super(BaseModel, self).__init__(*args, **kwargs)
        self.initialize()

    def initialize(self):
        pass


class CodeHookProperty(BaseModel):
    uri = types.StringType(serialize_when_none=False)
    messageVersion = types.StringType(serialize_when_none=False)


def assertFulfilmentType(val):
    assert val == 'ReturnIntent' or val == 'CodeHook'


class FulfilmentActivityProperty(BaseModel):
    type = types.StringType(validators=[assertFulfilmentType], serialize_when_none=False)
    codeHook = types.ModelType(CodeHookProperty, serialize_when_none=False, default=CodeHookProperty())
    """ :type : CodeHookProperty """


def assertContentType(val):
    assert val == 'PlainText' or 'SSML'


class MessageProperty(BaseModel):
    """
        {
            'contentType': 'PlainText'|'SSML',
            'content': 'string'
        }
    """
    content = types.StringType(default="")
    contentType = types.StringType(default="PlainText", validators=[assertContentType])


class PropertyWithMessages(BaseModel):
    messages = types.ListType(types.ModelType(MessageProperty), default=[])
    """ :type : list[MessageProperty] """

    def add_message(self, content, content_type='PlainText'):
        message = MessageProperty()
        message.content = content
        message.contentType = content_type
        self.messages.append(message)
        return self


class PropertyWithMessagesMaxAttempts(PropertyWithMessages):
    """
        {
            'messages': [
                {
                    'contentType': 'PlainText'|'SSML',
                    'content': 'string'
                },
            ],
            'maxAttempts': 123,
            'responseCard': 'string'
        }
    """
    maxAttempts = types.IntType(serialize_when_none=False)

    def add_message(self, content, content_type='PlainText', maxAttempts=3):
        self.maxAttempts = maxAttempts
        return super(PropertyWithMessagesMaxAttempts, self).add_message(content, content_type)


class ValueElicitationPromptProperty(PropertyWithMessagesMaxAttempts):
    pass


class EnumerationProperty(BaseModel):
    value = types.StringType(serialize_when_none=False)


class SlotProperty(BaseModel):
    name = types.StringType()
    description = types.StringType(serialize_when_none=False)
    enumerationValues = types.ListType(types.ModelType(EnumerationProperty), serialize_when_none=False)
    checksum = types.StringType(serialize_when_none=False)
    """ :type : list[EnumerationProperty] """
    version = types.StringType(serialize_when_none=False)

    def get_slot_type_checksum(self):
        checksum = None
        try:
            response = lex_model.get_slot_type(name=self.name, version='$LATEST')
            logging.debug("get_slot_type: {}".format(pformat(response)))
            checksum = response.get('checksum')
        except ClientError as e:
            if e.response['Error']['Code'] != 'NotFoundException':
                raise
        return checksum

    def create(self):
        logging.info("Creating slot: {}".format(self.name))
        self.checksum = self.get_slot_type_checksum()
        kwargs = self.to_primitive()
        # Put the slot
        response = lex_model.put_slot_type(**kwargs)
        logging.debug("put_slot_type: {}".format(pformat(response)))
        self.version = response['version']
        self.checksum = response['checksum']
        try:
            version_response = lex_model.create_slot_type_version(name=self.name, checksum=self.checksum)
            self.version = version_response['version']
            self.checksum = version_response['checksum']
        except ClientError as e:
            logging.warning('Failed to create new slot type version ', exc_info=1)

    def add_enumeration(self, value):
        enum = EnumerationProperty()
        enum.value = value
        if not self.enumerationValues:
            self.enumerationValues = [enum]
        else:
            self.enumerationValues = self.enumerationValues + [enum]


class IntentSlotPropertyBase(BaseModel):
    """
        {
            'name': 'string',
            'description': 'string',
            'slotConstraint': 'Required'|'Optional',
            'slotType': 'string',
            'slotTypeVersion': 'string',
            'valueElicitationPrompt': {
                'messages': [
                    {
                        'contentType': 'PlainText'|'SSML',
                        'content': 'string'
                    },
                ],
                'maxAttempts': 123,
                'responseCard': 'string'
            },
            'priority': 123,
            'sampleUtterances': [
                'string',
            ],
            'responseCard': 'string'
        }
    """
    name = types.StringType(serialize_when_none=False)
    description = types.StringType(serialize_when_none=False)
    slotConstraint = types.StringType(serialize_when_none=False)
    slotType = types.StringType(serialize_when_none=False)
    slotTypeVersion = types.StringType(serialize_when_none=False)
    valueElicitationPrompt = types.ModelType(ValueElicitationPromptProperty, default=ValueElicitationPromptProperty())
    """:type: ValueElicitationPromptProperty"""
    priority = types.IntType(serialize_when_none=False)
    sampleUtterances = types.ListType(types.StringType, serialize_when_none=False)
    """ :type : list[str] """
    responseCard = types.StringType(serialize_when_none=False)

    def add_utterance(self, utterance):
        self.sampleUtterances.append(utterance)
        return self

    def add_prompt(self, prompt):
        self.valueElicitationPrompt.add_message(prompt)

    def create(self):
        pass

def AmazonSlotProperty(slot_type, name=None, required=False, prompt=None):
    prop = IntentSlotPropertyBase()
    prop.slotType = slot_type
    prop.slotConstraint = 'Required' if required else 'Optional'
    if name:
        prop.name = name
    if prompt:
        prop.add_prompt(prompt)

    return prop

class IntentSlotProperty(IntentSlotPropertyBase):
    class SlotProperty(SlotProperty):
        pass

    def initialize(self):
        super(IntentSlotProperty, self).initialize()
        self.slotType = self.SlotProperty().name

    def create(self):
        slotToCreate = self.SlotProperty()
        slotToCreate.create()
        self.slotTypeVersion = slotToCreate.version


class PromptProperty(PropertyWithMessagesMaxAttempts):
    responseCard = types.StringType(serialize_when_none=False)


class StatmentProperty(PropertyWithMessages):
    responseCard = types.StringType(serialize_when_none=False)


class FollowUpPromptProperty(BaseModel):
    prompt = types.ModelType(PromptProperty, serialize_when_none=False)
    """ :type : PromptProperty """
    rejectionStatement = types.ModelType(StatmentProperty, serialize_when_none=False)
    """ :type : RejectionStatmentProperty """


class IntentProperty(BaseModel):
    name = types.StringType()
    description = types.StringType(serialize_when_none=False)
    slots = types.ListType(types.ModelType(IntentSlotProperty), serialize_when_none=False, default=[])
    """ :type : list[IntentSlotProperty] """

    sampleUtterances = types.ListType(types.StringType, serialize_when_none=False)
    """ :type : list[str] """

    confirmationPrompt = types.ModelType(PromptProperty, serialize_when_none=False)
    """ :type : PromptProperty """

    rejectionStatement = types.ModelType(StatmentProperty, serialize_when_none=False)
    """ :type : StatmentProperty """

    followUpPrompt = types.ModelType(FollowUpPromptProperty, serialize_when_none=False)
    """ :type : FollowUpPromptProperty """

    conclusionStatement = types.ModelType(StatmentProperty, serialize_when_none=False)
    """ :type : StatmentProperty """

    dialogCodeHook = types.ModelType(CodeHookProperty, serialize_when_none=False)
    """ :type : CodeHookProperty """

    fulfillmentActivity = types.ModelType(FulfilmentActivityProperty, serialize_when_none=False,
                                          default=FulfilmentActivityProperty())
    """ :type : FulfilmentActivityProperty """
    parentIntentSignature = types.StringType(serialize_when_none=False)
    checksum = types.StringType(serialize_when_none=False)

    def add_slot(self, slot_prop):
        self.slots.append(slot_prop)

    def add_utterance(self, utterance):
        self.sampleUtterances = self.sampleUtterances + [utterance]
        return self

    def get_intent_checksum(self, version='$LATEST'):
        checksum = None
        try:
            response = lex_model.get_intent(name=self.name, version=version)
            logging.info("get_intent: {}".format(pformat(response)))
            checksum = response.get('checksum')
        except ClientError as e:
            if e.response['Error']['Code'] != 'NotFoundException':
                raise

        return checksum

    def create_slots(self):
        for slot in self.slots:
            slot.create()

    def create(self):
        logging.info("Creating intent: {}".format(self.name))
        self.create_slots()
        # Create the intent and get the old checksum if it exists
        self.checksum = self.get_intent_checksum()
        kwargs = self.to_primitive()
        # Put the new/updated intent
        response = lex_model.put_intent(**kwargs)
        logging.info("put_intent: {}".format(pformat(response)))

        self.checksum = response.get('checksum')
        try:
            version_response = lex_model.create_intent_version(name=self.name, checksum=self.checksum)
            logging.info("create_intent_version: {}".format(pformat(version_response)))
            self.version = version_response.get('version')
            self.checksum = version_response.get('checksum')
        except ClientError as e:
            logging.warning('Failed to create new intent version ', exc_info=1)
        return self


class BotIntentProperty(BaseModel):
    intentName = types.StringType(serialize_when_none=False)
    intentVersion = types.StringType(serialize_when_none=False)


class BotProperty(BaseModel):
    name = types.StringType()
    description = types.StringType(serialize_when_none=False)
    intents = types.ListType(types.ModelType(BotIntentProperty), serialize_when_none=False, default=[])
    """ :type : BotIntentProperty"""
    clarificationPrompt = types.ModelType(PromptProperty, serialize_when_none=False, default=PromptProperty())
    """ :type : PromptProperty"""
    abortStatement = types.ModelType(StatmentProperty, serialize_when_none=False, default=StatmentProperty())
    """ :type : StatmentProperty"""
    idleSessionTTLInSeconds = types.IntType(serialize_when_none=False)
    voiceId = types.StringType(default='Joanna')
    checksum = types.StringType(serialize_when_none=False)
    version = types.StringType(serialize_when_none=False)
    processBehavior = types.StringType(default="BUILD")
    locale = types.StringType(default='en-US')
    childDirected = types.BooleanType()

    class IntentMeta:
        intents = []
        """ :type: list[IntentProperty] """
        existing_intents = []

    def create_all_intents(self, lambda_arn):
        for intent in self.IntentMeta.intents:
            if intent.is_lambda():
                intent.update_uri(lambda_arn)
            intent.create()


    def add_all_intents(self):
        for intent in self.get_all_intents():
            self.add_intent(intent.name, intent.version)

    def get_all_intents(self):
        all_intents = self.IntentMeta.intents + self.IntentMeta.existing_intents
        return all_intents

    def add_intent(self, name, version):
        intent = BotIntentProperty()
        intent.intentName = name
        intent.intentVersion = version
        self.intents.append(intent)
        return self

    @classmethod
    def wait_for_bot_build(cls, bot_name, version_name):
        build_status = 'BUILDING'
        response = {}
        while build_status == 'BUILDING':
            time.sleep(1)
            response = lex_model.get_bot(name=bot_name, versionOrAlias=version_name)
            logging.debug("get_bot: {}".format(pformat(response)))
            build_status = response.get('status')

        if build_status == 'FAILED' or build_status == 'NOT_BUILT':
            raise Exception("Couldn't build {}. build_status: {}. failureReason: {}".format(bot_name, build_status,
                                                                                            response.get(
                                                                                                'failureReason')))
        return response

    def delete_bot(self):
        raise NotImplementedError()

    @classmethod
    def get_bot_alias_checksum(cls, bot_name, alias_name):
        checksum = None
        try:
            response = lex_model.get_bot_alias(name=alias_name, botName=bot_name)
            logging.info("get_bot_alias: {}".format(pformat(response)))
            checksum = response.get('checksum')
        except ClientError as e:
            if e.response['Error']['Code'] != 'NotFoundException':
                raise

        return checksum

    @classmethod
    def get_bot_checksum(cls, bot_name, versionOrAlias):
        checksum = None
        try:
            response = lex_model.get_bot(name=bot_name, versionOrAlias=versionOrAlias)
            logging.info("get_bot: {}".format(pformat(response)))
            checksum = response.get('checksum')
        except ClientError as e:
            if e.response['Error']['Code'] != 'NotFoundException':
                raise
        return checksum

    def create_alias(self, version, alias='prod'):
        checksum = self.get_bot_alias_checksum(self.name, alias)
        kwargs = utils.get_kwargs(checksum)
        response = lex_model.put_bot_alias(name=alias, botVersion=version, botName=self.name, **kwargs)
        logging.info("put_bot_alias: {}".format(pformat(response)))

    def create(self, async=False):
        lambda_arn = self.deploy_cloudformation()
        self.create_all_intents(lambda_arn)
        self.add_all_intents()
        logging.info("Creating bot: {}".format(self.name))
        # Get the old bot checksum if available
        self.checksum = self.get_bot_checksum(self.name, '$LATEST')

        kwargs = self.to_primitive()
        # Build/Update the bot
        response = lex_model.put_bot(
            **kwargs
        )
        self.version = response.get('version')
        logging.info("put_bot: {}".format(pformat(response)))
        self.checksum = response.get('checksum')
        try:
            version_response = lex_model.create_bot_version(name=self.name, checksum=self.checksum)
            logging.info("create_bot_version: {}".format(pformat(response)))
            self.version = version_response.get('version')
            self.checksum = version_response.get('checksum')
        except ClientError as e:
            logging.warning("Failed to create Bot Version", exc_info=1)

        if not async:
            self.wait_for_bot_build(self.name, self.version)
            self.create_alias('$LATEST', 'dev')
            self.create_alias(self.version, 'prod')

    @property
    def environment_variables(self):
        return {}

    @property
    def runtime(self):
        return 'python2.7'

    @property
    def stack_name(self):
        return '{}ChatbotStack'.format(self.name)

    @property
    def s3_bucket_name(self):
        return '{}Bucket'.format(self.name)

    @property
    def lambda_alias(self):
        return 'production'

    @property
    def package_path(self):
        filepath = inspect.getfile(self.__class__)
        return os.path.dirname(filepath)

    def deploy_cloudformation(self):
        file_name = utils.upload_lambda(self.s3_bucket_name, self.package_path)
        t = self.get_cloudformation_template(file_name)
        template_path = 'template.json'
        with open(template_path, 'w') as f:
            f.write(t.to_json())

        try:
            utils.call(
                'aws cloudformation deploy --template-file {} --stack-name {} --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset'.format(
                    template_path, self.stack_name))
        except Exception as e:
            pass


        lambda_func_id = utils.cloudformation.describe_stack_resource(StackName=self.stack_name,
                                                                      LogicalResourceId=self.name)[
            'StackResourceDetail']['PhysicalResourceId']
        region = boto3.session.Session().region_name
        account = utils.get_account_number()
        lambda_arn = 'arn:aws:lambda:{region}:{account_id}:function:{resource_id}'.format(region=region,
                                                                                          account_id=account,
                                                                                          resource_id=lambda_func_id)
        boto3session = boto3.session.Session()
        awslambda = boto3.client('lambda')
        """ :type : pyboto3.lambda_ """

        for i, intent in enumerate(self.get_all_intents()):
            try:
                awslambda.add_permission(FunctionName='{}:{}'.format(lambda_arn, self.lambda_alias),
                                     StatementId='{}PermissionToLexProduction'.format(intent.name),
                                     Action='lambda:InvokeFunction',
                                     SourceArn='arn:aws:lex:{aws_region}:{aws_account_id}:intent:{intent_name}:*'.format(
                                         aws_region=boto3session.region_name,
                                         aws_account_id=boto3.client('sts').get_caller_identity().get('Account'),
                                         intent_name=intent.name
                                     ),
                                     Principal="lex.amazonaws.com",
                                     )
            except ClientError as e:
                if e.response['Error']['Code'] != 'ResourceConflictException':
                    raise
        return lambda_arn

    def get_cloudformation_template(self, lambda_filename):
        from troposphere import Template, GetAtt, Join
        from troposphere.awslambda import Environment
        from troposphere.awslambda import Permission
        from troposphere.serverless import Function
        t = Template()
        t.add_description("Built with WavyCloud's pylexbuilder")
        t.add_transform('AWS::Serverless-2016-10-31')
        lambda_func = t.add_resource(
            Function(
                self.name,
                Handler='handler.index',
                Runtime=self.runtime,
                CodeUri='s3://{}/{}'.format(self.s3_bucket_name, lambda_filename),
                Policies=['AmazonDynamoDBFullAccess', 'AmazonLexFullAccess'],
                AutoPublishAlias=self.lambda_alias,
                Environment=Environment(
                    Variables=self.environment_variables
                )
            ),
        )
        for i, intent in enumerate(self.get_all_intents()):
            t.add_resource(Permission(
                "PermissionToLex{}".format(intent.name),
                FunctionName=GetAtt(lambda_func, "Arn"),
                Action="lambda:InvokeFunction",
                Principal="lex.amazonaws.com",
                SourceArn=Join("", ['arn:aws:lex:', Ref(AWS_REGION), ':', Ref(AWS_ACCOUNT_ID), ':intent:{}:*'.format(intent.name)])
            ))
        return t
