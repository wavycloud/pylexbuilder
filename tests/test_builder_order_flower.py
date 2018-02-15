from pprint import pprint
import logging
from order_flower_bot import bot
from order_flower_bot.bot import OrderFlowersIntent
from pylexbuilder import SlotProperty, props

logging.basicConfig(level=logging.INFO)

def test_props():
    botIntent = props.BotIntentProperty(intentName="Hello")
    print(botIntent.to_json())

def test_bot():
    flower_bot = bot.OrderFlowersBot()
    assert flower_bot.name == "OrderFlowers"
    assert 'clarificationPrompt' in flower_bot.keys()
    pprint(flower_bot.to_json())
    flower_bot.create()


def test_intent():
    intent = OrderFlowersIntent()
    pprint(intent.to_json())

def test_slot():
    slot = SlotProperty()
    slot.name = "YesNo"
    slot.add_enumeration("Yes")
    slot.create()
    pprint(slot.to_json())