import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import queue
import time
from InternetController import *
import pystray
from PIL import Image
from pystray import MenuItem as item
from windows_toasts import WindowsToaster, Toast, ToastDisplayImage, ToastImage, ToastImagePosition

class DispatchGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Dispatch Proxy Manager")
        self.root.geometry("800x600")
        
        # Control variables
        self.running = False
        self.controller = None
        self.interfaces_objects = [Interface(i) for i in INTERFACES]
        self.available = []
        self.update_queue = queue.Queue()
        self.tray_icon = None
        self.minimized_to_tray = False
        
        try:
            if os.path.exists("icon.ico"):
                self.root.iconbitmap("icon.ico")
                self.toast_image = ToastImage("icon.ico")
        except:
            pass
        self.setup_ui()
        self.setup_tray_icon()
        self.start_monitoring()
        
        self.root.bind('<Unmap>', self.on_window_minimize)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def setup_ui(self):
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Status frame
        status_frame = ttk.LabelFrame(main_frame, text="Controller Status", padding="10")
        status_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.status_label = ttk.Label(status_frame, text="Controller: Stopped", font=('Arial', 10, 'bold'))
        self.status_label.grid(row=0, column=0, sticky=tk.W)
        
        self.control_button = ttk.Button(status_frame, text="Start Controller", command=self.toggle_controller)
        self.control_button.grid(row=0, column=1, padx=(20, 0))
        
        # Minimize to tray button
        self.tray_button = ttk.Button(status_frame, text="Minimize to Tray", command=self.minimize_to_tray)
        self.tray_button.grid(row=0, column=2, padx=(10, 0))
        
        
        # Interfaces frame
        interfaces_frame = ttk.LabelFrame(main_frame, text="Network Interfaces", padding="10")
        interfaces_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        
        # Interface list
        self.interface_tree = ttk.Treeview(interfaces_frame, columns=('level', 'ip'), height=10)
        self.interface_tree.heading('#0', text='Interface')
        self.interface_tree.heading('level', text='Level')
        self.interface_tree.heading('ip', text='IP Address')
        
        self.interface_tree.column('#0', width=150)
        self.interface_tree.column('level', width=80, anchor=tk.CENTER)
        self.interface_tree.column('ip', width=120)
        
        scrollbar = ttk.Scrollbar(interfaces_frame, orient=tk.VERTICAL, command=self.interface_tree.yview)
        self.interface_tree.configure(yscrollcommand=scrollbar.set)
        
        self.interface_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        interfaces_frame.columnconfigure(0, weight=1)
        interfaces_frame.rowconfigure(0, weight=1)
        
        # Log output frame
        log_frame = ttk.LabelFrame(main_frame, text="Controller Output", padding="10")
        log_frame.grid(row=1, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=20, width=50, state='disabled')
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Clear log button
        clear_button = ttk.Button(log_frame, text="Clear Log", command=self.clear_log)
        clear_button.grid(row=1, column=0, pady=(5, 0))
        
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        # Active proxies frame
        proxies_frame = ttk.LabelFrame(main_frame, text="Active Proxies", padding="10")
        proxies_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        
        self.proxies_label = ttk.Label(proxies_frame, text="No active proxies")
        self.proxies_label.grid(row=0, column=0, sticky=tk.W)
        
        # Configure main frame grid weights
        main_frame.rowconfigure(1, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Initialize interface tree
        for interface in self.interfaces_objects:
            self.interface_tree.insert('', 'end', interface.name, 
                                      text=interface.name,
                                      values=('-', '-'))
        
    def setup_tray_icon(self):
        """Setup system tray icon"""
            
        try:
            # Try to load icon
            if os.path.exists("icon.ico"):
                image = Image.open("icon.ico")
            else:
                # Create a simple default icon
                image = Image.new('RGB', (64, 64), color='blue')
            
            # Create menu for tray icon
            menu = (
                item('Show Window', self.show_from_tray),
                #Note: IDE is lying.
                item('Start Controller', self.tray_start_controller, enabled=lambda item: not self.running),  # pyright: ignore[reportArgumentType]
                item('Stop Controller', self.tray_stop_controller, enabled=lambda item: self.running),  # pyright: ignore[reportArgumentType]
                item('Exit', self.tray_exit)
            )
            
            # Create tray icon
            self.tray_icon = pystray.Icon(
                "dispatch_proxy_manager",
                image,
                "Dispatch Proxy Manager",
                menu
            )
            
        except Exception as e:
            print(f"Failed to setup tray icon: {e}")
            self.tray_button.config(state='disabled', text="Tray Error")
        
    def log_message(self, message):
        self.log_text.configure(state='normal')
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state='disabled')
        
    def clear_log(self):
        self.log_text.configure(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state='disabled')
        
    def toggle_controller(self):
        if not self.running:
            self.start_controller()
        else:
            self.stop_controller()
            
    def start_controller(self):
        try:
            # Initial update
            for interface in self.interfaces_objects:
                interface.update()
                
            self.available = []
            for interface in self.interfaces_objects:
                if interface.last_level == 3:
                    self.available.append(interface)
                    
            arguments = []
            for interface in self.available:
                arguments.append(interface.ip + '/' + str(INTERFACES[interface.name]))
                
            if arguments:
                self.controller = DispatchController(arguments)
                self.running = True
                self.status_label.config(text="Controller: Running", foreground="green")
                self.control_button.config(text="Stop Controller")
                self.log_message("Controller started successfully")
                self.update_proxies_display()
            else:
                self.log_message("No available interfaces at level 3")
                
        except Exception as e:
            self.log_message(f"Error starting controller: {e}")
            
    def stop_controller(self):
        if self.controller:
            self.controller.stop()
        self.running = False
        self.status_label.config(text="Controller: Stopped", foreground="red")
        self.control_button.config(text="Start Controller")
        self.log_message("Controller stopped")
        self.proxies_label.config(text="No active proxies")
        
    def update_interface_display(self):
        for interface in self.interfaces_objects:
            level = interface.last_level
            level_text = str(level) if level >= 0 else "Offline"
            ip_text = interface.ip if interface.ip else "-"
            
            # Update tree item
            self.interface_tree.item(interface.name, values=(level_text, ip_text))
            
            # Color coding
            if level == 3:
                self.interface_tree.tag_configure('level3', background='#d4edda')
                self.interface_tree.item(interface.name, tags=('level3',))
            elif level >= 0:
                self.interface_tree.tag_configure('level1-2', background='#fff3cd')
                self.interface_tree.item(interface.name, tags=('level1-2',))
            else:
                self.interface_tree.tag_configure('offline', background='#f8d7da')
                self.interface_tree.item(interface.name, tags=('offline',))
    
    def show_toast(self,*args):
        toast_images = [
            ToastDisplayImage(self.toast_image, position=ToastImagePosition.AppLogo),
        ]
        new_toast = Toast(text_fields=args, images=toast_images)
        WindowsToaster('Dispatch Proxy Manager').show_toast(new_toast)
        
    def process_levels_change(self):
        for interface in self.interfaces_objects:
            old = interface.last_last_level
            new = interface.last_level
            if old > new:
                if new == -1:
                    self.show_toast(f"{interface.name} disconnected!")
                else:
                    self.show_toast(f"{interface.name} downgraded!",f"from {old} to {new}.")
            elif new > old:
                if old == -1:
                    self.show_toast(f"{interface.name} connected!",f"level: {new}.")
                else:
                    self.show_toast(f"{interface.name} upgraded!",f"from {old} to {new}")
    
    def update_proxies_display(self):
        if self.available:
            proxies_text = ", ".join([f"{interface.name} ({interface.ip})" 
                                     for interface in self.available])
            self.proxies_label.config(text=proxies_text)
        else:
            self.proxies_label.config(text="No active proxies")
            
    def monitoring_thread(self):
        """Dispatch Proxy Monitoring thread"""
        while True:
            try:
                
                for interface in self.interfaces_objects:
                    interface.last_last_level = interface.last_level
                # Update interfaces
                for interface in self.interfaces_objects:
                    try:
                        interface.update()
                    except Exception as er:
                        print("Error while updating")
                        print(traceback.format_exc())
                # Check for changes
                new_available = []
                for interface in self.interfaces_objects:
                    if interface.last_level == 3:
                        new_available.append(interface)
                        
                if new_available != self.available:
                    self.update_queue.put(('levels_change', None))
                    self.available = new_available
                    arguments = []
                    for interface in self.available:
                        arguments.append(interface.ip + '/' + str(INTERFACES[interface.name]))
                        
                    if self.running and self.controller:
                        if arguments:
                            self.controller.restart(arguments)
                            self.log_message(f"Controller restarted with {len(arguments)} interfaces")
                        else:
                            self.controller.stop()
                            self.log_message("Controller stopped - no available interfaces")
                else:
                    if any([i.last_last_level != i.last_level for i in self.interfaces_objects]):
                        self.update_queue.put(('levels_change', None))
                    
                # Update display via queue
                self.update_queue.put(('interfaces', None))
                
                # Check controller status
                if self.running and self.controller:
                    if not self.controller.is_running():
                        self.log_message("Controller ended unexpectedly")
                        self.running = False
                        self.update_queue.put(('status_stop', None))
                    else:
                        output = self.controller.get_output()
                        if output and output != "No output available":
                            self.update_queue.put(('log', output))
                            
                time.sleep(1)
                
            except Exception as e:
                self.update_queue.put(('log', f"Monitoring error: {e}"))
                
    def process_queue(self):
        try:
            while True:
                msg_type, data = self.update_queue.get_nowait()
                print(msg_type,data)
                if msg_type == 'interfaces':
                    self.update_interface_display()
                    self.update_proxies_display()
                elif msg_type == 'status_stop':
                    self.status_label.config(text="Controller: Stopped", foreground="red")
                    self.control_button.config(text="Start Controller")
                    self.proxies_label.config(text="No active proxies")
                elif msg_type == 'log':
                    self.log_message(data)
                elif msg_type == 'levels_change':
                    self.process_levels_change()
                    
        except queue.Empty:
            pass
            
        self.root.after(100, self.process_queue)
        
    def start_monitoring(self):
        # Start monitoring thread
        monitor_thread = threading.Thread(target=self.monitoring_thread, daemon=True)
        monitor_thread.start()
        
        # Start queue processing
        self.process_queue()
                    
    def on_window_minimize(self, event):
        """Handle window minimization event"""
        if self.root.state() == 'iconic' and not self.minimized_to_tray:
            # User clicked minimize button, minimize to tray
            self.minimize_to_tray()
            
    def minimize_to_tray(self):
        """Minimize window to system tray"""
        print("Minimizing to tray")
        if self.tray_icon:
            self.root.withdraw()  # Hide the window
            self.minimized_to_tray = True
            self.log_message("Minimized to system tray")
            print("Minimized to system tray")
            
            # Run tray icon in separate thread
            tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
            tray_thread.start()
            print("Started tray thread")
            
    def show_from_tray(self, icon=None, item=None):
        """Show window from system tray"""
        if self.tray_icon:
            self.tray_icon.stop()
            
        print("Remaking tray_icon object...")
        self.setup_tray_icon()
        self.root.after(0, self.restore_window)
        
    def restore_window(self):
        """Restore the window"""
        self.root.deiconify()  # Show the window
        self.root.lift()  # Bring to top
        self.root.focus_force()  # Force focus
        self.minimized_to_tray = False
        
    def tray_start_controller(self, icon=None, item=None):
        """Start controller from tray menu"""
        self.root.after(0, self.start_controller)
        
    def tray_stop_controller(self, icon=None, item=None):
        """Stop controller from tray menu"""
        self.root.after(0, self.stop_controller)
        
    def tray_exit(self, icon=None, item=None):
        """Exit application from tray menu"""
        self.root.after(0, self.clean_exit)
        
    def clean_exit(self):
        """Clean exit procedure"""
        if self.tray_icon:
            self.tray_icon.stop()
        if self.controller:
            self.controller.stop()
        self.root.destroy()
        
    def on_closing(self):
        """Handle window closing"""
        if self.minimized_to_tray:
            # Window is already hidden in tray, just exit
            self.clean_exit()
        else:
            # Minimize to tray instead of closing
            self.minimize_to_tray()

if __name__ == '__main__':

    # Create and run GUI
    root = tk.Tk()
    app = DispatchGUI(root)
    
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    root.mainloop()