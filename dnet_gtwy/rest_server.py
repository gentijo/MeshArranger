#!/usr/bin/env python3
"""
SmartStepper Module

This module provides a web interface for controlling stepper motors using the MotorControl library.
It includes a JSON profile for the web form and endpoint interface for motor control.
"""

import json
import sys
import wifi
import gc

# MicroPython 1.25+ compatible imports
try:
    from typing import Dict, Any, Optional
except ImportError:
    # Fallback for MicroPython versions without typing
    Dict = dict
    Any = object
    Optional = object

# Import MotorControl and MicroPyServer
try:
    print("Motor Control")
    from rmp.MotorControl.MotorControl import MotorController, MotorType
    print("MicroPyServer")
    from rmp.MicroPyServer.micropyserver import MicroPyServer
    print("utils")
    from rmp.MicroPyServer.utils import *
except ImportError as e:
    print(e)
    # Fallback for different import paths
    try:
        from MotorControl import MotorController, MotorType
        from MicroPyServer import MicroPyServer
        from rmp.MicroPyServer.utils import *

    except ImportError:
        print("Error: Could not import MotorControl or MicroPyServer modules")
        sys.exit(1)


class SmartStepper:
    """SmartStepper controller with web interface."""
    
    def __init__(self, host="0.0.0.0", port=8080, config_file=None):
        """Initialize SmartStepper with web server."""
        try:
            print(f"host={host} port={port}")
            
             
            gc.enable()
            print(f"Mem Free {gc.mem_free()}\r\n")
            gc.collect()
            gc.disable()
           
            
            self.config = self._load_config(config_file)
            self.server = MicroPyServer()
            self.motor_controller = MotorController()
            self.stepper_motor = None
            print("Register")
            self.motor_controller.register_driver("stepper_driver", StepperDriver)
            print("List")
            self.motor_controller.list_available_drivers()
            print("Init")
            print(self.initialize_motor())

            self.setup_routes()

        except Exception as e:
            print(f"Error initializing SmartStepper: {e}")
            raise
    
    def _load_config(self, config_file=None):
        """Load configuration from JSON file."""
        if config_file is None:
            # Try common config file locations
            config_locations = [
                'config.json',
                '../config.json',
                'rmp/config.json'
            ]
            
            for location in config_locations:
                try:
                    with open(location, 'r') as f:
                        return json.load(f)
                except Exception:
                    continue
            
            print("Warning: Could not load config file from any location, using defaults")
        
        # Try to load the specified config file
        if config_file:
            try:
                with open(config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Could not load config file {config_file}: {e}")
        
        # Default configuration
        return {
            "server": {
                "host": "0.0.0.0",
                "port": 80
            },
            "motor": {
                "default_pins": {
                    "step_pin": 18,
                    "dir_pin": 19,
                    "enable_pin": 20
                },
                "default_settings": {
                    "microsteps": 1,
                    "default_speed": 60,
                    "default_steps": 200
                }
            },
            "web_interface": {
                "title": "SmartStepper Control",
                "description": "Control your stepper motor with direction and speed settings",
                "speed_range": {
                    "min": 0,
                    "max": 1000
                },
                "steps_range": {
                    "min": 1,
                    "max": 10000
                }
            }
        }
    
    def setup_routes(self):
        """Setup HTTP routes for the web interface."""
        print("adding routes")
        try:
            # Serve the layout JSON
            print("Adding layout")
            
            gc.enable()
            gc.mem_free()   
            gc.collect()
            gc.disable()
            
            self.server.add_route("/layout", self.get_layout, "GET")
            
            # Handle motor control commands
            print("Add Control")
            self.server.add_route("/control", self.control_motor, "POST")
            self.server.add_route("/control", self.optionsRequest, "OPTIONS" )

            # Get motor status
            self.server.add_route("/status", self.get_status, "GET")
            
            # Initialize motor
            self.server.add_route("/init", self.initialize_motor_from_api, "POST")
        except Exception as e:
            print(f"Error setting up routes: {e}")
            raise
        
    def optionsRequest(self, request):
        
        print("Options Request")
        # Define CORS headers
        cors_headers = {
            "Access-Control-Allow-Origin: *",  # Or specific origin, e.g., "http://example.com"
            "Access-Control-Allow-Methods: GET, POST, OPTIONS",
            "Access-Control-Allow-Headers: Content-Type, Authorization"
        }
        send_response(self.server, "", http_code=200, content_type="text/html", extend_headers=cors_headers)

  
    def get_layout(self, request):
        """Return the JSON layout for the web form."""
        print("Get Layout")
        try:
            web_config = self.config.get('web_interface', {})
            motor_config = self.config.get('motor', {})
            
            layout = {
                "title": web_config.get('title', 'SmartStepper Control'),
                "description": web_config.get('description', 'Control your stepper motor with direction and speed settings'),
                "submitUrl": "/control",
                "elements": [
                    {
                        "id": "direction",
                        "type": "select",
                        "label": "Direction",
                        "options": [
                            {"value": "forward", "label": "Forward"},
                            {"value": "backward", "label": "Backward"}
                        ],
                        "defaultValue": "forward",
                        "required": True
                    },
                    {
                        "id": "speed",
                        "type": "input",
                        "inputType": "number",
                        "label": "Speed (RPM)",
                        "placeholder": "Enter speed in RPM",
                        "min": web_config.get('speed_range', {}).get('min', 0),
                        "max": web_config.get('speed_range', {}).get('max', 1000),
                        "defaultValue": str(motor_config.get('default_settings', {}).get('default_speed', 60)),
                        "required": True
                    },
                    {
                        "id": "steps",
                        "type": "input",
                        "inputType": "number",
                        "label": "Steps",
                        "placeholder": "Number of steps to move",
                        "min": web_config.get('steps_range', {}).get('min', 1),
                        "max": web_config.get('steps_range', {}).get('max', 10000),
                        "defaultValue": str(motor_config.get('default_settings', {}).get('default_steps', 200)),
                        "required": True
                    },
                    {
                        "id": "submit",
                        "type": "button",
                        "label": "Move Motor",
                        "action": "submit",
                        "style": "primary"
                    },
                    {
                        "id": "stop",
                        "type": "button",
                        "label": "Stop Motor",
                        "action": "custom",
                        "style": "danger"
                    }
                ],
                "outputMappings": [
                    {
                        "elementId": "status",
                        "responseKey": "status"
                    },
                    {
                        "elementId": "message",
                        "responseKey": "message"
                    }
                ]
            }
            
            self._send_json_response(layout)
        except Exception as e:
            print(f"Error in get_layout: {e}")
            self._send_error_response("Internal server error")
    
    def control_motor(self, request):
        """Handle motor control commands."""
        print("Control Motor")

        try:
            # Parse request body
            body = self._get_request_body(request)
            data = {}
            
            if body:
                try:
                    data = json.loads(body)
                except json.JSONDecodeError as e:
                    print(f"Error parsing JSON: {e}")
                    self._send_error_response("Invalid JSON in request body")
                    return
            direction = data.get('direction', 'forward')
            try:
                speed = float(data.get('speed', 60))
            except (ValueError, TypeError):
                speed = 60
            
            try:
                steps = int(data.get('steps', 200))
            except (ValueError, TypeError):
                steps = 200
            
            if not self.stepper_motor:
                response = {
                    "status": "error",
                    "message": "Motor not initialized. Please initialize first."
                }
            else:
                # Set direction (True for forward, False for backward)
                motor_direction = direction.lower() == 'forward'
                
                # Set speed
                try:
                    self.stepper_motor.set_speed(speed)
                except Exception as e:
                    print(f"Error setting speed: {e}")
                    response = {
                        "status": "error",
                        "message": f"Failed to set speed: {str(e)}"
                    }
                    self._send_json_response(response)
                    return
                
                # Move motor
                try:
                    success = self.stepper_motor.move_steps(steps, motor_direction)
                except Exception as e:
                    print(f"Error moving motor: {e}")
                    response = {
                        "status": "error",
                        "message": f"Failed to move motor: {str(e)}"
                    }
                    self._send_json_response(response)
                    return
                
                if success:
                    try:
                        position = self.stepper_motor.get_stepper_position()
                    except Exception as e:
                        print(f"Error getting position: {e}")
                        position = 0
                    
                    response = {
                        "status": "success",
                        "message": f"Motor moved {steps} steps {direction} at {speed} RPM",
                        "position": position
                    }
                else:
                    response = {
                        "status": "error",
                        "message": "Failed to move motor"
                    }
            
            self._send_json_response(response)
            
        except Exception as e:
            print(f"Error in control_motor: {e}")
            self._send_error_response(f"Error controlling motor: {str(e)}")
    
    def get_status(self, request):
        """Get current motor status."""
        try:
            if not self.stepper_motor:
                status = {
                    "status": "not_initialized",
                    "message": "Motor not initialized"
                }
            else:
                try:
                    motor_status = self.stepper_motor.get_status()
                    status = {
                        "status": "initialized",
                        "message": "Motor is ready",
                        "position": motor_status.get("position", 0),
                        "speed": motor_status.get("speed", 0),
                        "initialized": motor_status.get("initialized", False)
                    }
                except Exception as e:
                    print(f"Error getting motor status: {e}")
                    status = {
                        "status": "error",
                        "message": f"Error getting motor status: {str(e)}"
                    }
            
            self._send_json_response(status)
        except Exception as e:
            print(f"Error in get_status: {e}")
            self._send_error_response("Internal server error")
    
    def initialize_motor_from_api(self, request):
        # Parse request body
        body = self._get_request_body(request)
        data = {}
        
        if body:
            try:
                data = json.loads(body)
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON: {e}")
                self._send_error_response("Invalid JSON in request body")
                return
        response = self.initialize_motor(data)
        self._send_json_response(response)

    def initialize_motor(self, data={}):
        """Initialize the stepper motor."""
        print("Init Motor")
        try:
            
            # Get default pins from config
            default_pins = self.config.get('motor', {}).get('default_pins', {})
            default_settings = self.config.get('motor', {}).get('default_settings', {})
            
            # Use request data or fall back to config defaults
            try:
                step_pin = int(data.get('step_pin', default_pins.get('step_pin', 18)))
            except (ValueError, TypeError):
                step_pin = default_pins.get('step_pin', 18)
            
            try:
                dir_pin = int(data.get('dir_pin', default_pins.get('dir_pin', 19)))
            except (ValueError, TypeError):
                dir_pin = default_pins.get('dir_pin', 19)
            
            try:
                enable_pin = int(data.get('enable_pin', default_pins.get('enable_pin', 20)))
            except (ValueError, TypeError):
                enable_pin = default_pins.get('enable_pin', 20)
            
            try:
                microsteps = int(data.get('microsteps', default_settings.get('microsteps', 1)))
            except (ValueError, TypeError):
                microsteps = default_settings.get('microsteps', 1)
            
            print(f"Enable={enable_pin}  Dir={dir_pin} Step={step_pin} Microsteps= {microsteps} ")
            
            # Create stepper motor
            try:
                self.stepper_motor = self.motor_controller.create_motor(
                    "smart_stepper",
                    MotorType.STEPPER,
                    "stepper_driver",
                    step_pin=step_pin,
                    dir_pin=dir_pin,
                    enable_pin=enable_pin,
                    microsteps=microsteps
                )
            except Exception as e:
                print(f"Error creating motor: {e}")
                response = {
                    "status": "error",
                    "message": f"Failed to create motor: {str(e)}"
                }
                return
            
            # Initialize the motor
            try:
                success = self.stepper_motor.initialize()
            except Exception as e:
                print(f"Error initializing motor: {e}")
                return {
                    "status": "error",
                    "message": f"Failed to initialize motor: {str(e)}"
                }

            
            if success:
                return {
                    "status": "success",
                    "message": f"Stepper motor initialized successfully with pins: step={step_pin}, dir={dir_pin}, enable={enable_pin}"
                }
            else:
                return {
                    "status": "error",
                    "message": "Failed to initialize stepper motor"
                }
            
                
        except Exception as e:
            print(f"Error in initialize_motor: {e}")
            return {
                "status": "error",
                "message": "Failed to initialize stepper motor"
            }
    
    def _get_request_body(self, request):
        """Extract request body from HTTP request."""
        try:
            lines = request.split('\r\n')
            body_start = False
            body = ""
            
            for line in lines:
                if body_start:
                    body += line
                elif line == "":
                    body_start = True
            
            return body
        except Exception as e:
            print(f"Error parsing request body: {e}")
            return ""
    
    def _send_json_response(self, data):
        """Send JSON response to client."""
        try:
            response = json.dumps(data)
            self.server.send("HTTP/1.1 200 OK\r\n")
            self.server.send("Content-Type: application/json\r\n")
            self.server.send("Access-Control-Allow-Origin: *\r\n")
            self.server.send("Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n")
            self.server.send("Access-Control-Allow-Headers: Content-Type\r\n")
            self.server.send("\r\n")
            self.server.send(response)
        except Exception as e:
            print(f"Error sending JSON response: {e}")
            self._send_error_response("Internal server error")
    
    def _send_error_response(self, message):
        """Send error response to client."""
        try:
            response = {
                "status": "error",
                "message": message
            }
            self._send_json_response(response)
        except Exception as e:
            print(f"Error sending error response: {e}")
    
    def start(self):
        """Start the SmartStepper web server."""
        try:
            print("Starting SmartStepper web server...")
            print("Web interface available at: http://localhost:8080")
            print("API endpoints:")
            print("  GET  /api/layout    - Get form layout")
            print("  POST /api/init      - Initialize motor")
            print("  POST /api/control   - Control motor")
            print("  GET  /api/status    - Get motor status")
            self.server.start()
        except Exception as e:
            print(f"Error starting server: {e}")
            raise
    
    def stop(self):
        """Stop the SmartStepper web server."""
        try:
            if self.stepper_motor:
                try:
                    self.stepper_motor.shutdown()
                except Exception as e:
                    print(f"Error shutting down motor: {e}")
            
            try:
                self.server.stop()
            except Exception as e:
                print(f"Error stopping server: {e}")
        except Exception as e:
            print(f"Error in stop method: {e}")


def main():
    """Main function to run SmartStepper."""
    try:
        stepper = SmartStepper()
        stepper.start()
    except KeyboardInterrupt:
        print("\nShutting down SmartStepper...")
        try:
            stepper.stop()
        except Exception as e:
            print(f"Error during shutdown: {e}")
    except Exception as e:
        print(f"Error in main: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
