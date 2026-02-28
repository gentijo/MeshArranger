import network
import asyncio

import json
from   signalling.LighthouseMesh import LighthouseMesh


lighthouse = LighthouseMesh()
asyncio.run(lighthouse.run())
print ("end of main")