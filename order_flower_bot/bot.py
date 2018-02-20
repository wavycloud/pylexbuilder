from pylexbuilder import IntentProperty, BotProperty, SlotProperty, IntentSlotProperty


class FlowerTypeIntentSlot(IntentSlotProperty):
    class SlotProperty(SlotProperty):
        def initialize(self):
            self.name = 'FlowerTypes'
            self.enumerationValues = [
                {'value': 'roses'},
                {'value': 'tulips'},
                {'value': 'lilies'},
                {'value': 'red roses'},
            ]



    def initialize(self):
        self.name = 'FlowerType'
        self.slotConstraint = 'Required'
        self.description = 'The type of flower to pick up'
        self.sampleUtterances = [
            "I would like to order {FlowerType}",
            "May I order {FlowerType}",
            "Can I order {FlowerType}",
        ]
        super(FlowerTypeIntentSlot, self).initialize()
        self.add_prompt("What flower type would you like?")

class OrderFlowersIntent(IntentProperty):

    def update_uri(self, lambda_arn):
        self.fulfillmentActivity.codeHook.uri = lambda_arn

    def is_lambda(self):
        return self.fulfillmentActivity.type == 'CodeHook'

    def initialize(self):
        self.name = "OrderFlowers"
        self.description = "Order Beautiful Flowers"
        self.sampleUtterances = [
            "I would like to order {{{0}}}".format(FlowerTypeIntentSlot().name),
            "I would like to order some {{{0}}}".format(FlowerTypeIntentSlot().name),
        ]
        self.fulfillmentActivity.type = 'CodeHook'
        self.fulfillmentActivity.codeHook.messageVersion = '1.0'
        self.add_slot(FlowerTypeIntentSlot())


class OrderFlowersBot(BotProperty):

    class IntentMeta(BotProperty.IntentMeta):
        intents = [
            OrderFlowersIntent()
        ]

    def initialize(self):
        self.name = 'OrderFlowers'
        self.childDirected = False
        self.abortStatement.add_message("Sorry I couldn't understand, could you please try in a different way")
        self.clarificationPrompt.add_message("Hello There, this Joanna from Flowers Shop. How can I help you?")

