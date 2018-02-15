from pylexbuilder import IntentProperty, BotProperty, SlotProperty, IntentSlotProperty


class FlowerTypeIntentSlot(IntentSlotProperty):
    class SlotProperty(SlotProperty):
        name = 'FlowerTypes'
        enumerationValues = [
            {'value': 'roses'},
            {'value': 'tulips'},
            {'value': 'lilies'},
            {'value': 'red roses'},
        ]

    name = 'FlowerType'

    slotConstraint = 'Required'
    description = 'The type of flower to pick up'
    sampleUtterances = [
        "I would like to order {FlowerType}",
        "May I order {FlowerType}",
        "Can I order {FlowerType}",
    ]

    def initialize(self):
        super(FlowerTypeIntentSlot, self).initialize()
        self.add_prompt("What flower type would you like?")

class OrderFlowersIntent(IntentProperty):
    name = "OrderFlowers"
    description = "Order Beautiful Flowers"
    sampleUtterances = [
        "I would like to order {{{0}}}".format(FlowerTypeIntentSlot().name),
        "I would like to order some {{{0}}}".format(FlowerTypeIntentSlot().name),
    ]

    def update_uri(self, lambda_arn):
        self.fulfillmentActivity.codeHook.uri = lambda_arn

    def is_lambda(self):
        return self.fulfillmentActivity.type == 'CodeHook'

    def initialize(self):
        self.fulfillmentActivity.type = 'CodeHook'
        self.fulfillmentActivity.codeHook.messageVersion = '1.0'
        self.add_slot(FlowerTypeIntentSlot())


class OrderFlowersBot(BotProperty):
    name = "OrderFlowers"
    childDirected = False

    class IntentMeta(BotProperty.IntentMeta):
        intents = [
            OrderFlowersIntent()
        ]

    def initialize(self):
        self.abortStatement.add_message("Sorry I couldn't understand, could you please try in a different way")
        self.clarificationPrompt.add_message("Hello There, this Joanna from Flowers Shop. How can I help you?")

