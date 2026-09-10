import time
import threading
from threading import Timer
import evdev
from evdev import InputDevice, ecodes
import os
import sys

class ScannerListener:
    def __init__(self, callback, min_length=3, timeout=2.0, device_path=None):
        """
        Initialize the scanner listener using evdev for Wayland compatibility.
        
        Args:
            callback: Function to call when a scan is detected
            min_length: Minimum length of scan data to be considered valid
            timeout: Time in seconds to clear buffer if no Enter key received
            device_path: Specific device path (e.g., '/dev/input/event0'), None for auto-detect
        """
        self.callback = callback
        self.min_length = min_length
        self.timeout = timeout
        self.device_path = device_path
        self.buffer = ""
        self.device = None
        self.running = False
        self.thread = None
        self.clear_timer = None
        
        # Key mapping for common characters
        self.keycode_to_char = {
            ecodes.KEY_A: 'a', ecodes.KEY_B: 'b', ecodes.KEY_C: 'c', ecodes.KEY_D: 'd',
            ecodes.KEY_E: 'e', ecodes.KEY_F: 'f', ecodes.KEY_G: 'g', ecodes.KEY_H: 'h',
            ecodes.KEY_I: 'i', ecodes.KEY_J: 'j', ecodes.KEY_K: 'k', ecodes.KEY_L: 'l',
            ecodes.KEY_M: 'm', ecodes.KEY_N: 'n', ecodes.KEY_O: 'o', ecodes.KEY_P: 'p',
            ecodes.KEY_Q: 'q', ecodes.KEY_R: 'r', ecodes.KEY_S: 's', ecodes.KEY_T: 't',
            ecodes.KEY_U: 'u', ecodes.KEY_V: 'v', ecodes.KEY_W: 'w', ecodes.KEY_X: 'x',
            ecodes.KEY_Y: 'y', ecodes.KEY_Z: 'z',
            ecodes.KEY_0: '0', ecodes.KEY_1: '1', ecodes.KEY_2: '2', ecodes.KEY_3: '3',
            ecodes.KEY_4: '4', ecodes.KEY_5: '5', ecodes.KEY_6: '6', ecodes.KEY_7: '7',
            ecodes.KEY_8: '8', ecodes.KEY_9: '9',
            ecodes.KEY_SPACE: ' ', ecodes.KEY_MINUS: '-', ecodes.KEY_EQUAL: '=',
            ecodes.KEY_LEFTBRACE: '[', ecodes.KEY_RIGHTBRACE: ']',
            ecodes.KEY_SEMICOLON: ';', ecodes.KEY_APOSTROPHE: "'",
            ecodes.KEY_COMMA: ',', ecodes.KEY_DOT: '.', ecodes.KEY_SLASH: '/',
            ecodes.KEY_BACKSLASH: '\\', ecodes.KEY_GRAVE: '`',
        }
        
        # Shifted characters
        self.shifted_chars = {
            '1': '!', '2': '@', '3': '#', '4': '$', '5': '%', '6': '^', '7': '&', '8': '*', '9': '(', '0': ')',
            '-': '_', '=': '+', '[': '{', ']': '}', ';': ':', "'": '"', ',': '<', '.': '>', '/': '?',
            '\\': '|', '`': '~'
        }
    
    def list_input_devices(self):
        """List all available input devices."""
        devices = []
        for path in evdev.list_devices():
            try:
                device = InputDevice(path)
                devices.append({
                    'path': path,
                    'name': device.name,
                    'phys': device.phys,
                    'capabilities': device.capabilities()
                })
            except:
                continue
        return devices
    
    def find_scanner_device(self):
        """
        Try to automatically find a scanner device.
        Looks for devices that support keyboard events.
        """
        devices = self.list_input_devices()
        
        # Look for devices that have keyboard capabilities
        keyboard_devices = []
        for device_info in devices:
            caps = device_info['capabilities']
            # Check if device has key events
            if ecodes.EV_KEY in caps:
                keyboard_devices.append(device_info)
        
        if not keyboard_devices:
            return None
        
        # Prefer devices with "barcode", "scanner", or "usb" in the name
        for device_info in keyboard_devices:
            name_lower = device_info['name'].lower()
            if any(keyword in name_lower for keyword in ['barcode', 'scanner', 'usb']):
                return device_info['path']
        
        # If no specific scanner found, return the first keyboard device
        # (user may need to specify the correct one manually)
        return keyboard_devices[0]['path']
    
    def _clear_buffer(self):
        """Clear the buffer (used by timeout or manual clearing)."""
        self.buffer = ""
        if self.clear_timer:
            self.clear_timer.cancel()
            self.clear_timer = None
    
    def _process_scan(self):
        """Process the accumulated buffer as a scan."""
        # Cancel the timeout timer first
        if self.clear_timer:
            self.clear_timer.cancel()
            self.clear_timer = None
            
        scan_data = self.buffer.strip()
        if len(scan_data) >= self.min_length:
            try:
                self.callback(scan_data)
            except Exception as e:
                print(f"Error in callback: {e}")
        
        # Clear buffer after processing
        self.buffer = ""
    
    def _handle_key_event(self, event, shift_pressed):
        """Convert key event to character and handle it."""
        if event.type != ecodes.EV_KEY or event.value != 1:  # Only key press events
            return
        
        key_code = event.code
        
        # Handle Enter key
        if key_code == ecodes.KEY_ENTER:
            self._process_scan()
            return
        
        # Handle clear keys (Escape, Tab)
        if key_code in [ecodes.KEY_ESC, ecodes.KEY_TAB]:
            self._clear_buffer()
            return
        
        # Convert keycode to character
        char = self.keycode_to_char.get(key_code)
        if char:
            # Apply shift if needed
            if shift_pressed and char in self.shifted_chars:
                char = self.shifted_chars[char]
            elif shift_pressed and char.isalpha():
                char = char.upper()
            
            # If buffer is empty, start the timeout timer
            if not self.buffer:
                self.clear_timer = Timer(self.timeout, self._clear_buffer)
                self.clear_timer.start()
            
            self.buffer += char
    
    def _listener_thread(self):
        """Thread function that runs the evdev listener."""
        try:
            # Find device if not specified
            if not self.device_path:
                self.device_path = self.find_scanner_device()
                if not self.device_path:
                    print("Error: No suitable input device found!")
                    print("Available devices:")
                    for device_info in self.list_input_devices():
                        print(f"  {device_info['path']}: {device_info['name']}")
                    return
            
            # Open the device
            try:
                self.device = InputDevice(self.device_path)
                print(f"Listening on device: {self.device.name} ({self.device_path})")
            except PermissionError:
                print(f"Permission denied accessing {self.device_path}")
                print("Try running with sudo or add your user to the input group:")
                print("  sudo usermod -a -G input $USER")
                print("  (then log out and back in)")
                return
            except Exception as e:
                print(f"Error opening device {self.device_path}: {e}")
                return
            
            # Grab the device to prevent other applications from receiving events
            # Comment out the next line if you want other apps to still receive the input
            self.device.grab()
            
            shift_pressed = False
            
            # Main event loop
            for event in self.device.read_loop():
                if not self.running:
                    break
                
                # Track shift key state
                if event.type == ecodes.EV_KEY:
                    if event.code in [ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT]:
                        shift_pressed = event.value == 1
                    else:
                        self._handle_key_event(event, shift_pressed)
                        
        except Exception as e:
            print(f"Listener thread error: {e}")
        finally:
            if self.device:
                try:
                    self.device.ungrab()
                    self.device.close()
                except:
                    pass
    
    def start(self):
        """Start the scanner listener in a separate thread."""
        if self.running:
            print("Scanner listener is already running.")
            return
        
        # Check permissions
        if os.geteuid() != 0:
            print("WARNING: Not running as root.")
            print("You may need to run with sudo or add your user to the input group:")
            print("  sudo usermod -a -G input $USER")
            print("  (then log out and back in)")
        
        self.running = True
        self.thread = threading.Thread(target=self._listener_thread, daemon=True)
        self.thread.start()
        print("Scanner listener started. Waiting for Enter-terminated scans...")
    
    def stop(self):
        """Stop the scanner listener."""
        if not self.running:
            print("Scanner listener is not running.")
            return
        
        print("Stopping scanner listener...")
        self.running = False
        
        # Cancel any pending timeout timer
        if self.clear_timer:
            self.clear_timer.cancel()
        
        # Close device
        if self.device:
            try:
                self.device.ungrab()
                self.device.close()
            except:
                pass
        
        # Wait for thread to finish
        if self.thread:
            self.thread.join(timeout=1.0)
        
        print("Scanner listener stopped.")
    
    def is_running(self):
        """Check if the listener is currently running."""
        return self.running and self.thread and self.thread.is_alive()
    
    def clear_buffer(self):
        """Manually clear the current buffer."""
        self._clear_buffer()

# Example usage with a long-running application
def on_scan(data):
    """Callback function called when a scan is made."""
    print(f"[{time.strftime('%H:%M:%S')}] Scanner scanned: {data}")
    # Add your custom logic here

class ScannerApp:
    """Example application that uses the scanner listener."""
    
    def __init__(self, device_path=None):
        self.listener = ScannerListener(
            callback=self.handle_scan,
            min_length=3,
            timeout=1.5,
            device_path=device_path
        )
        self.scan_count = 0
        self.scan_history = []
    
    def handle_scan(self, scan_data):
        """Handle scan with custom logic."""
        self.scan_count += 1
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        
        # Store in history
        self.scan_history.append({
            'timestamp': timestamp,
            'data': scan_data,
            'scan_number': self.scan_count
        })
        
        print(f"[{timestamp}] Scan #{self.scan_count}: {scan_data}")
        
        # Example processing logic
        if scan_data.startswith('ERROR'):
            print("  -> Error detected!")
        elif scan_data.isdigit():
            print(f"  -> Numeric scan: {len(scan_data)} digits")
        elif scan_data.startswith('http'):
            print(f"  -> QR code with URL detected")
        else:
            print(f"  -> Alphanumeric code: {len(scan_data)} characters")
    
    def list_devices(self):
        """List available input devices."""
        print("Available input devices:")
        for device_info in self.listener.list_input_devices():
            print(f"  {device_info['path']}: {device_info['name']}")
    
    def start(self):
        """Start the application."""
        print("Starting Scanner Application (evdev/Wayland)...")
        self.listener.start()
        
        # Main application loop
        try:
            while True:
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.listener.stop()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Scanner Listener using evdev')
    parser.add_argument('--device', '-d', help='Input device path (e.g., /dev/input/event0)')
    parser.add_argument('--list-devices', '-l', action='store_true', help='List available input devices')
    args = parser.parse_args()
    
    if args.list_devices:
        listener = ScannerListener(lambda x: None)
        print("Available input devices:")
        for device_info in listener.list_input_devices():
            caps = device_info['capabilities']
            has_keys = ecodes.EV_KEY in caps
            print(f"  {device_info['path']}: {device_info['name']} {'(keyboard)' if has_keys else ''}")
        sys.exit(0)
    
    # Simple example - start the listener
    listener = ScannerListener(on_scan, min_length=1, timeout=5.0, device_path=args.device)
    
    try:
        listener.start()
        
        print("Scanner listener is running (evdev/Wayland compatible).")
        print("Only scans terminated with Enter will be processed.")
        print("Press Ctrl+C to exit.")
        
        # Keep the main thread alive
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        listener.stop()