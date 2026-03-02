
import ubinascii
import json
import network

class Payload:

#payload structure
#   target_id
#   source_id
#   action
#   data

    class Action:
        isThereAnybodyOutThere = const("a1")
        whoHas = const("a2")
        eventTrigger = const("a3")
        profile = const("a4")

    #Field Names
    class Field:
        TargetId = const("f1")
        SourceId = const("f2")
        Action = const("f4")
        Data = const("f3")

    def __init__(self):
        self.data = {}
        self.payload = {}
 
    def getData(self):
        return self.payload[Payload.Data]
    
    def parse(self, sPayload:str):
        print(f"parse: {sPayload}")
        if (sPayload):
            self.payload = json.loads(sPayload)
            print(f"parsed {str(self.payload)}")
        else:
            self.payload = {}
            
        return self.payload
    
    def getTargetId(self):
        self.payload[Payload.Field.TargetId] 
        
    def build(self, source_id, target_id, action:str="", data:dict={}):
        self.payload[Payload.Field.SourceId] = ubinascii.hexlify(source_id).decode()
        self.payload[Payload.Field.TargetId] = ubinascii.hexlify(target_id).decode() 
        self.payload[Payload.Field.Action] = action
        self.payload[Payload.Field.Data] = data
        return json.dumps(self.payload)

    def payload(self):
        return json.dumps(self.payload)
    
    def stringify(self):
        return json.dumps(self.payload)

