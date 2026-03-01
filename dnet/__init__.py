import gc
gc.enable()
print("Loading LighthouseMesg")
from dnet.signalling.LighthouseMesh import LighthouseMesh
print("loading Payload")
from dnet.signalling.Payload import Payload
gc.collect()

