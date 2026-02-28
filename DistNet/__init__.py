import gc
gc.enable()
print("Loading LighthouseMesg")
from distnet.signalling.LighthouseMesh import LighthouseMesh
print("loading Payload")
from distnet.signalling.Payload import Payload
gc.collect()

