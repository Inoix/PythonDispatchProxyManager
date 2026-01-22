import subprocess
from enum import IntEnum
import time
import os
import re
import signal
import threading
import traceback
from dotenv import load_dotenv
import ast

# Load environment variables from .env file
load_dotenv()

DISPATCH_EXE = os.environ.get("DISPATCH_EXE", "dispatch.exe")
INTERFACES = ast.literal_eval(os.environ.get("INTERFACES", "{}"))
WHITELISTED_URL = os.environ.get("WHITELISTED_URL", "google.com")
NOT_WHITELISTED_URL = os.environ.get("NOT_WHITELISTED_URL", "youtube.com")

def execute_cmd(cmd_command):
    # Run the command and capture its output
    try:
        completed_process = subprocess.run(cmd_command, shell=True, text=True, capture_output=True,encoding="utf-8")
        output = completed_process.stdout
    except subprocess.CalledProcessError as e:
        output = e.output
        # Handle the error if the command execution fails
    return output
def interface_list():
    text = subprocess.run([DISPATCH_EXE, "list"], capture_output=True, text=True)
    # Remove ANSI codes
    text = re.sub(r'\x1b\[[0-9;]*m', '', text.stdout)
    
    # Split by horizontal dividers to get sections
    sections = re.split(r'╠═══════════════════════════════════╬════════════════════════════════════════╣', text)
    
    interfaces = {}
    
    for section in sections:
        lines = [line.strip() for line in section.split('\n') if line.strip()]
        
        for line in lines:
            if not '║' in line: continue
            
            parts = line.split('║')
            if len(parts) < 3: continue
            interface = parts[1].strip()
            ip = parts[2].strip()
            
            # Skip divider lines
            if any(c in interface for c in '═╦╣╠╗╝'):
                continue
            
            if interface and ip:
                if interface not in interfaces:
                    interfaces[interface] = []
                
                # Only add if it looks like an IP address
                if '.' in ip or ':' in ip:
                    interfaces[interface].append(ip)
    
    return interfaces

def ping(adr, interface, n=4):
    print("Running internet subprocess...")
    ping_result = execute_cmd(f'ping {adr} -S {interface} -n {n}')
    max_ping,avg_ping,min_ping,dns,sent,retrieved,loss = None,None,None,None,None,None,None
    for line in ping_result.splitlines():
        if "Packets:" in line: #getting sent,retrieved,loss
            value = ""
            index = 0
            for char in line:
                if char in list('0123456789'):
                    value += char
                elif len(value):
                    if index == 0:
                        sent = int(value)
                    elif index == 1:
                        retrieved = int(value)
                    elif index == 2:
                        loss = int(value)
                    index += 1
                    value = ""
        elif 'Pinging' in line: #getting dns
            if not re.match(f'Pinging {adr} '+r'\[(.*?)\]', line):
                dns = False
            else:
                dns = True
        elif "Minimum" in line or "Минимальное" in line: #ping     Minimum = 68ms, Maximum = 80ms, Average = 72ms
            value = ""
            index = 0
            for char in line:
                if char in list('0123456789'):
                    value += char
                elif len(value):
                    if index == 2:
                        avg_ping = int(value)
                    elif index == 1:
                        max_ping = int(value)
                    elif index == 0:
                        min_ping = int(value)
                    index += 1
                    value = ""
    return dns,(sent,retrieved,loss),(min_ping,avg_ping,max_ping)

class Element(object):
    def __init__(self,color:str='green', text:str="Test"):
        if not color in "green,red,gray,blue,orange":
            raise ValueError(f"{color} of element with text:'{text}' is not green, red, blue, gray or orange.")
        self.color = color
        self.text = text
    def __repr__(self):
        t = self.text
        if len(t) > 20:
            t = t[:17]+"..."
        return f"<text:'{t}'color:{self.color}>"

class Interface():
    def __init__(self, name):
        self.name = name
        self.ip = None
        self.statuses = [Element('gray','Disconnected'), #-1
            Element('red','No Internet connection'),     #0
            Element('red','DNS only'),                   #1
            Element('orange','Whitelisted'),             #2
            Element('green','Full access')]              #3
        self.status = Element('gray','Loading...')
        self.last_level = -1
        self.last_last_level = -1
        self.last_check = 0
    def check_for_level(self,level):
        if level <= 0:
            interfaces = interface_list()
            for i in interfaces.keys():
                #print(f"    {self.name} {i}")
                if self.name.lower() == i.lower():
                    self.ip = interfaces[self.name][0]
                    return True
        elif level == 1:
            dns,packets,pings = ping(WHITELISTED_URL,self.ip)
            if dns or pings[1]:
                return True
        elif level == 2:
            dns,packets,pings = ping(WHITELISTED_URL,self.ip)
            if pings[1]:
                return True
        elif level == 3:
            dns,packets,pings = ping(NOT_WHITELISTED_URL,self.ip)
            if pings[1]:
                return True
        return False
    def update(self):
        delta = time.time()-self.last_check
        if delta < 30: 
            device_available = self.check_for_level(0)
            if device_available:
                if self.last_level == -1:
                    self.last_level = 0
                    self.status = self.statuses[0]
                    #go and check for an upgrade
                else:
                    return self.status
            else:
                if self.last_level > -1:
                    self.last_level = -1
                    self.status = self.statuses[0]
                return self.status
        self.last_check = time.time()
        level = self.last_level
        
        available = self.check_for_level(level)
        if available:
            if level == -1:
                level = 0
            #try to upgrade level
            while level < 3:
                level += 1
                available = self.check_for_level(level)
                if not available: 
                    level -= 1
                    break
        else:
            #try to downgrade level, 'cause current one is not available
            while level > 0:
                level -= 1
                available = self.check_for_level(level)
                if available: break
        self.last_level = level
        self.status = self.statuses[level+1]
        return self.status
class ServerController:
    def __init__(self, server_path, args=None):
        self.server_path = server_path
        self.process = None
        self.args = args
        self.stdout_buffer = []
        self.stderr_buffer = []
        self.stdout_thread = None
        self.stderr_thread = None
    
    def _read_stdout(self):
        """Thread function to read stdout non-blockingly"""
        while self.process and self.process.stdout:
            line = self.process.stdout.readline()
            if line:
                decoded = line.decode('utf-8', errors='ignore').rstrip()
                self.stdout_buffer.append(decoded)
                print(f"[STDOUT] {decoded}")
            else:
                break
    
    def _read_stderr(self):
        """Thread function to read stderr non-blockingly"""
        while self.process and self.process.stderr:
            line = self.process.stderr.readline()
            if line:
                decoded = line.decode('utf-8', errors='ignore').rstrip()
                self.stderr_buffer.append(decoded)
                print(f"[STDERR] {decoded}")
            else:
                break
                
    def start(self):
        """Start the server"""
        if self.is_running():
            print("Server is already running")
            return False
        
        try:
            # Start the server
            # Use CREATE_NEW_PROCESS_GROUP on Windows for signal handling
            creationflags = 0
            if os.name == 'nt':  # Windows
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            values = [self.server_path]
            for i in self.args or []:
                values.append(i)
            self.process = subprocess.Popen(
                values,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                creationflags=creationflags
            )
            print(f"Server started with PID: {self.process.pid}")

            # Start threads to read output non-blockingly
            self.stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
            self.stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
            self.stdout_thread.start()
            self.stderr_thread.start()
            
            # Give the process a moment to start
            time.sleep(2)
            
            # Check if process is still alive
            if self.process.poll() is not None:
                print(f"Server terminated immediately with exit code: {self.process.returncode}")
                # Try to get any error output
                try:
                    stdout, stderr = self.process.communicate(timeout=1)
                    if stdout:
                        print(f"Last stdout: {stdout.decode('utf-8', errors='ignore')}")
                    if stderr:
                        print(f"Last stderr: {stderr.decode('utf-8', errors='ignore')}")
                except:
                    pass
                return False
                
            return True
        except Exception as e:
            print(f"Failed to start server: {e}")
            return False
        
    def stop(self):
        """Stop the server"""
        if self.process is None:
            print("No server process found")
            return False
        
        try:
            # First, try to read any remaining output
            if self.stdout_thread:
                self.stdout_thread.join(timeout=1)
            if self.stderr_thread:
                self.stderr_thread.join(timeout=1)
            
            if os.name == 'nt':  # Windows
                # Use CTRL_BREAK_EVENT for process groups
                self.process.send_signal(signal.CTRL_BREAK_EVENT)
            else:  # Unix/Linux/Mac
                self.process.terminate()
            
            # Wait for process to terminate
            self.process.wait(timeout=10)
            print("Server stopped")
            return True
        except subprocess.TimeoutExpired:
            print("Force killing server...")
            self.process.kill()
            self.process.wait()
            return True
        except Exception as e:
            print(f"Error stopping server: {e}")
            return False
    
    def is_running(self):
        """Check if server is running"""
        if self.process is None:
            return False
        
        # Poll returns None if process is still running
        return self.process.poll() is None
    
    def get_output(self):
        """Get server output if available - non-blocking"""
        output = "\n".join(self.stdout_buffer)
        if not output:
            output = "\n".join(self.stderr_buffer)
        return output if output else "No output available"
class DispatchController(ServerController):
    def __init__(self, interfaces):
        print("Starting with:",interfaces)
        interfaces.insert(0,"start")
        super().__init__(DISPATCH_EXE,interfaces)
        self.start()
    def restart(self,interfaces):
        print("Restarting with:",interfaces)
        self.stop()
        if len(interfaces) == 0: return
        interfaces.insert(0,"start")
        self.args = interfaces
        return self.start()

if __name__ == '__main__':
    interfaces_objects =  [Interface(i) for i in INTERFACES]
    available = []
    for interface in interfaces_objects:
        interface.update()
    for interface in interfaces_objects:
        if interface.last_level == 3:
            available.append(interface)
    arguments = []
    for interface in available:
        arguments.append(interface.ip+'/'+str(INTERFACES[interface.name]))
    Controller = DispatchController(arguments)

    try:
        while True:
            for interface in interfaces_objects:
                interface.update()
            
            new_available = []
            for interface in interfaces_objects:
                print(f"{interface.name} - {interface.last_level}")
                if interface.last_level == 3:
                    new_available.append(interface)
            if new_available != available:
                available = new_available
                arguments = []
                for interface in available:
                    arguments.append(interface.ip+'/'+str(INTERFACES[interface.name]))
                Controller.restart(arguments)
            #print(available)
            if not Controller.is_running():
                print("Controller ended early")
                print(Controller.process.poll() if Controller.process else "No process")
            print(Controller.get_output())
            time.sleep(1)
    except Exception as er:
        print(traceback.format_exc())
    finally:
        Controller.stop()
    input("Press Enter to exit...")