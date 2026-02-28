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
        import MicroPyServer
        gc.collect()
    except:
        print("ERROR: Unable to load MicroPyServer base class")
