import gc
gc.enable()

from . import messaging

print("Loading LighthouseMesh")
from .signalling.LighthouseMesh import LighthouseMesh
print("loading Payload")
from .signalling.Payload import Payload

gc.collect()