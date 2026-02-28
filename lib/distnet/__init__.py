import gc
gc.enable()
print("Loading LighthouseMesg", version="Packaging")
from distnet.signalling.LighthouseMesh import LighthouseMesh
print("loading Payload")
from distnet.signalling.Payload import Payload
gc.collect()

