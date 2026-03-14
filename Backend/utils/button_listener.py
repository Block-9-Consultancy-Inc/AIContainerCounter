import serial
import time
from threading import Thread


def _listening_thread(arduino_port: str, baud_rate: int, on_button_pressed):
        buttons = [1, 2, 3, 4, 5]
        try:
            ser = serial.Serial(arduino_port, baud_rate, timeout=1)
            time.sleep(2)  # Wait for the serial connection to initialize
            print(f"Listening on {arduino_port} at {baud_rate} baud...")
            
            while True:
                line = ser.readline().decode('utf-8').strip()
                if line:
                    # Expecting a message like "Button 1 pressed"
                    if "Button" in line and "pressed" in line:
                        parts = line.split()
                        if len(parts) >= 3:
                            button_id = int(parts[1]) 
                            if button_id in buttons:
                                on_button_pressed(int(button_id))
                time.sleep(0.05)
        
        except serial.SerialException as e:
            print(f"Error opening serial port {arduino_port}: {e}")
        except KeyboardInterrupt:
            print("Exiting script.")
        finally:
            if 'ser' in locals() and ser.is_open:
                ser.close()

class ButtonListener:
    def __init__(self, on_button_pressed, arduino_port: str, baud_rate = 9600):
        self.arduino_port = arduino_port
        self.baud_rate = baud_rate
        self.thread = Thread(target=_listening_thread, args=(self.arduino_port, self.baud_rate, on_button_pressed), daemon=True)
        self.thread.start()




def main():
    # Update this to match your Arduino's serial port
    #arduino_port = "/dev/ttyACM0"  # On Windows, this might be 'COM3', 'COM4', etc.
    arduino_port = "/dev/ttyUSB0"  # On Windows, this might be 'COM3', 'COM4', etc.
    baud_rate = 9600

    def on_button_pressed(button_id: int):
        print(f'{button_id} pressed!')
        print(f'baud rate: {baud_rate}')

    button_listener = ButtonListener(on_button_pressed, arduino_port, baud_rate)

    button_listener.thread.join()

if __name__ == "__main__":
    main()