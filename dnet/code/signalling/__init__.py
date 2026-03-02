import gc
gc.enable()
print("Loading LighthouseMesh")
from .LighthouseMesh import LighthouseMesh
print("loading Payload")
from .Payload import Payload
gc.collect()

