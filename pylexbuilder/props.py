import logging
import time
from pprint import pformat

import boto3
import botocore
from botocore.exceptions import ClientError
from jsonobject import StringProperty, ObjectProperty, IntegerProperty, BooleanProperty, ListProperty

from . import utils
from .utils import BaseJsonObject

lex_model = boto3.client('lex-models')
""" :type : pyboto3.lexmodelbuildingservice """


class CodeHookProperty(BaseJsonObject):
    uri = StringProperty(exclude_if_none=True)
    messageVersion = StringProperty(exclude_if_none=True)


def assertFulfilmentType(val):
    assert val == 'ReturnIntent' or val == 'CodeHook'


class FulfilmentActivityProperty(BaseJsonObject):
    type = StringProperty(validators=[assertFulfilmentType], exclude_if_none=True)
    codeHook = ObjectProperty(CodeHookProperty, exclude_if_none=True)


def assertContentType(val):
    assert val == 'PlainText' or 'SSML'


class MessageProperty(BaseJsonObject):
    """
        {
            'contentType': 'PlainText'|'SSML',
            'content': 'string'
        }
    """
    content = StringProperty("")
    contentType = StringProperty("PlainText", validators=[assertContentType])


class PropertyWithMessages(BaseJsonObject):
    messages = ListProperty(MessageProperty, exclude_if_none=True)
    """ :type : list[MessageProperty] """

    def add_message(self, content, content_type='PlainText'):
        message = MessageProperty()
        message.content = content
        message.contentType = content_type
        self.messages = self.messages + [message]
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
    maxAttempts = IntegerProperty(exclude_if_none=True)

    def add_message(self, content, content_type='PlainText', maxAttempts=3):
        self.maxAttempts = maxAttempts
        return super(PropertyWithMessagesMaxAttempts, self).add_message(content, content_type)


class valueElicitationPromptProperty(PropertyWithMessagesMaxAttempts):
    pass


class EnumerationProperty(BaseJsonObject):
    value = StringProperty(exclude_if_none=True)


class SlotProperty(BaseJsonObject):
    name = StringProperty()
    description = StringProperty(exclude_if_none=True)
    enumerationValues = ListProperty(EnumerationProperty)
    checksum = StringProperty(exclude_if_none=True)
    """ :type : list[EnumerationProperty] """
    version = StringProperty(exclude_if_none=True)
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
        kwargs = self.to_json()
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
        self.enumerationValues = self.enumerationValues + [enum]


class IntentSlotProperty(BaseJsonObject):
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
    name = StringProperty(exclude_if_none=True)
    description = StringProperty(exclude_if_none=True)
    slotConstraint = StringProperty(exclude_if_none=True)
    slotType = StringProperty(exclude_if_none=True)
    slotTypeVersion = StringProperty(exclude_if_none=True)
    valueElicitationPrompt = ObjectProperty(valueElicitationPromptProperty, exclude_if_none=True)
    priority = IntegerProperty(exclude_if_none=True)
    sampleUtterances = ListProperty(StringProperty, exclude_if_none=True)
    """ :type : list[str] """
    responseCard = StringProperty(exclude_if_none=True)

    class SlotProperty(SlotProperty):
        pass

    def initialize(self):
        super(IntentSlotProperty, self).initialize()
        self.slotType = self.SlotProperty().name

    def create(self):
        slotToCreate = self.SlotProperty()
        slotToCreate.create()
        self.slotTypeVersion = slotToCreate.version

    def add_utterance(self, utterance):
        self.sampleUtterances = self.sampleUtterances + [utterance]
        return self


class PromptProperty(PropertyWithMessagesMaxAttempts):
    responseCard = StringProperty(exclude_if_none=True)


class StatmentProperty(PropertyWithMessages):
    responseCard = StringProperty(exclude_if_none=True)


class FollowUpPromptProperty(BaseJsonObject):
    prompt = ObjectProperty(PromptProperty, exclude_if_none=True)
    """ :type : PromptProperty """
    rejectionStatement = ObjectProperty(StatmentProperty, exclude_if_none=True)
    """ :type : RejectionStatmentProperty """


class IntentProperty(BaseJsonObject):
    name = StringProperty()
    description = StringProperty(exclude_if_none=True)
    slots = ListProperty(IntentSlotProperty, exclude_if_none=True)
    """ :type : list[IntentSlotProperty] """

    sampleUtterances = ListProperty(StringProperty, exclude_if_none=True)
    """ :type : list[str] """

    confirmationPrompt = ObjectProperty(PromptProperty, exclude_if_none=True)
    """ :type : PromptProperty """

    rejectionStatement = ObjectProperty(StatmentProperty, exclude_if_none=True)
    """ :type : StatmentProperty """

    followUpPrompt = ObjectProperty(FollowUpPromptProperty, exclude_if_none=True)
    """ :type : FollowUpPromptProperty """

    conclusionStatement = ObjectProperty(StatmentProperty, exclude_if_none=True)
    """ :type : StatmentProperty """

    dialogCodeHook = ObjectProperty(CodeHookProperty, exclude_if_none=True)
    """ :type : CodeHookProperty """

    fulfillmentActivity = ObjectProperty(FulfilmentActivityProperty, exclude_if_none=True)
    """ :type : FulfilmentActivityProperty """
    parentIntentSignature = StringProperty(exclude_if_none=True)
    checksum = StringProperty(exclude_if_none=True)

    def add_slot(self, slot_prop):
        self.slots = self.slots + [slot_prop]

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
        kwargs = self.to_json()
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


class BotIntentProperty(BaseJsonObject):
    intentName = StringProperty(exclude_if_none=True)
    intentVersion = StringProperty(exclude_if_none=True)


class BotProperty(BaseJsonObject):
    name = StringProperty()
    description = StringProperty(exclude_if_none=True)
    intents = ListProperty(BotIntentProperty, exclude_if_none=True)
    """ :type : BotIntentProperty"""
    clarificationPrompt = ObjectProperty(PromptProperty, exclude_if_none=True)
    """ :type : PromptProperty"""
    abortStatement = ObjectProperty(StatmentProperty, exclude_if_none=True)
    """ :type : StatmentProperty"""
    idleSessionTTLInSeconds = IntegerProperty(exclude_if_none=True)
    voiceId = StringProperty('Joanna')
    checksum = StringProperty(exclude_if_none=True)
    processBehavior = StringProperty("BUILD")
    locale = StringProperty('en-US')
    childDirected = BooleanProperty()

    class IntentMeta:
        intents = []
        existing_intents = []

    def create_all_intents(self):
        for intent in self.IntentMeta.intents:
            intent.create()

    def add_all_intents(self):
        all_intents = self.IntentMeta.intents + self.IntentMeta.existing_intents
        for intent in all_intents:
            self.add_intent(intent.name, intent.version)

    def add_intent(self, name, version):
        intent = BotIntentProperty()
        intent.intentName = name
        intent.intentVersion = version
        self.intents = self.intents + [intent]
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

    def create(self, async=False, publish=False):
        self.create_all_intents()
        self.add_all_intents()
        logging.info("Creating bot: {}".format(self.name))
        # Get the old bot checksum if available
        self.checksum = self.get_bot_checksum(self.name, '$LATEST')

        kwargs = self.to_json()
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