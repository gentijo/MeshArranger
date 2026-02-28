import network
import aioespnow
import uasyncio as asyncio
import ubinascii
import json
import time
        
from distnet.signalling.Payload import Payload

class LighthouseMesh():
    BROADCAST_TARGET = const(b'\xff\xff\xff\xff\xff\xff')

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # Optional: Add an initialized flag to prevent re-initialization of __init__
            cls._initialized = False 
        return cls._instance
        
    def __init__(self):
        self.wlan_sta = None
        self.wlan_mac = None
        self.espnow = None
        self.payload_IsThereAnybodyOutThere = None
        self,payload_Profile = None
    
        self.wlan_sta = network.WLAN(network.STA_IF)  # Or network.AP_IF
        self.wlan_sta.active(True)
        self.wlan_mac = wlan_sta.config('mac')
        self.wlan_sta.config()  # Set channel explicitly if packets are not delivered
        self.wlan_sta.disconnect()      # For ESP8266

        self.espnow = aioespnow.AIOESPNow()  
        self.espnow.active(True)

        #comment one out
        self.peer1 = b'\x80\x65\x99\xdd\x48\xf4'
        self.peer2 = b'\xf4\x12\xfa\xce\xee\x18'

        if wlan_mac == self.peer1:
            self.peer = self.peer2
        elif self.wlan_mac == self.peer2:
            self.peer = self.peer1

        self.use_broadcast = True;
        if self.use_broadcast:
            self.peer = LighthouseMesh.BROADCAST_TARGET

        self.espnow.add_peer(LighthouseMesh.BROADCAST_TARGET)
        self.espnow.add_peer(self.peer1)
        self.espnow.add_peer(self.peer2)


    def wait_for_message(self, esp):
        while True:
            mac, msg = esp.irecv(timeout_ms=0)
            if mac is None:
                return
        
            if msg:
                print(f"Message Received. {msg}")
                payload:dict = Payload().parse(msg.decode('utf-8'))
                print(f"payload {payload}")
                if payload: # msg == None if timeout in recv()       
                    action = payload[Payload.Field.Action]
                if action == Payload.Action.isThereAnybodyOutThere:
                    print("Is there anyboth out there")

                else:
                    print ("Invalid message")
        
    def send_IsThereAnybodyOutThere(self):
        payload = Payload().build(self.wlan_mac, \
            self.peer,\
            Payload.Action.isThereAnybodyOutThere)
        print(f"A Send, {payload}")
        self.espnow.send(peer, payload)
 
    def print_stats(self):
        stats = self.espnow.stats()
        print("\nESP-NOW Statistics:")
        print(f"  Packets Sent: {stats[0]}")
        print(f"  Packets Delivered: {stats[1]}")
        print(f"  Packets Dropped (TX): {stats[2]}")
        print(f"  Packets Received: {stats[3]}")
        print(f"  Packets Dropped (RX): {stats[4]}")
    
    def get_stats(self):
        return self.espnow.stats()

    async def run():
        self.espnow.irq(wait_for_message(self.espnow))
        print("Lighthouse Mesh: Running")

    
