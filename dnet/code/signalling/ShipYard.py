import asyncio


class ShipYard:

    def __init__(self):
        self.dock = {}

    def addVessel(self, ship:Vessel):
        self.dock[ship.name()]=ship

    def findVesselByName(self, name:str) -> Vessel:
        pass

    def findVesselsBuService(self, service:str) -> List[Vessle]:
        pass
