from jsonobject import JsonObject


def get_kwargs(checksum):
    kwargs = {}
    if checksum:
        kwargs['checksum'] = checksum

    return kwargs


class BaseJsonObject(JsonObject):

    def __init__(self, *args, **kwargs):
        super(BaseJsonObject, self).__init__(*args, **kwargs)
        self.initialize()

    def to_json(self):
        for key in self.keys():
            setattr(self, key, getattr(self, key))

        return super(BaseJsonObject, self).to_json()

    def initialize(self):
        pass
