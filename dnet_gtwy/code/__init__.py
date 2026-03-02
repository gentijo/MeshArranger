import gc
gc.enable()

try:
    import MicroPyServer
except:
    import mip
    try:
        print("Installing MicroPyServer")
        mip.install("github:ROSMicroPy/rmp_pylib-micropyserver")
        import MicroPyServer
        gc.collect()
    except:
        print("ERROR: Unable to load MicroPyServer base class")

try:
    import dnet
except:
    import mip
    try:
        print("Installing dnet")
        mip.install("github:WidgetMesh/MeshArranger/dnet", version="Packaging")
        import dnet
        gc.collect()
    except:
        print("ERROR: Unable to load MicroPyServer base class")

from dnet.signalling.LighthouseMesh import LighthouseMesh
from dnet.signalling.Payload import Payload
