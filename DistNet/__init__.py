import gc
gc.enable()
print("Loading LighthouseMesg")
from signalling.LighthouseMesh import LighthouseMesh
print("loading Payload")
from signalling.Payload import Payload
gc.collect()

